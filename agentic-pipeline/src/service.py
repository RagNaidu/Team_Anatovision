"""The UI-facing layer over the existing code: structured results, no printing, no input().

ask(question, body_type, brief, allowed_lectures, runtime=...) -> dict
    status          answered | not_found | out_of_scope | access_limited | capped | error
    answer_text     what to show (markdown)
    units, citations  the answer split into sentences with numbered citation chips (see src/citations.py)
    retrieved_chunks  [{breadcrumb, source_type, text, score, cosine, cite, ...}]  empty for not_found / out_of_scope
    events          REAL pipeline events recorded by the code as each step ran (search, thresholds, fact-check lookup,
                    verified-fix lookup, model call, output guards, citation check). Nothing is reconstructed afterwards.
    tokens, cost, flags_hit, verified_fix_used, basis, notes

`ask()` returns the FULL (instructor-side) result. Students never receive it: `ask_for_student()` hands the student views only
`src/student_view.build(...)` plus the cost/tokens the app needs for its own bookkeeping.

Access control lives in the search (qa.answer_question -> Searcher.search(allowed_lectures=...)): notes of lectures the
user may not use never reach this function's caller or the model. audience="student" also strips fact-check detail
(verifier reasons, original wording, severity) from flags_hit; "professor" keeps it.
"""
import functools
import os
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from src import citations as cit
from src import llm
from src import query as qry
from src import sources as src_kinds
from src import term_lookup, web_fallback, web_sources
from src import student_view
from src import usage as usage_log
from src import verified
from src.modes import qa
from src.retrieval.search import Hit, Searcher

ROOT = Path(__file__).resolve().parents[1]
MAX_QUESTION_CHARS = 600
CAP_MSG = ("This session has reached its spending cap, so I have stopped calling the model. "
           "Ask your instructor to raise the cap, or start a new session.")
NOT_FOUND_MSG = ("I couldn't find that in Dr. Inglis's lecture notes or in the OpenStax textbook, so I won't answer it "
                 "from memory.")
NOT_ANATOMY_MSG = ("That doesn't look like a question about anatomy or the lab, so I can't help with it here. "
                   "Ask about a structure, a region or a step from the lectures.")
CLINICAL_MSG = ("This tool covers structure and function from the course material, not clinical advice such as treatment, "
                "medication or diagnosis, so it can't answer that here.")
WEB_LABEL = "From the web, not in Dr. Inglis's notes or OpenStax. Check with your instructor."
WIKI_LABEL = "From Wikipedia, not in Dr. Inglis's notes or OpenStax. Check with your instructor."
MAX_ACCESS_TITLES = 2


def access_message(titles):
    """The student's grant does not include the lecture the answer would come from. Names it (title only)."""
    names = " or ".join(titles[:MAX_ACCESS_TITLES]) if titles else "the lecture it is in"
    return f"The notes for this are in {names}, which you don't have access to. Ask Dr. Inglis to open it for you."


def access_note(titles):
    """The short last line under an answer that was written without the student's own lecture."""
    names = " or ".join(t.split(" - ")[0] for t in titles[:MAX_ACCESS_TITLES]) if titles else "a lecture"
    return f"Dr. Inglis's notes for this are in {names}, which you don't have yet. Ask him to open it."


def too_long_message(n):
    return f"That question is {n:,} characters long. The limit is {MAX_QUESTION_CHARS}. Please shorten it and ask again."


@dataclass
class Runtime:
    searcher: object
    next_of: dict
    client: object
    model: str
    rewrite_model: str = ""          # small model for follow-up rewriting and the off-topic check ("" = src/query.py default)
    web_lookup: object = None        # tests replace this; None = src.web_fallback.lookup


def build_runtime(warm=True):
    """Load the index, the embedding model and the API client once. The key is read from .env and never printed."""
    load_dotenv(ROOT / ".env")
    searcher = Searcher()
    if warm:
        searcher.search("warm up")           # loads the embedding model now, not on the first question
    return Runtime(searcher=searcher, next_of=qa.next_sections(searcher), client=llm.make_client(),
                   model=llm.default_model(), rewrite_model=llm.rewrite_model())


def cost_for(usage, model):
    c = qa.cost_of(usage, model)
    return 0.0 if c is None else c


def _empty(question, status, text, events, **extra):
    return {"question": question, "status": status, "answer_text": text, "units": [], "citations": [],
            "n_unmatched": 0, "retrieved_chunks": [], "events": list(events),
            "tokens": {"input": 0, "output": 0}, "cost": 0.0, "flags_hit": [], "verified_fix_used": [],
            "basis": "not_covered", "notes": [], "access_limited": False, **extra}


def _chunk_view(h, sid, marks, hit_texts):
    c = h.chunk
    return {"sid": sid, "id": c["id"], "breadcrumb": qa.plain(c["breadcrumb"]), "lecture": c["lecture"],
            "source_type": c["source_type"], "text": hit_texts.get(sid, c["text"]), "score": round(h.score, 4),
            "cosine": round(h.cosine, 3), "cite": qa.cite_for(c), "section_number": c.get("section_number", ""),
            "source_url": c.get("source_url", ""), "uploaded": c.get("uploaded", ""),
            "title": c.get("title", ""), "site": c.get("site", ""), "retrieved": c.get("retrieved", ""), "license": c.get("license", ""),
            "class_number": c.get("class_number", ""), "slide": c.get("slide", ""),
            "marks": [{"kind": k, "id": mid} for k, mid, s, obj in marks if s == sid]}


def _fix_view(fix, marker=""):
    return {"id": fix["id"], "marker": marker, "decision": fix["decision"], "by": fix["by"], "date": fix["date"],
            "correction": fix["correction"], "lecture": fix["lecture"], "breadcrumb": qa.plain(fix["breadcrumb"]),
            "citation": f"[{verified.citation(fix)}]"}


def _flag_views(out, audience):
    ans, views = out.get("answered_ids", {"review": [], "doubtful": []}), []
    for kind, mid, sid, obj in out["marks"]:
        label = {"review": "under_review", "doubtful": "doubtful"}.get(kind)
        if not label or mid not in ans.get(kind, []):
            continue
        view = {"kind": label, "id": mid, "breadcrumb": qa.plain(obj["breadcrumb"]), "statement": obj["issue"]}
        if audience == "professor":
            view.update(quote=obj["claim_quote"], severity=obj["severity"], confidence=obj.get("confidence"),
                        reason=obj.get("verification", {}).get("reason", ""))
        views.append(view)
    return views


def _add_usage(total, extra):
    return {k: total[k] + extra.get(k, 0) for k in total}


def _zero():
    return {"input_tokens": 0, "output_tokens": 0}


def web_chunk(p):
    """A fetched web passage as a chunk the answer pipeline can cite (see src/web_fallback.py)."""
    return {"id": p["id"], "source_type": "web", "priority": 4, "lecture": p["site"], "title": p["title"], "site": p["site"],
            "breadcrumb": f"Web > {p['site']} > {p['title']}", "section_path": [p["title"]], "text": p["text"],
            "source_url": p["url"], "retrieved": p["retrieved"], "license": p.get("license", ""), "section_number": "", "uploaded": ""}


def web_hits(passages):
    return [Hit(web_chunk(p), 1.0 - 0.01 * i, 0.0, 0.0, 0.0, None, None) for i, p in enumerate(passages)]


def is_term_question(dec):
    """A bare term (term lookup, or the ordinary answer to a term found in one place): the coverage check does not apply."""
    return dec.use in ("term", "term_if_missing")


def ask(question, body_type="", brief=True, allowed_lectures=None, *, runtime, ctx=None, audience="student",
        session_cost=0.0, cap=None, user="", log=True, history=None, instructor_detail=False, kind="chat_answer",
        as_user=""):
    """The full result. audience picks the model's wording ("student": no fact-check detail in the answer text) and, with
    "professor" or instructor_detail=True, keeps the fact-check detail in flags_hit.
    history: earlier turns [{"question", "answer"}] (see src/query.py), used to understand follow-ups, never as a source.
    kind / as_user: how the question is logged (chat_answer | professor_preview; as_user = the student being previewed).

    Source order: verified fix > notes + dissection guides > OpenStax > trusted web. A bare term ("apex") gets a TERM LOOKUP
    (the places it appears) instead of the 0.68 rule; the web is asked ONLY when every other source found nothing and the
    question is a clear anatomy question (never clinical advice, never off-topic)."""
    question = (question or "").strip()
    events = qa.EventLog()
    if not question:
        return _empty(question, "error", "Type a question first.", events)
    if len(question) > MAX_QUESTION_CHARS:
        return _empty(question, "error", too_long_message(len(question)), events, reason="too_long")
    if cap is not None and session_cost >= cap:
        events.add("cap", "Spending cap reached: no model call made", session_cost=round(session_cost, 4), cap=cap)
        return _empty(question, "capped", CAP_MSG, events)

    allowed = None if allowed_lectures is None else sorted(set(allowed_lectures))
    if allowed is not None:
        events.add("access", f"Search limited to {len(allowed)} lecture(s) this user may use", n_lectures=len(allowed))
    ctx = ctx if ctx is not None else qa.load_context()
    extra = _zero()          # small helper calls (follow-up rewrite, scope check) and answers that were replaced by a later tier
    rewrite_model = runtime.rewrite_model or runtime.model

    history = list(history or [])[-qry.MAX_TURNS:]
    search_query, how = question, "unchanged"
    if history:
        t0 = time.perf_counter()
        search_query, u, how = qry.rewrite_query(runtime.client, question, history, rewrite_model)
        extra = _add_usage(extra, u)
        events.add("followup", "Follow-up resolved from the last turns before searching", how=how,
                   turns_used=len(history), search_query=search_query, seconds=round(time.perf_counter() - t0, 2))
    list_mode = qry.is_list_question(question)
    procedural = qry.is_procedural_question(search_query) and not list_mode
    k = qry.LIST_K if list_mode else qry.PROC_K if procedural else None
    if list_mode:
        events.add("list_question", f"List question: retrieving up to {qry.LIST_K} passages instead of 5", k=qry.LIST_K)
    if procedural:
        events.add("procedural_question", f"'How do I' question: retrieving up to {qry.PROC_K} passages and answering as ordered steps",
                   k=qry.PROC_K)

    dec = term_lookup.Decision()
    if not list_mode:
        dec = term_lookup.decide(runtime.searcher, search_query, allowed)
        if dec.n_groups or dec.use != "normal":
            events.add("term_check", "Short term: looked for the word itself in the notes, guides and textbook", use=dec.use,
                       n_places=dec.n_groups, words=dec.words, why=dec.why)

    cov = {}                    # what the coverage check did (see pre_answer)

    def pre_answer(result):
        """After retrieval, when the answer would rest on OpenStax alone (nothing from Dr. Inglis's notes or guides, nothing from the
        term lookup or a guide's steps): does the text answer every part? If parts are missing, fetch Wikipedia for them and hand the
        model both, plus the parts that may stay unanswered. -> (hits to use or None, gap lines)."""
        nonlocal extra
        hits_ = result.hits
        if not hits_ or any(h.chunk["source_type"] != "open_text" for h in hits_):
            return None, []
        if not (web_sources.web_fallback_on() and any(x["id"] == "wikipedia" for x in web_sources.enabled_sites())):
            return None, []
        t0 = time.perf_counter()
        covered, missing, u, sure = qry.coverage_check(runtime.client, question, [h.chunk["text"] for h in hits_], rewrite_model)
        extra = _add_usage(extra, u)
        cov.update(checked=True, covered=covered, missing=missing, seconds=0.0)
        events.add("coverage_check", "OpenStax-only answer: checked that the textbook text answers every part of the question",
                   covered=covered, missing=missing, sure=sure, seconds=round(time.perf_counter() - t0, 2))
        if covered:
            return None, []
        lookup = runtime.web_lookup or functools.partial(web_fallback.lookup, sources=("wikipedia",), loose=True)
        wr = lookup(search_query)
        events.add("web_lookup", "Wikipedia fetched for the parts the textbook does not answer", n_passages=len(wr.passages),
                   cached=wr.cached, seconds=wr.seconds, error=wr.error, sites=sorted({p["site"] for p in wr.passages}), missing=missing)
        cov.update(passages=wr.passages, web_seconds=wr.seconds)
        parts = "; ".join(missing)
        if wr.passages:
            return list(hits_) + web_hits(wr.passages), [
                f"The textbook passages do not answer: {parts}. A Wikipedia page is included for these parts: use it only for what it states, "
                "keep each source's own citation, and if neither source states a part, say so in one plain sentence."]
        return None, [f"No source I can use answers: {parts}. Say so in one plain sentence inside the answer and do not state those parts."]

    def call(mode="normal", forced=None):
        extra_kw = {} if mode == "normal" else {"forced_hits": forced, "mode": mode}
        if mode == "normal" and not procedural and not is_term_question(dec):
            extra_kw["pre_answer"] = pre_answer
        if procedural:
            extra_kw["procedural"] = True
        return qa.answer_question(runtime.searcher, runtime.client, runtime.model, question, body_type, ctx,
                                  runtime.next_of, brief=brief, events=events, allowed_lectures=allowed,
                                  search_query=search_query if search_query != question else None,
                                  history=history or None, k=k, list_mode=list_mode, audience=audience, **extra_kw)

    def failed(exc):
        events.add("error", "The model call failed", error=type(exc).__name__)
        if isinstance(exc, llm.EmptyAnswer):
            return _empty(question, "error", llm.EMPTY_MESSAGE, events, reason="empty_answer")
        return _empty(question, "error", f"Sorry, I could not answer that just now ({type(exc).__name__}). "
                                         "Please try again.", events)

    mode = "term" if dec.use == "term" else "normal"
    try:
        out = call(mode, dec.hits if mode == "term" else None)
        if dec.use == "term_if_missing" and not out["result"].found:         # a lone place: only if the ordinary answer found nothing
            mode = "term"
            out = call("term", dec.hits)
    except (llm.LLMError, RuntimeError) as exc:
        return failed(exc)

    result = out["result"]
    hits = result.hits if result.found else []
    decline = out.get("decline_reason", "")
    declined = result.found and out["basis"] == "not_covered"
    has_notes = any(src_kinds.is_course(h.chunk) for h in hits)

    # Does the topic exist in notes this user may not open? (only asked when the allowed notes gave nothing to answer with)
    access_titles = []
    if allowed is not None and not has_notes and not (declined and decline in ("clinical_advice", "not_anatomy")):
        t0 = time.perf_counter()
        access_titles = list(runtime.searcher.outside_titles(search_query, allowed))      # local, title-only: no text, no reranker, no model
        events.add("access_check", "Checked, on this machine only, whether relevant notes exist outside the allowed lectures "
                   "(only lecture titles were kept; no text of them was read by a model or reranker)", outside_notes_found=bool(access_titles),
                   seconds=round(time.perf_counter() - t0, 2))
    access_limited = bool(access_titles)

    scope = {}

    def get_scope():
        nonlocal extra
        if not scope:
            label, u, sure = qry.scope_check(runtime.client, question, rewrite_model)
            scope.update(label=label, sure=sure)
            extra = _add_usage(extra, u)
            events.add("topic_check", "Nothing relevant found: checked whether this is an anatomy question",
                       scope=label, is_anatomy=label == "anatomy", sure=sure)
        return scope

    # The web is the LAST tier: only when notes, guides and OpenStax found nothing (or the model found nothing usable in what
    # was found), nobody's access is the reason, and the question is clearly about anatomy.
    web_used = None
    nothing = (not result.found) or (declined and decline in ("", "not_in_sources"))
    if nothing and mode == "normal" and not access_limited and web_sources.web_fallback_on():
        sc = get_scope()
        if sc["label"] == "anatomy" and sc["sure"]:
            lookup = runtime.web_lookup or web_fallback.lookup
            wr = lookup(search_query)
            events.add("web_lookup", "Trusted web sites searched (last tier: nothing else covered this)",
                       n_passages=len(wr.passages), cached=wr.cached, seconds=wr.seconds, error=wr.error,
                       sites=sorted({p["site"] for p in wr.passages}), keywords=wr.keywords)
            if wr.passages:
                try:
                    web_out = call("web", web_hits(wr.passages))
                except (llm.LLMError, RuntimeError):
                    web_out = None
                if web_out is not None:
                    covered = web_out["basis"] != "not_covered" and web_out["result"].found
                    events.add("web_answer", "Web passages used" if covered else "The web passages did not cover it: not covered",
                               covered=covered)
                    if covered:
                        extra = _add_usage(extra, out["usage"] or _zero())
                        out, result, mode, web_used = web_out, web_out["result"], "web", wr
                        hits, declined, decline = result.hits, False, ""
                    else:
                        extra = _add_usage(extra, web_out["usage"] or _zero())

    reason = ""
    if not result.found or declined:
        if access_limited:
            reason = "outside_access"
        elif declined and decline == "not_anatomy":
            reason = "not_anatomy"
        elif declined and decline == "clinical_advice":
            reason = "clinical_advice"
        elif declined and decline == "":
            reason = "declined"                       # the model declined without saying why: keep its own words
        elif declined:
            reason = "nothing_relevant"
        else:
            sc = get_scope()
            reason = {"anatomy": "nothing_relevant", "clinical_advice": "clinical_advice", "not_anatomy": "not_anatomy"}[sc["label"]]

    main_usage = out["usage"] or _zero()
    tokens = _add_usage(main_usage, extra)
    cost = cost_for(out["usage"], runtime.model) + cost_for(extra, rewrite_model)
    base = {"question": question, "tokens": {"input": tokens["input_tokens"], "output": tokens["output_tokens"]},
            "cost": cost, "basis": out.get("basis", "not_covered"), "notes": out["notes"], "access_limited": access_limited,
            "model": runtime.model, "reason": reason, "list_mode": list_mode, "search_query": search_query,
            "followup": how, "history_turns": len(history), "procedural": procedural, "n_retrieved": len(hits),
            "access_lectures": access_titles, "list_note_added": bool(out.get("list_note_added")),
            "mode": mode, "web": mode == "web" or bool(cov.get("passages")), "web_label": WEB_LABEL if mode == "web" else "",
            "web_urls": [p["url"] for p in web_used.passages] if web_used else [p["url"] for p in cov.get("passages", [])],
            "web_seconds": web_used.seconds if web_used else cov.get("web_seconds", 0.0), "coverage": dict(cov, passages=len(cov.get("passages", []))), "term_places": dec.n_groups if mode == "term" else 0,
            "tier": "none"}

    if not result.found or declined:
        status = "access_limited" if access_limited else "not_found" if not result.found else "out_of_scope"
        text = {"outside_access": access_message(access_titles), "not_anatomy": NOT_ANATOMY_MSG,
                "nothing_relevant": NOT_FOUND_MSG}.get(reason, out["answer"])
        if reason == "clinical_advice" and not result.found:
            text = CLINICAL_MSG                          # nothing was retrieved, so the model never answered: our own words
        res = {**_empty(question, status, text, events), **base}
        res["events"] = list(events)
        _log(log, user, question, res, [], kind, as_user)
        return res

    marks, sources = out["marks"], {f"S{n}": h for n, h in enumerate(result.hits, 1)}
    chunks = [_chunk_view(h, sid, marks, out["source_texts"]) for sid, h in sources.items()]
    fixes = [_fix_view(fix, mid) for mid, fix in out["verified"]]
    verified_marks = [_fix_view(obj, mid) for k_, mid, sid, obj in marks if k_ == "verified"]
    parsed = cit.parse_answer(out["answer"], chunks, fixes)
    events.add("citation_check", "Citations checked against the retrieved passages",
               n_citations=len(parsed["citations"]), n_matched=len(parsed["citations"]) - parsed["n_unmatched"],
               not_found=[c["cite"] for c in parsed["citations"] if not c["matched"]])
    cited = [chunks[c["chunk"]] for c in parsed["citations"] if c["chunk"] is not None]
    if mode == "web":                                   # the label names the site the cited text came from
        base["web_label"] = WIKI_LABEL if any(c.get("site") == "Wikipedia" for c in cited) else WEB_LABEL
    base["tier"] = ("verified" if fixes else "term" if mode == "term" else src_kinds.tier_of(cited))
    res = {**base, "status": "access_limited" if access_limited else "answered", "answer_text": out["answer"],
           "access_notice": access_note(access_titles) if access_limited else "",
           "units": parsed["units"], "citations": parsed["citations"], "n_unmatched": parsed["n_unmatched"],
           "retrieved_chunks": chunks, "events": list(events),
           "flags_hit": _flag_views(out, "professor" if instructor_detail else audience), "verified_fix_used": fixes,
           "verified_marks": verified_marks}
    _log(log, user, question, res, [c["lecture"] for c in chunks if c["source_type"] in src_kinds.COURSE_TYPES and c["lecture"]],
         kind, as_user)
    return res


def ask_for_student(question, body_type="", brief=True, allowed_lectures=None, *, runtime, keep_instructor=False, **kw):
    """ask() for a student session. -> {"view": student_view.build(...), "cost", "tokens", "instructor": full result | None}.

    The student views get only "view". The full result is returned in "instructor" only when keep_instructor is set (a
    professor previewing as a student); a real student session never keeps it."""
    raw = ask(question, body_type, brief, allowed_lectures, runtime=runtime, audience="student",
              instructor_detail=keep_instructor, **kw)
    return {"view": student_view.build(raw), "cost": raw["cost"], "tokens": raw["tokens"],
            "instructor": raw if keep_instructor else None}


def _log(log, user, question, res, lectures, kind="chat_answer", as_user=""):
    if not log:
        return
    answered = res["status"] == "answered" and res["basis"] in ("course_notes", "both")
    entry = {"mode": "qa", "kind": kind, "user": user, "question": question, "status": res["status"],
             "reason": res.get("reason", ""), "basis": res["basis"], "answered_from_notes": answered,
             "lectures": list(dict.fromkeys(lectures)), "cost": res["cost"], "tokens": res["tokens"],
             "answer_mode": res.get("mode", "normal"), "tier": res.get("tier", "none")}
    if res.get("web"):
        entry.update(web=True, web_urls=list(res.get("web_urls", [])))
    if as_user:
        entry["as_user"] = as_user
    usage_log.log_event(entry)
