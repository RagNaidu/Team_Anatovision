"""Saved chats (Q&A history). A student's chats live in data/chats.db (src/chat_store.py), one owner per chat.

An instructor who is previewing gets throw-away chats kept in memory for the length of the session: they work (follow-ups see the
earlier turns) but nothing is written to disk.
"""
import time
import uuid

from fastapi import APIRouter, Depends, Request

from app_api import convert, deps
from app_api.deps import Ctx
from app_api.errors import ApiError
from app_api.schemas import ChatItem, ChatOut, Ok, TitleIn, TitleOut
from src import chat_store

router = APIRouter(prefix="/chats", tags=["chats"])
NEW = "New chat"


_current = {}


def current_index(rt):
    """The CURRENT notes and guide passages, to tell a student when an old answer cites a section the revised notes changed or removed (built once per index)."""
    chunks = getattr(getattr(rt, "searcher", None), "chunks", None)
    if not chunks:
        return None
    key = id(chunks)
    if _current.get("key") != key:
        from src.revision_status import CurrentIndex
        _current.clear()
        _current.update(key=key, index=CurrentIndex(chunks))
    return _current["index"]


def store():
    return chat_store.ChatStore()


def preview_chats(request: Request, ctx: Ctx):
    bucket = getattr(request.app.state, "preview_chats", None)
    if bucket is None:
        bucket = request.app.state.preview_chats = {}
    return bucket.setdefault(ctx.token, {})


def chat_rows(request, ctx, chat_id):
    """The chat in the form chat_store.get_chat_rows returns, or None. Foreign and unknown ids are the same: None."""
    if ctx.preview:
        return preview_chats(request, ctx).get(chat_id)
    return store().get_chat_rows(ctx.real["username"], chat_id)


def need_chat(request, ctx, chat_id):
    chat = chat_rows(request, ctx, chat_id)
    if chat is None:
        raise ApiError(404, "That chat was not found.")
    return chat


@router.get("", response_model=list[ChatItem])
def list_chats(request: Request, ctx: Ctx = Depends(deps.student_ctx)):
    """Newest first. Empty chats (no question yet) are left out of the history."""
    if ctx.preview:
        return []
    return [{"id": c["id"], "title": c["title"], "updated_at": convert.iso(c["updated"])}
            for c in store().list_chats(ctx.real["username"]) if c["n_messages"]]


@router.post("", response_model=ChatItem, tags=["chats"])
def new_chat(request: Request, ctx: Ctx = Depends(deps.student_ctx)):
    """A new, empty chat titled "New chat". If the user already has an empty chat it is returned instead of making another one."""
    now = time.time()
    if ctx.preview:
        cid = "preview-" + uuid.uuid4().hex[:12]
        preview_chats(request, ctx)[cid] = {"id": cid, "title": NEW, "updated": now, "messages": []}
        return {"id": cid, "title": NEW, "updated_at": convert.iso(now)}
    s, user = store(), ctx.real["username"]
    empty = next((c for c in s.list_chats(user) if c["n_messages"] == 0), None)
    if empty:
        return {"id": empty["id"], "title": empty["title"], "updated_at": convert.iso(empty["updated"])}
    try:
        cid = s.create_chat(user, "", now)
    except chat_store.ChatLimit as exc:
        raise ApiError(409, str(exc))
    return {"id": cid, "title": NEW, "updated_at": convert.iso(now)}


@router.get("/{chat_id}", response_model=ChatOut)
def get_chat(chat_id: str, request: Request, ctx: Ctx = Depends(deps.student_ctx), rt=Depends(deps.runtime)):
    chat = need_chat(request, ctx, chat_id)
    return {"id": chat["id"], "title": chat["title"], "messages": convert.chat_messages(chat, current_index(rt), allowed=ctx.allowed)}


@router.patch("/{chat_id}", response_model=TitleOut)
def rename_chat(chat_id: str, body: TitleIn, request: Request, ctx: Ctx = Depends(deps.student_ctx)):
    need_chat(request, ctx, chat_id)
    title = " ".join(body.title.split())
    if not title:
        raise ApiError(422, "Type a name for the chat.")
    if ctx.preview:
        preview_chats(request, ctx)[chat_id]["title"] = title
        return {"id": chat_id, "title": title}
    store().rename_chat(ctx.real["username"], chat_id, title)
    return {"id": chat_id, "title": store().get_chat_rows(ctx.real["username"], chat_id)["title"]}


@router.delete("/{chat_id}", response_model=Ok)
def delete_chat(chat_id: str, request: Request, ctx: Ctx = Depends(deps.student_ctx)):
    need_chat(request, ctx, chat_id)
    if ctx.preview:
        preview_chats(request, ctx).pop(chat_id, None)
    else:
        store().delete_chat(ctx.real["username"], chat_id)
    return {"ok": True}
