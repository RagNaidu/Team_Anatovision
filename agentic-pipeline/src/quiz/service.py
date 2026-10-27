"""What the Quiz screens call. No Streamlit here.

  new_quiz(user, allowed, request, rt, ...)   build (or fail to build) a quiz: every question must pass every gate; never padded
      -> {"status": "ready" | "offer" | "failed", "quiz_id", "passed", "requested", "message"}
      "offer": a 10-question quiz had only 5 that passed; the student must explicitly accept the 5 (accept_offer) or discard
  open_view(user, qid, allowed, ...)           the student's view of an OPEN quiz: questions and saved selections, nothing else
  results(user, qid, allowed, ...)             ONLY for a submitted quiz: selections, correct answers, explanations, evidence
Access is checked on every call, against the grants as they are NOW: a quiz built from a lecture the student can no longer open is not shown.
The key, explanations and evidence never leave this module before submission.
"""
import random
import time

from src import llm
from src import query as qry
from src import web_fallback, web_sources
from src.modes import qa
from src.quiz import evidence, generate, items
from src.quiz.store import LENGTHS, QuizError, QuizStore

LABEL = {"unreviewed": generate.LABEL_UNREVIEWED, "approved": "Approved by {by}, {date}.", "rejected": "Marked as not usable by {by}, {date}."}
TIER_LABEL = {"verified": "Verified fix (Dr. Inglis)", "course": "Course material", "openstax": "OpenStax Anatomy & Physiology 2e (not course notes)",
              "web": "From the web, not in Dr. Inglis's notes or OpenStax"}


def validate_request(request):
    if request.get("n") not in LENGTHS:
        raise QuizError("A quiz has exactly 5 or 10 questions.")
    if request.get("mode") not in ("materials", "topic"):
        raise QuizError("Choose lectures or guides, or type a topic.")
    return request


def item_allowed(item, allowed, note_lectures=frozenset()):
    """Course and verified evidence of an item must still be open to this user. Open material (OpenStax, web) always is."""
    if allowed is None:
        return True
    for p in item["evidence"].values():
        if p["tier"] in ("course", "verified"):
            chunk = {"source_type": "dissection_guide" if p["kind"] == "dissection_guide" else "notes", "lecture": p.get("lecture", ""),
                     "lecture2": p.get("lecture2", ""), "guide": p.get("guide", "")}
            if not evidence.allowed_chunk(chunk, allowed, note_lectures):
                return False
    return True


def _scope_of(request):
    return {"mode": request["mode"], "selected": sorted(request.get("selected") or []), "topic": (request.get("topic") or "").strip(), "n": request["n"]}


def _matches_topic(item, request):
    words = set(w for w in items.words(request.get("topic", "")) if len(w) > 3)
    text = items.norm(item["stem"] + " " + item["lead_in"] + " " + item["objective"] + " " + (item.get("scope") or {}).get("topic", ""))
    return bool(words) and all(w in text for w in words)


def _in_materials(item, selected):
    """Every course passage the item rests on belongs to a lecture or guide the student selected (and there is at least one)."""
    course = [p for p in item["evidence"].values() if p["tier"] in ("course", "verified")]
    if not course or len(course) != len(item["evidence"]):
        return False
    return all((p["guide"] in selected) if p["kind"] == "dissection_guide" else (p["lecture"] in selected) for p in course)


def _current_text(p, by_id, ctx):
    """The usable text of a stored passage as it is NOW, or None if the passage is gone or no longer usable."""
    if p["tier"] == "verified":
        fix = next((f for f in ctx.get("fixes", []) if f"fix:{f['id']}" == p["id"] and f["decision"] != "notes_correct"), None)
        return fix["correction"].strip() if fix else None
    c = by_id.get(p["id"])
    if c is None:
        return None
    cur = evidence.passage_of(c, ctx)
    return cur["text"] if cur else None


def eligible_items(store, searcher, allowed, ctx, request, note_lectures=frozenset(), web_current=None):
    """Saved, already-checked items that may be reused for this request RIGHT NOW. All of these must hold:
      * same checks version, not rejected by the professor (and approved, when only approved questions are wanted);
      * the student may still open every course source it rests on;
      * every cited passage still has exactly the text it had when the item was checked (a changed or withdrawn line retires the item);
      * it belongs to the selected lectures/guides, or matches the typed topic;
      * web evidence only if the CURRENT (cached or fresh) lookup returns the same passage id with identical text; otherwise the item is retired.
    Frozen keys and option order are never touched."""
    by_id = {c["id"]: c for c in searcher.chunks}
    out = []
    for it in store.list_items(None, 5000):
        if it.get("version") != items.QUIZ_VERSION or it["review"]["status"] == "rejected":
            continue
        if request.get("reviewed_only") and it["review"]["status"] != "approved":
            continue
        if not item_allowed(it, allowed, note_lectures):
            continue
        if any(p["tier"] == "web" and (web_current or {}).get(p["id"]) != p["text"] for p in it["evidence"].values()):
            continue
        if request["mode"] == "materials":
            if not _in_materials(it, set(request.get("selected") or [])):
                continue
        elif not _matches_topic(it, request):
            continue
        if all(p["tier"] == "web" or _current_text(p, by_id, ctx) == p["text"] for p in it["evidence"].values()):
            out.append(it)
    return out


def pick_unique(candidates, n, rng=None):
    """Up to n eligible items with no near-duplicates among them: instructor-approved first, then the rest in random order."""
    rng = rng or random.Random()
    pool = list(candidates)
    rng.shuffle(pool)
    pool.sort(key=lambda i: i["review"]["status"] != "approved")
    chosen = []
    for it in pool:
        text = it["stem"] + " " + it["lead_in"]
        if len(chosen) < n and not any(generate.jaccard(text, c["stem"] + " " + c["lead_in"]) > 0.7 or items.same_point(it, c) for c in chosen):
            chosen.append(it)
    return chosen


def generate_probe(client, gen_model, ver_model):
    return llm.probe(client, [gen_model, ver_model])


def failure_reason(batch):
    """Why a build fell short, in the words the student sees: the AI service failing is not the same as the material being thin."""
    non_ok = [r for r in batch.rejected]
    gateway = sum(r["stage"] == "model_error" for r in non_ok)
    if batch.aborted or (batch.gateway_errors and gateway >= max(1, len(non_ok) // 2)):
        return "gateway"
    return "rejected"


MESSAGES = {
    "insufficient_evidence": "There is not enough source text for this request to write {n} well-supported questions. Try a broader topic or more lectures.",
    "rejected": "{have} of {n} questions passed every check. The other drafts were rejected by the checks, which says nothing wrong about your material. "
                "The {have} are saved: Continue preparing looks only for the {missing} still missing.",
    "gateway": "The AI service did not respond reliably, so preparation stopped. Nothing is wrong with your lecture. "
               "{have_text}Continue preparing tries again for the {missing} still missing.",
}


def new_quiz(user, allowed, request, rt, *, store=None, ctx=None, rng=None, web_lookup="default", progress=None, ver_model=None):
    """Reuse saved, checked questions first, generate only what is missing, and start a quiz only when ALL n are in hand.
    -> {"status": ready | offer | partial | failed, "reason", "quiz_id", "have", "requested", "reused", "generated", "message", ...}
    partial = some questions are saved for this request but fewer than asked (no quiz was started; Continue preparing finds the rest)."""
    store = store or QuizStore()
    request = validate_request(dict(request))
    n, rng = request["n"], rng or random.Random()
    note_lectures = getattr(rt.searcher, "note_lectures", frozenset())
    scope = _scope_of(request)
    run = {"scope": scope, "requested": n, "reviewed_only": bool(request.get("reviewed_only"))}
    ctx = ctx if ctx is not None else qa.load_context()
    t0 = time.perf_counter()
    client, gen_model, default_ver, backend = llm.quiz_backend(rt)
    ver_model = ver_model or default_ver
    run["backend"] = backend
    run["models"] = [gen_model, ver_model]

    def report(progress_fn, have, note=""):
        if progress_fn:
            progress_fn(have, n, note)

    def finish(status, reason, chosen, message, **extra):
        qid = None
        if status in ("ready", "offer"):
            take = chosen if status == "ready" else chosen[:5]
            qid = store.create_quiz(user, [i["item_id"] for i in take], n, scope, "open" if status == "ready" else "offer", bool(request.get("reviewed_only")))
        store.log_run(user, {**run, "outcome": status, "reason": reason, "message": message, "passed": len(chosen), "seconds": round(time.perf_counter() - t0, 1), **extra})
        return {"status": status, "reason": reason, "quiz_id": qid, "have": len(chosen), "passed": len(chosen), "requested": n, "message": message,
                "reused": extra.get("reused", 0), "generated": extra.get("generated", 0)}

    if web_lookup == "default":
        web_lookup = web_fallback.lookup if web_sources.web_fallback_on() else None
    web_current = None
    if request["mode"] == "topic" and web_lookup is not None and any(p["tier"] == "web" for i in store.list_items(None, 5000) for p in i["evidence"].values()
                                                                    if _matches_topic(i, request)):
        web_current = {p["id"]: p["text"] for p in evidence.web_passages(request["topic"], web_lookup)}          # no model call; the lookup is cached for days
    chosen = pick_unique(eligible_items(store, rt.searcher, allowed, ctx, request, note_lectures, web_current), n, rng)
    reused = len(chosen)
    run["reused"] = reused
    report(progress, reused, f"Reusing {reused} saved question(s) that were already checked against your current sources" if reused else "")
    if request.get("reviewed_only"):
        if reused < min(LENGTHS):
            return finish("failed", "no_approved", chosen, f"Only {reused} instructor-approved question(s) match this choice. A quiz needs at least 5, and approved "
                          "questions are never replaced by unreviewed ones.", reused=reused)
        status = "ready" if reused == n else "offer"
        return finish(status, "", chosen, "" if status == "ready" else f"Only {reused} approved questions match. Start a 5-question quiz instead?", reused=reused)
    if reused == n:
        return finish("ready", "", chosen, "", reused=reused, generated=0)

    missing = n - reused
    report(progress, reused, "Checking that the AI service (BullsAI) is reachable")
    down = [c for c in generate_probe(client, gen_model, ver_model) if not c["ok"]]
    if down:                                                                  # fail in seconds, with the real reason, before any drafting
        names = ", ".join(f"{c['model']} ({c['error']})" for c in down)
        quota = any("budget" in c["error"] or "credit" in c["error"] for c in down)
        saved = f"{len(chosen)} question(s) are saved and can still be reused. " if chosen else ""
        msg = (f"The course's AI budget (BullsAI) is used up, so no new questions can be prepared right now: {names}. Nothing is wrong with your lecture. {saved}"
               "Ask the course staff to raise the budget, then press Continue preparing." if quota else
               f"The AI service (BullsAI) could not be reached: {names}. Nothing is wrong with your lecture or your questions. {saved}"
               "Check the connection (for example the UB VPN) and press Continue preparing.")
        return finish("partial" if chosen else "failed", "quota" if quota else "gateway", chosen, msg, reused=reused, generated=0, service_down=down)
    def scope_check(topic):
        label, _u, sure = qry.scope_check(client, topic, gen_model)
        return label, sure
    pool = evidence.build_pool({**request, "n": missing}, rt.searcher, allowed, ctx, rng, web_lookup, scope_check=scope_check if request["mode"] == "topic" else None)
    run.update(events=pool.events, web_used=pool.web_used, passages=len(pool.passages))
    if pool.error:
        reason = "insufficient_evidence"
        msg = pool.error
        return finish("partial" if chosen else "failed", reason, chosen, msg, reused=reused, generated=0)
    got = {'n': 0}
    batch = generate.build_batch(pool, missing, client, gen_model, ver_model, rng, scope, lambda a, b: (got.update(n=a), report(progress, reused + a, "new question accepted")),
                                 on_error=lambda k: report(progress, reused + got['n'], f"The AI service is failing or slow ({k} of {generate.MAX_ERRORS} failures before preparation stops)"),
                                 avoid=[i["lead_in"] for i in chosen] + [i["lead_in"] for i in store.list_items("rejected", 50)],
                                 used={pid for i in chosen + store.list_items("rejected", 200) for pid in i["evidence"]}, known=chosen)      # passages already asked about come last
    store.save_items(batch.items)                           # every accepted item is kept: for reuse, and for the professor
    stages = {}
    for r in batch.rejected:
        stages[r["stage"]] = stages.get(r["stage"], 0) + 1
    chosen = chosen + batch.items
    extra = dict(cost_usd=batch.cost_usd, tokens=batch.tokens, reused=reused, generated=len(batch.items), drafts=batch.drafts, calls=batch.calls, gateway_errors=batch.gateway_errors, rejected=batch.rejected[:25],
                 rejected_by_stage=stages, budget_left=batch.budget_left)
    have = len(chosen)
    if have == n:
        return finish("ready", "", chosen, "", **extra)
    reason = failure_reason(batch)
    msg = MESSAGES[reason].format(have=have, n=n, missing=n - have, have_text=(f"{have} question(s) are saved. " if have else ""))
    if n == 10 and have >= 5:
        return finish("offer", reason, chosen, f"{have} of 10 questions are ready. You can start a 5-question quiz now, or continue preparing the other {n - have}.", **extra)
    return finish("partial" if have else "failed", reason, chosen, msg, **extra)


def accept_offer(user, qid, store=None):
    store = store or QuizStore()
    q = store.get_quiz(user, qid)
    if q is None or q["status"] != "offer":
        raise QuizError("There is no quiz waiting for that choice.")
    store.set_status(user, qid, "open")


def decline_offer(user, qid, store=None):
    (store or QuizStore()).delete_quiz(user, qid)


def _open_checked(user, qid, allowed, note_lectures, store):
    q = store.get_quiz(user, qid)
    if q is None:
        raise QuizError("That quiz was not found.")
    its = [store.item(i) for i in q["item_ids"]]
    if any(i is None for i in its):
        raise QuizError("This quiz can no longer be opened.")
    if not all(item_allowed(i, allowed, note_lectures) for i in its):
        raise QuizError("This quiz uses lectures or guides that are no longer open to you. Ask your instructor.")
    return q, its


def open_view(user, qid, allowed, note_lectures=frozenset(), store=None):
    """The OPEN quiz as the student may see it: public questions, saved selections, position. No key, explanation or source."""
    store = store or QuizStore()
    q, its = _open_checked(user, qid, allowed, note_lectures, store)
    if q["status"] != "open":
        raise QuizError("This quiz is not open.")
    return {"quiz_id": qid, "length": q["length"], "current": q["current"], "questions": [items.public_view(i) for i in its],
            "selections": {int(k): v for k, v in q["selections"].items()}, "answered": sum(1 for k, v in q["selections"].items() if v)}


def submit(user, qid, allowed, note_lectures=frozenset(), store=None):
    """Score the WHOLE quiz at once. Unanswered questions count as wrong. -> the results (only now are keys read)."""
    store = store or QuizStore()
    q, its = _open_checked(user, qid, allowed, note_lectures, store)
    if q["status"] != "open":
        raise QuizError("This quiz is not open.")
    total = sum(items.score(it, q["selections"].get(str(k))) for k, it in enumerate(its))
    store.finish(user, qid, total)
    return results(user, qid, allowed, note_lectures, store)


def review_label(review):
    r = review or {"status": "unreviewed"}
    return LABEL[r["status"]].format(by=r.get("by", ""), date=r.get("date", ""))


def results(user, qid, allowed, note_lectures=frozenset(), store=None):
    """Everything about a SUBMITTED quiz. Passage text is shown only for sources the student can still open."""
    store = store or QuizStore()
    q = store.get_quiz(user, qid)
    if q is None:
        raise QuizError("That quiz was not found.")
    if q["status"] != "submitted":
        raise QuizError("Answers and explanations appear after you submit the whole quiz.")
    out = []
    for k, iid in enumerate(q["item_ids"]):
        it = store.item(iid)
        sel = q["selections"].get(str(k)) or []
        texts = {o["id"]: o["text"] for o in it["options"]}
        ev = []
        for p in it["evidence"].values():
            visible = item_allowed({"evidence": {p["id"]: p}}, allowed, note_lectures)
            ev.append({"id": p["id"], "label": p["label"], "tier": TIER_LABEL[p["tier"]], "url": p["url"], "visible": visible,
                       "text": p["text"] if visible else "", "license": p.get("license", "")})
        spans = {"key": it["key_support"], "explanation": it["explanation_support"], "alternatives": {i: a["support"] for i, a in it["alternatives"].items()}}
        out.append({"n": k + 1, "stem": it["stem"], "lead_in": it["lead_in"], "options": it["options"], "selected": sel, "answer_ids": it["answer_ids"],
                    "correct": items.score(it, sel), "explanation": it["explanation"],
                    "alternatives": {i: a["why_wrong"] for i, a in it["alternatives"].items()},
                    "spans": spans, "evidence": ev, "tiers": it["tiers"], "label": review_label(it["review"]), "review_status": it["review"]["status"]})
    return {"quiz_id": qid, "score": q["score"], "length": q["length"], "submitted": q["submitted"], "questions": out}
