"""Instructor only (403 for students): dashboard numbers, the review queue, students' questions, access grants, preview-as-student.

Everything here reuses the code the Streamlit professor page uses: src/review.py (queue, decisions through verified.resolve),
src/usage.py (the question log), src/auth.py (grants), src/ingest/guides.py (guide labels). Instructors may see full detail.
"""
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request

from app_api import catalog, config, convert, deps
from app_api.deps import Ctx, FULL
from app_api.errors import ApiError
from app_api.routers import chats
from app_api.schemas import (AccessIn, Ok, PreviewIn, QuestionList, ReviewActionIn, ReviewList, StatsOut, StudentItem, WebQuizPage)
from src import auth, review, usage, verified
from src.quiz import service as quiz_service
from src.quiz.store import QuizStore

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(deps.instructor_ctx)])
KIND_NAME = {"likely_factual": "confirmed_factual", "doubtful": "doubtful", "wording": "wording", "typo": "typo"}
TYPES = ("confirmed_factual", "doubtful", "wording", "typo", "start_here", "student_report")
STATUS_OF = {"confirm_error": "verified", "reword": "verified", "notes_correct": "dismissed"}


def ident(key):
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def since(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def bank_counts():
    from src.qbank import service as bank_service
    try:
        return bank_service.counts_now()
    except Exception:
        return None


# ---- stats ----
@router.get("/stats", response_model=StatsOut)
def stats():
    cutoff = since(7)
    chat = [e for e in usage.read_log() if usage.kind_of(e) == "chat_answer" and e.get("ts", "") >= cutoff]
    items = [i for i in review.queue() if i["decision"]["status"] != "resolved" and (i.get("revision") or {}).get("status") != "changed"]
    counts = {k: sum(1 for i in items if KIND_NAME[i["kind"]] == k) for k in ("confirmed_factual", "doubtful", "wording", "typo")}
    return {"questions_7d": len(chat), "flagged_open": len(verified.list_open()), "web_answers_7d": sum(1 for e in chat if e.get("web")),
            "review_counts": {**counts, "start_here": len([i for i in review.start_here(items)])}, "bank_counts": bank_counts()}


# ---- review queue ----
def item_status(item):
    d = item["decision"]
    if d["status"] == "resolved":
        return STATUS_OF.get(d.get("decision"), "verified")
    return "changed" if (item.get("revision") or {}).get("status") == "changed" else "open"


def review_item(item):
    refs = []
    note = item["issue"] + (f"\nWhat the reference says: {item['what_references_say']}" if item.get("what_references_say") else "")
    section = " › ".join(item.get("section_path") or []) or item["breadcrumb"].split(" > ", 1)[-1]
    refs.append({"n": 1, "type": "notes", "title": "Lecture notes", "subtitle": convert._lecture_label(item["lecture"]) + f" › {section}",
                 "lecture_id": item.get("lecture_id") or catalog.lecture_id_for_title(item["lecture"]), "url": None,
                 "snippet": item["claim_quote"], "retrieved_at": None, "license": None})
    rev = item.get("revision") or {}
    if rev.get("status") == "changed":
        note = ("Changed in the revised notes: the quoted line is no longer there.\n" + (f"New wording: {rev['new_text']}\n" if rev.get("new_text") else "") + note)
        if rev.get("new_text"):
            refs.append({"n": len(refs) + 1, "type": "notes", "title": "Lecture notes (revised)", "subtitle": (rev.get("new_breadcrumb") or rev.get("new_lecture") or "").replace(" > ", " › "),
                         "lecture_id": catalog.lecture_id_for_title(rev.get("new_lecture", "")) or None, "url": None, "snippet": rev["new_text"], "retrieved_at": None, "license": None})
    ref = item.get("reference") or {}
    if item.get("basis") == "openstax" and ref.get("cite"):
        refs.append({"n": 2, "type": "openstax", "title": ref["cite"], "subtitle": " › ".join(ref.get("section_path") or []), "lecture_id": None,
                     "url": ref.get("source_url") or None, "snippet": item.get("reference_quote") or "", "retrieved_at": None,
                     "license": convert.OPENSTAX_LICENSE})
    return {"id": ident(item["key"]), "type": KIND_NAME[item["kind"]], "status": item_status(item), "lecture": item["lecture"],
            "section": section, "original_text": item["claim_quote"], "ai_note": note, "sources": refs}


def report_item(n, f):
    sources = [{"n": i + 1, "type": "web", "title": "Web page", "subtitle": "", "lecture_id": None, "url": u, "snippet": "", "retrieved_at": None,
                "license": None} for i, u in enumerate(f.get("web_urls") or [])]
    note = f"Reported by {f.get('student', '?')}: {f.get('reason', '')}" + (f". {f['comment']}" if f.get("comment") else "") + f"\nQuestion: {f.get('question', '')}"
    return {"id": f"sr-{n}", "type": "student_report", "status": "open" if f.get("status") == "open" else "dismissed", "lecture": "", "section": "",
            "original_text": f.get("answer", ""), "ai_note": note, "sources": sources}


def all_reports():
    return [(n, f) for n, f in enumerate(verified.read_jsonl(verified.FLAGS_PATH), 1) if f.get("type") == "student_report"]


@router.get("/review", response_model=ReviewList)
def review_list(type: str = "", status: str = "", lecture: str = "", page: int = Query(1, ge=1)):
    if type and type not in TYPES:
        raise ApiError(422, "“type” has a value that is not allowed.")
    if status and status not in ("open", "verified", "dismissed", "decided", "changed"):
        raise ApiError(422, "“status” has a value that is not allowed.")
    rows = []
    if type in ("", "student_report"):
        rows += [report_item(n, f) for n, f in reversed(all_reports())]
    if type != "student_report":
        queue = review.queue()
        pool = review.start_here(queue) if type == "start_here" else [i for i in queue if not type or KIND_NAME[i["kind"]] == type]
        rows += [review_item(i) for i in pool]
    if lecture:
        want = {lecture, catalog.lecture_title(lecture)}
        rows = [r for r in rows if r["lecture"] in want]
    if status:
        rows = [r for r in rows if (r["status"] not in ("open", "changed") if status == "decided" else r["status"] == status)]
    start = (page - 1) * config.PAGE_SIZE
    return {"items": rows[start:start + config.PAGE_SIZE], "total": len(rows)}


@router.post("/review/{item_id}", response_model=Ok)
def review_decide(item_id: str, body: ReviewActionIn, ctx: Ctx = Depends(deps.instructor_ctx)):
    """verify = Dr. Inglis confirms the line is wrong (or rewords it) and gives the corrected text, which students then see in its place.
    dismiss = the notes are correct as written. Both go through review.decide -> verified.resolve, like the dashboard. A student report
    can only be dismissed (marked handled)."""
    by = ctx.real["name"]
    if item_id.startswith("sr-"):
        n = int(item_id[3:]) if item_id[3:].isdigit() else 0
        if body.action == "verify":
            raise ApiError(422, "A student report can only be dismissed (marked as handled). Fix the cause in the review queue or the notes.")
        flags = verified.read_jsonl(verified.FLAGS_PATH)
        if not 1 <= n <= len(flags) or flags[n - 1].get("type") != "student_report":
            raise ApiError(404, "That report was not found.")
        if flags[n - 1].get("status") != "open":
            raise ApiError(409, "That report was already handled.")
        review.close_report(n)
        return {"ok": True}
    item = next((i for i in review.queue() if ident(i["key"]) == item_id), None)
    if item is None:
        raise ApiError(404, "That item was not found.")
    if item["decision"]["status"] == "resolved":
        raise ApiError(409, "That item was already decided.")
    if (item.get("revision") or {}).get("status") == "changed":
        raise ApiError(409, "That line changed in the revised notes, so there is nothing left to decide. The new wording is shown with the item.")
    fix = (body.fix_text or "").strip()
    if body.action == "verify":
        if not fix:
            raise ApiError(422, "Type the corrected wording first. It is what students will see.")
        decision = "confirm_error" if item["kind"] in ("likely_factual", "doubtful") else "reword"
    else:
        decision, fix = "notes_correct", ""
    try:
        review.decide(item, decision, fix, by)
    except ValueError as exc:
        raise ApiError(422, str(exc))
    return {"ok": True}


# ---- students' questions ----
def question_kind(e):
    if e.get("status") == "answered" or e.get("status") == "access_limited":
        return "term_lookup" if e.get("answer_mode") == "term" else "answer"
    if e.get("reason") in convert.REFUSED_REASONS:
        return "refused"
    return "error" if e.get("status") in ("error", "capped") else "not_covered"


@router.get("/questions", response_model=QuestionList)
def questions(web: bool | None = None, flagged: bool | None = None, page: int = Query(1, ge=1)):
    reported = {(f.get("student"), f.get("question")) for _, f in all_reports()}
    rows = []
    for e in reversed([e for e in usage.read_log() if usage.kind_of(e) == "chat_answer"]):
        is_web, is_flagged = bool(e.get("web")), (e.get("user"), e.get("question")) in reported
        if (web is not None and is_web != web) or (flagged is not None and is_flagged != flagged):
            continue
        rows.append((e, is_web, is_flagged))
    start = (page - 1) * config.PAGE_SIZE
    out = []
    for e, is_web, is_flagged in rows[start:start + config.PAGE_SIZE]:
        try:
            near = datetime.fromisoformat(e["ts"]).timestamp()
        except (KeyError, ValueError):
            near = None
        found = chats.store().find_answer(e.get("user", ""), e.get("question", ""), near)
        message = convert.assistant_message(found["result"], id=convert.message_id(found["chat_id"], found["seq"]), created=found["created"],
                                            timing_ms=found["timing_ms"]) if found else None
        out.append({"id": ident(f"{e.get('ts')}|{e.get('user')}|{e.get('question')}"), "student": e.get("user", ""), "question": e.get("question", ""),
                    "kind": question_kind(e), "web": is_web, "flagged": is_flagged, "created_at": convert.iso(e.get("ts")), "message": message})
    return {"items": out, "total": len(rows)}


# ---- quizzes built from the web ----
@router.get("/web-quizzes", response_model=WebQuizPage)
def web_quizzes(page: int = Query(1, ge=1)):
    """Every student quiz with at least one question built from Wikipedia (never a preview quiz), newest first."""
    rows = QuizStore().web_quizzes()
    start = (page - 1) * config.PAGE_SIZE
    items = [{"id": r["quiz"]["id"], "student": r["quiz"]["user"], "title": quiz_service.quiz_title(r["quiz"]["scope"]), "status": r["quiz"]["status"],
              "score": r["quiz"]["score"], "length": r["quiz"]["length"], "web_questions": r["web_questions"], "sources": r["sources"],
              "created_at": convert.iso(r["quiz"]["created"])} for r in rows[start:start + config.PAGE_SIZE]]
    return {"items": items, "total": len(rows)}


# ---- students and access ----
def ids_of(titles):
    lecture_ids = [l["id"] for l in catalog.lectures() if l["title"] in titles]
    guide_ids = [g["id"] for g in catalog.guides() if g["label"] in titles]
    return lecture_ids, guide_ids


@router.get("/students", response_model=list[StudentItem])
def students():
    out = []
    for username, rec in auth.students():
        lecture_ids, guide_ids = ids_of(set(rec.get("allowed_lectures", [])))
        out.append({"id": username, "name": rec["name"], "username": username, "lecture_ids": lecture_ids, "guide_ids": guide_ids})
    return out


@router.put("/students/{student_id}/access", response_model=Ok)
def set_access(student_id: str, body: AccessIn):
    if student_id not in {u for u, _ in auth.students()}:
        raise ApiError(404, "That student was not found.")
    titles = []
    for lid in body.lecture_ids:
        t = catalog.lecture_title(lid)
        if t is None:
            raise ApiError(422, "One of the lectures does not exist.")
        titles.append(t)
    for gid in body.guide_ids:
        g = catalog.guide_by_id(gid)
        if g is None:
            raise ApiError(422, "One of the guides does not exist.")
        titles.append(g["label"])
    auth.set_allowed_lectures(student_id, titles)
    return {"ok": True}


# ---- preview as a student ----
@router.post("/preview", response_model=Ok)
def preview_start(body: PreviewIn, ctx: Ctx = Depends(deps.instructor_ctx)):
    """profile: "full" (a student who may use every lecture) or a student's id. Until /preview/exit, the student tools act as that student
    and nothing is saved as theirs."""
    profile = body.profile.strip()
    if profile != FULL and profile not in {u for u, _ in auth.students()}:
        raise ApiError(404, "That student was not found.")
    ctx.sessions.set_preview(ctx.token, {"profile": profile})
    return {"ok": True}


@router.post("/preview/exit", response_model=Ok)
def preview_exit(request: Request, ctx: Ctx = Depends(deps.instructor_ctx)):
    ctx.sessions.set_preview(ctx.token, None)
    if getattr(request.app.state, "preview_chats", None):
        request.app.state.preview_chats.pop(ctx.token, None)
    return {"ok": True}
