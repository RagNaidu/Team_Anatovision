"""POST /api/ask and the "report an error" flag. Both wrap existing code: service.ask_for_student and student_report.report_error."""
import json
import os
import re
import threading
import time
import uuid

from fastapi import APIRouter, Depends, Request

from app_api import catalog, config, convert, deps
from app_api.deps import Ctx
from app_api.errors import ApiError
from app_api.routers import chats
from app_api.schemas import AskIn, AskStatus, FlagIn, Message, Ok
from src import chat_store, service, student_report, usage
from src import stagetime
from src import query as qry

router = APIRouter(tags=["ask"])
BODY_TYPE = re.compile(r"^(more|average|less) fat, (more|average|less) muscle, (large|average|small) build$")
_slots = threading.BoundedSemaphore(4)          # at most four questions are being answered at once


def scope_titles(ctx, lecture_ids):
    """The lectures the search may use: the grants, narrowed to the lectures the student picked (as the Streamlit sidebar does)."""
    allowed = ctx.allowed
    if not lecture_ids:
        return allowed
    chosen = []
    for lid in lecture_ids:
        title = catalog.lecture_title(lid)
        if title is None:
            raise ApiError(422, "One of the lectures you picked does not exist.")
        if title in allowed:
            chosen.append(title)
    return chosen or allowed


class Progress:
    """Which of four stage words each running question has reached: searching -> reading -> writing -> checking -> done. Nothing else is kept,
    so nothing of an answer (and nothing the safe layer has not seen) can leave through it. A word never goes backwards; entries live 2 minutes
    after the answer is sent, and belong to the user who asked."""
    ORDER = stagetime.PHASES + ("done",)
    KEEP = 120

    def __init__(self):
        self.lock, self.items = threading.Lock(), {}

    def start(self, rid, owner):
        with self.lock:
            now = time.time()
            for k in [k for k, v in self.items.items() if now - v["t"] > self.KEEP]:
                del self.items[k]
            if rid in self.items and self.items[rid]["owner"] != owner:
                raise ApiError(409, "That request id is already in use.")
            self.items[rid] = {"owner": owner, "stage": "searching", "t": now}

    def move(self, rid, stage):
        with self.lock:
            item = self.items.get(rid)
            if item and self.ORDER.index(stage) > self.ORDER.index(item["stage"]):
                item["stage"], item["t"] = stage, time.time()

    def get(self, rid, owner):
        with self.lock:
            item = self.items.get(rid)
        if item is None or item["owner"] != owner:
            raise ApiError(404, "No question with that id is being answered.")
        return item["stage"]


def progress_of(request: Request) -> Progress:
    if getattr(request.app.state, "progress", None) is None:
        request.app.state.progress = Progress()
    return request.app.state.progress


def log_timing(question, brief, rec, total, tokens=None):
    """Server-side only, and only when API_TIMING_LOG names a file (the sandbox sets it): one JSON line per question with the time of each stage.
    Never sent to a client and never written otherwise."""
    path = os.environ.get("API_TIMING_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"question": question, "brief": brief, "total": round(total, 3), "tokens": tokens, "stages": rec.rows}) + "\n")


def history_of(chat):
    """Earlier turns in the shape src/query.py expects: [{"role": "user", "text"}, {"role": "assistant", "result"}]."""
    msgs = [{"role": "user", "text": m["text"]} if m["role"] == "user" else {"role": "assistant", "result": m["result"]}
            for m in chat["messages"]]
    return qry.recent_turns(msgs)


@router.post("/ask", response_model=Message)
def ask(body: AskIn, request: Request, ctx: Ctx = Depends(deps.student_ctx), rt=Depends(deps.runtime), progress: Progress = Depends(progress_of)):
    question = body.question.strip()
    if not question:
        raise ApiError(422, "Type a question first.")
    if len(question) > config.MAX_QUESTION:
        raise ApiError(422, service.too_long_message(len(question)))
    body_type = (body.body_type or "").strip()
    if body_type and not BODY_TYPE.match(body_type):
        raise ApiError(422, "The body type is not one of the choices.")
    chat = chats.need_chat(request, ctx, body.chat_id)
    user = ctx.real["username"]
    if not ctx.preview and not chats.store().can_add_turn(user, body.chat_id):
        raise ApiError(409, chat_store.CHAT_FULL)
    allowed = scope_titles(ctx, body.lecture_ids)
    brief = body.length != "detailed"
    t0 = time.perf_counter()
    rid = body.request_id
    if rid:
        progress.start(rid, ctx.owner)
    rec = stagetime.Recorder(on_phase=(lambda phase: progress.move(rid, phase)) if rid else None)
    try:
        with _slots, stagetime.use(rec):
            reply = service.ask_for_student(
                question, body_type, brief, allowed, runtime=rt, session_cost=ctx.cost, cap=usage.load_settings()["spending_cap_usd"],
                history=history_of(chat), user=user, as_user=ctx.student["username"] if ctx.preview else "",
                kind="professor_preview" if ctx.preview else "chat_answer")
    finally:
        if rid:
            progress.move(rid, "done")
    log_timing(question, brief, rec, time.perf_counter() - t0, reply["tokens"])
    ctx.sessions.add_cost(ctx.token, reply["cost"])
    timing = int((time.perf_counter() - t0) * 1000)
    view, now, n = reply["view"], time.time(), len(chat["messages"])
    if ctx.preview:
        mid = f"{body.chat_id}:{n + 1}"
        chat["messages"] += [{"seq": n, "created": now, "role": "user", "text": question},
                             {"seq": n + 1, "created": now, "role": "assistant", "result": view, "brief": brief, "timing_ms": timing}]
        chat["updated"] = now
        if not n:
            chat["title"] = chat_store.make_title(question)
    else:
        s = chats.store()
        try:
            s.add_turn(user, body.chat_id, question, view, brief, now, timing)
            if n == 0 and chat["title"] == chats.NEW:
                s.rename_chat(user, body.chat_id, chat_store.make_title(question))
        except chat_store.ChatLimit as exc:
            raise ApiError(409, str(exc))
    return convert.assistant_message(view, id=convert.message_id(body.chat_id, n + 1), created=now, timing_ms=timing, allowed=ctx.allowed)


@router.get("/ask/status/{request_id}", response_model=AskStatus)
def ask_status(request_id: str, ctx: Ctx = Depends(deps.student_ctx), progress: Progress = Depends(progress_of)):
    """Where a question is: searching | reading | writing | checking | done. Send POST /api/ask with a `request_id`, then poll this once a second.
    Only the stage word is returned. The answer itself arrives whole in the POST response, after the student-safe layer has run. 404 until the
    POST has registered the id (treat it as "searching"), and for another user's id."""
    return {"stage": progress.get(request_id, ctx.owner)}


@router.post("/messages/{message_id}/flag", response_model=Ok)
def flag_message(message_id: str, body: FlagIn, request: Request, ctx: Ctx = Depends(deps.student_ctx)):
    """A student's "Report an error": goes to the instructor's queue (data/flags.jsonl, type student_report). A preview saves nothing."""
    chat_id, seq = convert.parse_message_id(message_id)
    if chat_id is None:
        raise ApiError(404, "That message was not found.")
    chat = chats.need_chat(request, ctx, chat_id)
    msg = next((m for m in chat["messages"] if m["seq"] == seq and m["role"] == "assistant"), None)
    if msg is None:
        raise ApiError(404, "That message was not found.")
    if ctx.preview:
        return {"ok": True}
    prev = next((m for m in chat["messages"] if m["seq"] == seq - 1 and m["role"] == "user"), None)
    reason = body.reason.strip()
    comment = (body.comment or "").strip()
    if reason not in student_report.REASONS:
        comment, reason = (f"{reason} {comment}").strip(), "Something else"
    result = msg["result"]
    cites = [c["cite"] for c in result.get("citations", [])]
    student_report.report_error(ctx.real["username"], prev["text"] if prev else "", result.get("answer_text", ""), cites, reason, comment,
                                convert.web_urls(result))
    return {"ok": True}
