"""Where the bank meets the quiz. The ONLY ways a bank question reaches a student:
  * bank_candidates(): status = approved AND use = practice, inside the student's access;
  * AI / web items that were saved to the bank as DRAFT are still served by the quiz's own reuse rule (they are AI-checked, labelled so), unless the instructor retired
    them or made them exam_secure; instructor / imported items are never served through that path (ai_item_ok).
Exam-secure questions are never served and are used to throw away AI questions that are too close to them."""
import re
import time

from src.qbank import checks
from src.qbank.store import BankStore, text_hash
from src.quiz import items as quiz_items

SERVED = ("approved",)


def servable(q):
    d = q["data"]
    return d["status"] == "approved" and d["use"] == "practice"


def to_quiz_item(q):
    """A bank question as a frozen quiz item. Its id carries the bank id and version, so an edited question is a new quiz item and statistics never mix versions."""
    d = q["data"]
    opts = [{"id": o["id"], "text": o["text"]} for o in d["options"]]
    return {"item_id": f"bank:{q['id']}:v{q['version']}", "selection_mode": "single", "stem": d["stem"], "lead_in": d["lead_in"], "options": opts, "answer_ids": [d["answer"]],
            "explanation": d["explanation"] or "No explanation was written for this question.", "key_support": [], "explanation_support": [], "alternatives": {}, "objective": d["objective"],
            "evidence": {}, "tiers": ["instructor"], "scope": {}, "checks": {}, "review": {"status": "approved", "by": "your instructor", "date": time.strftime("%Y-%m-%d", time.localtime(q["updated"]))},
            "created": q["updated"], "version": quiz_items.QUIZ_VERSION, "bank_id": q["id"]}


def in_access(d, allowed):
    """allowed None = unrestricted (an instructor). Otherwise the question's lecture or guide must be one the student may open."""
    if allowed is None:
        return True
    names = [x for x in (d["lecture"], d["guide"]) if x]
    return bool(names) and all(n in set(allowed) for n in names)


def matches_request(d, request):
    if request["mode"] == "materials":
        sel = set(request.get("selected") or [])
        return any(n in sel for n in (d["lecture"], d["guide"]) if n)
    topic = {w for w in quiz_items.words(request.get("topic", "")) if len(w) > 3}
    hay = quiz_items.norm(" ".join([d["stem"], d["lead_in"], d["objective"], d["section"], d["lecture"], " ".join(d["tags"])]))
    return bool(topic) and all(w in hay for w in topic)


def bank_candidates(request, allowed, bank=None, quiz_store=None):
    """Approved practice questions that fit this request and this student. Saved into the quiz store as frozen items (keyed by id + version)."""
    bank = bank or BankStore()
    out = []
    for q in bank.all():
        if q["quiz_item_id"]:                    # an AI / web question keeps its own frozen item (with its evidence): it is served by the quiz's reuse rule, gated by ai_item_ok
            continue
        if servable(q) and in_access(q["data"], allowed) and matches_request(q["data"], request):
            out.append(to_quiz_item(q))
    if quiz_store is not None and out:
        quiz_store.save_items(out)
        for it in out:                           # the stored review marks it as approved by the instructor (what the student's label says)
            quiz_store.set_review(it["item_id"], "approved", it["review"]["by"], date=it["review"]["date"])
    return out


def ai_item_ok(item, reviewed_only, bank=None):
    """May this SAVED quiz item (AI or web) be reused right now, according to the bank?"""
    bank = bank or BankStore()
    if item.get("bank_id"):                      # an instructor's question frozen as a quiz item: only through bank_candidates (it is re-checked there, with its CURRENT status)
        return False
    row = bank.by_quiz_item(item["item_id"])
    if row is None:
        return True
    d = row["data"]
    if d["source"] in ("instructor", "imported") or d["status"] == "retired" or d["use"] == "exam_secure":
        return False
    if reviewed_only:
        return d["status"] == "approved" and d["use"] == "practice"
    return True


def style_examples(request, allowed, bank=None, k=3):
    """One-line renderings of up to k approved practice questions in this scope, so new questions copy the instructor's format, length and difficulty (never his facts)."""
    bank = bank or BankStore()
    out = []
    for q in bank.all():
        d = q["data"]
        if servable(q) and in_access(d, allowed) and (matches_request(d, request) or request["mode"] == "topic") and len(out) < k:
            opts = "; ".join(f"{o['id']}. {o['text']}" for o in d["options"])
            out.append(f"{(d['stem'] + ' ') if d['stem'] else ''}{d['lead_in']} Options: {opts}. Difficulty: {d['difficulty'] or 'unspecified'}.")
    return out


def secure_texts(bank=None):
    bank = bank or BankStore()
    return [checks.text_of(q["data"]) for q in bank.all() if q["data"]["use"] == "exam_secure"]


def save_generated(items, bank=None, searcher=None):
    """New AI / web quiz items are kept in the bank as DRAFT with their source, linked to the lecture and passage they came from. Existing rows are left alone."""
    from app_api import catalog
    bank = bank or BankStore()
    chunks = {c["id"]: c for c in getattr(searcher, "chunks", [])} if searcher is not None else {}
    for it in items:
        if bank.by_quiz_item(it["item_id"]) is not None or it.get("bank_id"):
            continue
        ev = list(it["evidence"].values())
        course = next((p for p in ev if p["tier"] in ("course", "verified")), None)
        web = "web" in it["tiers"]
        links = []
        for p in ev:
            c = chunks.get(p["id"])
            if c is not None and c.get("section_id"):
                links.append(make_link(c, list(chunks.values())))
        lecture = (course or {}).get("lecture", "") if course and course.get("kind") != "dissection_guide" else ""
        guide = (course or {}).get("guide", "") if course and course.get("kind") == "dissection_guide" else ""
        d = {"stem": it["stem"], "lead_in": it["lead_in"], "options": it["options"], "answer": it["answer_ids"][0], "explanation": it["explanation"], "lecture": lecture, "guide": guide,
             "section": (course or {}).get("label", ""), "links": links, "region": catalog.region_of(lecture) if lecture else "", "tags": ["web"] if web else [],
             "source": "web" if web else "ai", "status": "draft", "use": "practice", "objective": it.get("objective", "")}
        try:
            q = bank.create(d, by="ai", note="saved from a quiz", quiz_item_id=it["item_id"])
            bank.replace_flags(q["id"], ("nbme",), checks.nbme_flaws(q["data"]))
        except Exception:
            continue


# ---------------------------------------------------------------- knock-on with the Notes manager
def section_hash(chunks, section_id):
    parts = sorted((c.get("chunk_index", 0), c["text"]) for c in chunks if c.get("section_id") == section_id)
    return text_hash("\n".join(t for _i, t in parts)) if parts else ""


def make_link(chunk, chunks):
    return {"doc_id": chunk.get("doc_id", ""), "section_id": chunk.get("section_id", ""), "breadcrumb": chunk["breadcrumb"], "hash": section_hash(chunks, chunk.get("section_id"))}


def recheck_after_swap(chunks, bank=None):
    """Called after the live notes or guides changed. A question whose cited section is gone or has different text gets "needs re-check". Never changes status or text.
    -> number of questions newly marked."""
    bank = bank or BankStore()
    n = 0
    for q in bank.all():
        reasons = []
        for l in q["data"]["links"]:
            if not l.get("section_id") or not l.get("hash"):
                continue
            now = section_hash(chunks, l["section_id"])
            if not now:
                reasons.append(f"the section it cites is no longer in the notes ({l['breadcrumb']})")
            elif now != l["hash"]:
                reasons.append(f"the section it cites was changed ({l['breadcrumb']})")
        if reasons and not q["recheck"]:
            bank.set_recheck(q["id"], "Notes changed: " + "; ".join(reasons[:2]))
            n += 1
    return n


def clear_recheck(qid, chunks, bank=None, by=""):
    """The instructor looked again: refresh the stored hashes and clear the mark."""
    bank = bank or BankStore()
    q = bank.get(qid)
    links = []
    for l in q["data"]["links"]:
        now = section_hash(chunks, l.get("section_id")) if l.get("section_id") else ""
        links.append({**l, "hash": now or l.get("hash", "")})
    bank.update(qid, {"links": links}, by, "re-checked against the current notes")
    bank.set_recheck(qid, "")


def sync_from_review(item_id, status, by, bank=None):
    """The older per-quiz-item review (Quiz review tab) also decides the bank row of an AI / web question: approved -> approved, rejected -> retired."""
    bank = bank or BankStore()
    row = bank.by_quiz_item(item_id)
    if row is None:
        return
    new = {"approved": "approved", "rejected": "retired"}.get(status)
    if new and row["data"]["source"] in ("ai", "web"):
        bank.update(row["id"], {"status": new}, by, f"quiz review: {status}")
