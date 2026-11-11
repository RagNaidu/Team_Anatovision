"""Shared request helpers: who is signed in, who the student view is showing, and the search runtime.

Ctx.real       the signed-in account (public form, re-read from data/users.json on every request, so a removed account or a changed
               grant applies at once)
Ctx.student    the account the STUDENT tools act as: the student themself, or (an instructor who started a preview) the previewed
               student / full access. None for an instructor who is not previewing: the student tools then answer 403.
Ctx.preview    True while an instructor previews. Nothing of a preview is saved as the student's (chats, saved Guide sessions, usage as
               student); see docs/api_contract.md.
"""
import threading
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Request

from app_api import catalog, config
from app_api.errors import ApiError
from app_api.sessions import SessionStore
from src import auth

FULL = "full"
_runtime_lock = threading.Lock()


@dataclass
class Ctx:
    token: str
    real: dict
    student: Optional[dict]
    preview: bool
    preview_name: str
    sessions: SessionStore
    cost: float

    @property
    def is_instructor(self):
        return self.real["role"] == "professor"

    @property
    def owner(self):
        """The name quizzes and saved chats are kept under. A previewing instructor never writes as the student."""
        return f"preview:{self.real['username']}" if self.preview else self.real["username"]

    @property
    def allowed(self):
        """Lecture titles and guide labels the student tools may use, or None for the unrestricted instructor catalog."""
        return catalog.accessible_titles(self.student) if self.student else None

    @property
    def log_user(self):
        return self.real["username"]


def public_user(rec):
    return {"id": rec["username"], "name": rec["name"], "role": "instructor" if rec["role"] == "professor" else "student"}


def preview_student(profile):
    """The student record an instructor previews: a real student's grants, or access to every lecture. Always role student."""
    if profile != FULL:
        u = auth.get_user(profile)
        if u and u["role"] == "student":
            return u
    return {"username": "preview", "name": "Preview (full access)", "role": "student", "allowed_lectures": catalog.all_lecture_titles()}


def sessions(request: Request) -> SessionStore:
    store = getattr(request.app.state, "sessions", None)
    if store is None:
        store = request.app.state.sessions = SessionStore()
    return store


def current(request: Request, store: SessionStore = Depends(sessions)) -> Ctx:
    token = request.cookies.get(config.COOKIE_NAME)
    sess = store.get(token)
    user = auth.get_user(sess["username"]) if sess else None
    if sess is None or user is None:
        raise ApiError(401, "Please sign in.")
    preview = sess["preview"] if user["role"] == "professor" else None
    student = None
    if user["role"] == "student":
        student = user
    elif preview:
        student = preview_student(preview["profile"])
    return Ctx(token, user, student, bool(preview), student["name"] if preview and student else "", store, sess["cost"])


def student_ctx(ctx: Ctx = Depends(current)) -> Ctx:
    """The student tools (chats, ask, guide checks, quiz): a student, or an instructor who is previewing."""
    if ctx.student is None:
        raise ApiError(403, "Start a preview as a student first (POST /api/admin/preview).")
    return ctx


def instructor_ctx(ctx: Ctx = Depends(current)) -> Ctx:
    if not ctx.is_instructor:
        raise ApiError(403, "This is for instructors only.")
    return ctx


def runtime(request: Request):
    """The search runtime (index, embedding model, BullsAI client), loaded once. Tests put a fake at app.state.runtime."""
    rt = getattr(request.app.state, "runtime", None)
    if rt is None:
        with _runtime_lock:
            rt = getattr(request.app.state, "runtime", None)
            if rt is None:
                from src import service
                rt = request.app.state.runtime = service.build_runtime()
    return rt
