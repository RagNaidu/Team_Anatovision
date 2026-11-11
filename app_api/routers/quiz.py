"""Quiz: build as a background job, take it, submit, read the results. Wraps src/quiz/service.py (and QuizStore for saving answers).

The key, the explanations and the evidence are read only by service.results after submit. Nothing here reads them earlier: the open quiz
comes from service.open_view (question text and options only). Access is re-checked on every call that opens a quiz.
"""
import threading
import time
import uuid

from fastapi import APIRouter, Depends, Request

from app_api import catalog, config, convert, deps
from app_api.deps import Ctx
from app_api.errors import ApiError
from app_api.schemas import (AnswerIn, AnsweredOut, BuildIn, CurrentIn, HistoryItem, JobOut, JobStatus, LatestQuiz, Ok, OpenQuiz, Results)
from src.quiz import service as qs
from src.quiz.store import QuizError, QuizStore

router = APIRouter(prefix="/quiz", tags=["quiz"])
JOB_KEEP_SECONDS = 3600


def quiz_status(exc):
    """QuizError carries only a message for the student; the status code follows from which message it is."""
    m = str(exc).lower()
    if "not found" in m or "no such question" in m:
        return 404
    if "no longer" in m:
        return 403
    if "not open" in m or "after you submit" in m or "no quiz waiting" in m:
        return 409
    return 400


def quiz_error(exc):
    return ApiError(quiz_status(exc), str(exc))


def note_lectures(rt):
    return getattr(rt.searcher, "note_lectures", frozenset())


# ---- the job table (in memory: a server restart forgets running builds; saved questions are in the quiz database) ----
class Jobs:
    def __init__(self):
        self.lock, self.items = threading.Lock(), {}

    def start(self, owner, request, work):
        with self.lock:
            now = time.time()
            for k in [k for k, j in self.items.items() if now - j["created"] > JOB_KEEP_SECONDS]:
                del self.items[k]
            if any(j["owner"] == owner and not j["done"] for j in self.items.values()):
                raise ApiError(409, "A quiz is already being prepared. Wait for it to finish.")
            jid = uuid.uuid4().hex[:16]
            job = self.items[jid] = {"owner": owner, "created": now, "done": False, "have": 0, "requested": request["n"],
                                     "note": "Looking for saved questions that were already checked", "result": None}
        threading.Thread(target=self._run, args=(job, work), daemon=True, name=f"quiz-build-{jid}").start()
        return jid

    def _run(self, job, work):
        def progress(have, wanted, note=""):
            job.update(have=have, requested=wanted, note=note or job["note"])
        try:
            out = work(progress)
        except QuizError as exc:
            out = {"status": "failed", "reason": "", "message": str(exc), "quiz_id": None, "have": 0, "requested": job["requested"]}
        except Exception:
            out = {"status": "failed", "reason": "gateway", "quiz_id": None, "have": 0, "requested": job["requested"],
                   "message": "Quiz preparation hit an unexpected problem. Nothing is wrong with your material. Try again."}
        job["result"] = {"status": out["status"], "reason": out.get("reason") or "", "quiz_id": out.get("quiz_id"),
                         "have": out.get("have", out.get("passed", 0)), "requested": out.get("requested", job["requested"]),
                         "message": out.get("message") or ""}
        job.update(have=job["result"]["have"], requested=job["result"]["requested"], done=True)

    def get(self, owner, jid):
        with self.lock:
            job = self.items.get(jid)
        if job is None or job["owner"] != owner:
            raise ApiError(404, "That quiz job was not found.")
        return {"done": job["done"], "have": job["have"], "requested": job["requested"], "note": job["note"], "result": job["result"]}


def jobs(request: Request) -> Jobs:
    if getattr(request.app.state, "quiz_jobs", None) is None:
        request.app.state.quiz_jobs = Jobs()
    return request.app.state.quiz_jobs


def selected_titles(ctx, body):
    """Lecture ids and guide ids -> the keys the quiz service uses (lecture title, or 'Dissection Guide, Class N'). Must be open to the user."""
    allowed, selected = set(ctx.allowed), []
    for lid in body.lecture_ids or []:
        title = catalog.lecture_title(lid)
        if title is None:
            raise ApiError(422, "One of the lectures you picked does not exist.")
        if title not in allowed:
            raise ApiError(403, "One of the lectures you picked is not open to you. Ask your instructor.")
        selected.append(title)
    open_files = catalog.open_guides(ctx.allowed)
    for gid in body.guide_ids or []:
        g = catalog.guide_by_id(gid)
        if g is None:
            raise ApiError(422, "One of the guides you picked does not exist.")
        if g["file"] not in open_files:
            raise ApiError(403, "One of the guides you picked is not open to you. Ask your instructor.")
        selected.append(g["label"])
    return selected


@router.post("/build", response_model=JobOut)
def build(body: BuildIn, request: Request, ctx: Ctx = Depends(deps.student_ctx), rt=Depends(deps.runtime), j: Jobs = Depends(jobs)):
    req = {"mode": body.mode, "n": body.n, "reviewed_only": body.reviewed_only, "different_style": body.different_style}
    if body.mode == "materials":
        req["selected"] = selected_titles(ctx, body)
        if not req["selected"]:
            raise ApiError(422, "Choose at least one lecture or guide.")
    else:
        req["topic"] = (body.topic or "").strip()
        if len(req["topic"]) < 3:
            raise ApiError(422, "Type a topic of at least 3 characters.")
        if len(req["topic"]) > config.MAX_TOPIC:
            raise ApiError(422, f"The topic can be up to {config.MAX_TOPIC} characters.")
    owner, allowed = ctx.owner, list(ctx.allowed)
    store = QuizStore()
    if body.continue_quiz_id:                         # "Continue preparing" after a 5-question offer: drop the offer, look for the rest
        q = store.get_quiz(owner, body.continue_quiz_id)
        if q is None or q["status"] != "offer":
            raise ApiError(404, "That quiz is not waiting for a choice.")

    def work(progress):
        if body.continue_quiz_id:
            qs.decline_offer(owner, body.continue_quiz_id)
        return qs.new_quiz(owner, allowed, req, rt, progress=progress)
    return {"job_id": j.start(owner, req, work)}


@router.get("/jobs/{job_id}", response_model=JobStatus)
def job(job_id: str, ctx: Ctx = Depends(deps.student_ctx), j: Jobs = Depends(jobs)):
    return j.get(ctx.owner, job_id)


@router.get("/latest", response_model=LatestQuiz | None)
def latest(ctx: Ctx = Depends(deps.student_ctx)):
    q = QuizStore().latest(ctx.owner, ("open", "offer"))
    if q is None:
        return None
    return {"id": q["id"], "status": q["status"], "length": q["length"], "answered": sum(1 for v in q["selections"].values() if v)}


@router.get("/history", response_model=list[HistoryItem])
def history(ctx: Ctx = Depends(deps.student_ctx)):
    store = QuizStore()
    out = []
    for q in store.list_quizzes(ctx.owner, "submitted", 50):
        web = any("web" in (store.item(i) or {"tiers": []})["tiers"] for i in q["item_ids"])
        out.append({"id": q["id"], "score": q["score"], "length": q["length"], "submitted": convert.iso(q["submitted"]),
                    "title": qs.quiz_title(q["scope"]), "web": web})
    return out


@router.delete("/history/{quiz_id}", response_model=Ok)
def delete_history(quiz_id: str, ctx: Ctx = Depends(deps.student_ctx)):
    """Remove one finished quiz from the student's own history. Another student's quiz is a 404, never a 403."""
    if not QuizStore().delete_submitted(ctx.owner, quiz_id):
        raise ApiError(404, "That quiz was not found.")
    return {"ok": True}


@router.post("/{quiz_id}/accept", response_model=Ok)
def accept(quiz_id: str, ctx: Ctx = Depends(deps.student_ctx), rt=Depends(deps.runtime)):
    store = QuizStore()
    try:
        qs._open_checked(ctx.owner, quiz_id, ctx.allowed, note_lectures(rt), store)
        qs.accept_offer(ctx.owner, quiz_id, store)
    except QuizError as exc:
        raise quiz_error(exc)
    return {"ok": True}


@router.delete("/{quiz_id}", response_model=Ok)
def discard(quiz_id: str, ctx: Ctx = Depends(deps.student_ctx)):
    store = QuizStore()
    q = store.get_quiz(ctx.owner, quiz_id)
    if q is None:
        raise ApiError(404, "That quiz was not found.")
    if q["status"] == "submitted":
        raise ApiError(409, "A submitted quiz is kept in your history and cannot be discarded.")
    qs.decline_offer(ctx.owner, quiz_id, store)
    return {"ok": True}


@router.get("/{quiz_id}", response_model=OpenQuiz)
def open_quiz(quiz_id: str, ctx: Ctx = Depends(deps.student_ctx), rt=Depends(deps.runtime)):
    try:
        view = qs.open_view(ctx.owner, quiz_id, ctx.allowed, note_lectures(rt))
    except QuizError as exc:
        raise quiz_error(exc)
    return {"quiz_id": view["quiz_id"], "length": view["length"], "current": view["current"], "answered": view["answered"],
            "questions": view["questions"], "selections": {str(k): v for k, v in view["selections"].items()}}


@router.put("/{quiz_id}/answers/{index}", response_model=AnsweredOut)
def answer(quiz_id: str, index: int, body: AnswerIn, ctx: Ctx = Depends(deps.student_ctx), rt=Depends(deps.runtime)):
    store = QuizStore()
    try:
        qs._open_checked(ctx.owner, quiz_id, ctx.allowed, note_lectures(rt), store)
        store.select(ctx.owner, quiz_id, index, body.option_ids)
        q = store.get_quiz(ctx.owner, quiz_id)
    except QuizError as exc:
        raise quiz_error(exc)
    return {"ok": True, "answered": sum(1 for v in q["selections"].values() if v)}


@router.put("/{quiz_id}/current", response_model=Ok)
def current(quiz_id: str, body: CurrentIn, ctx: Ctx = Depends(deps.student_ctx), rt=Depends(deps.runtime)):
    store = QuizStore()
    try:
        qs._open_checked(ctx.owner, quiz_id, ctx.allowed, note_lectures(rt), store)
        store.goto(ctx.owner, quiz_id, body.index)
    except QuizError as exc:
        raise quiz_error(exc)
    return {"ok": True}


def results_json(res):
    out = []
    for q in res["questions"]:
        spans = q["spans"]
        flat = list(spans["key"]) + list(spans["explanation"]) + [s for sup in spans["alternatives"].values() for s in sup]
        out.append({"n": q["n"], "stem": q["stem"], "lead_in": q["lead_in"], "options": [{"id": o["id"], "text": o["text"]} for o in q["options"]],
                    "selected": q["selected"], "answer_ids": q["answer_ids"], "correct": q["correct"], "explanation": q["explanation"],
                    "alternatives": q["alternatives"], "evidence": [{**e, "url": e["url"] or None, "license": e.get("license") or None} for e in q["evidence"]],
                    "label": q["label"], "review_status": q["review_status"], "web": q.get("web", False), "source_note": q.get("source_note"),
                    "spans": [{"source_id": s["source_id"], "span": s["span"]} for s in flat if s.get("span") and any(e["id"] == s["source_id"] and e["visible"] for e in q["evidence"])]})
    return {"quiz_id": res["quiz_id"], "score": res["score"], "length": res["length"], "submitted": convert.iso(res["submitted"]), "questions": out}


@router.post("/{quiz_id}/submit", response_model=Results)
def submit(quiz_id: str, ctx: Ctx = Depends(deps.student_ctx), rt=Depends(deps.runtime)):
    try:
        return results_json(qs.submit(ctx.owner, quiz_id, ctx.allowed, note_lectures(rt)))
    except QuizError as exc:
        raise quiz_error(exc)


@router.get("/{quiz_id}/results", response_model=Results)
def results(quiz_id: str, ctx: Ctx = Depends(deps.student_ctx), rt=Depends(deps.runtime)):
    try:
        return results_json(qs.results(ctx.owner, quiz_id, ctx.allowed, note_lectures(rt)))
    except QuizError as exc:
        raise quiz_error(exc)
