"""Sign in / out, who am I, and what may this student use."""
import threading
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, Request, Response

from app_api import catalog, config, deps
from app_api.deps import Ctx, public_user
from app_api.errors import ApiError
from app_api.schemas import LoginIn, MeOut, Ok, ScopeOut, UserOut
from src import auth

router = APIRouter()
_fails = defaultdict(list)           # client address -> timestamps of recent failed logins (in memory)
_lock = threading.Lock()
WINDOW = 300


def _client(request):
    return request.client.host if request.client else "?"


def _ip_blocked(ip, now):
    with _lock:
        recent = [t for t in _fails[ip] if now - t < WINDOW]
        _fails[ip] = recent
        return len(recent) >= config.login_ip_limit()


@router.post("/auth/login", response_model=UserOut, tags=["auth"])
def login(body: LoginIn, request: Request, response: Response, store=Depends(deps.sessions)):
    """Wrong login -> 401. Throttled: 5 failures for one username, or LOGIN_IP_MAX (20) failures from one address, in 5 minutes -> 429."""
    now, ip, username = time.time(), _client(request), body.username.strip()
    if _ip_blocked(ip, now) or auth.locked(username, now):
        raise ApiError(429, "Too many sign-in attempts. Wait a few minutes and try again.")
    user = auth.authenticate(username, body.password, now)
    if user is None:
        with _lock:
            _fails[ip].append(now)
        raise ApiError(401, "Wrong username or password.")
    token = store.create(user["username"], now)
    response.set_cookie(config.COOKIE_NAME, token, max_age=config.SESSION_HOURS * 3600, httponly=True, samesite="lax",
                        secure=config.cookie_secure(), path="/")
    return {"user": public_user(user)}


@router.post("/auth/logout", response_model=Ok, tags=["auth"])
def logout(request: Request, response: Response, store=Depends(deps.sessions)):
    store.delete(request.cookies.get(config.COOKIE_NAME, ""))
    response.delete_cookie(config.COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me", response_model=MeOut, tags=["auth"])
def me(ctx: Ctx = Depends(deps.current)):
    preview = {"profile": "full" if ctx.student["username"] == "preview" else ctx.student["username"], "name": ctx.preview_name} if ctx.preview else None
    return {"user": public_user(ctx.real), "preview": preview}


@router.get("/scope", response_model=ScopeOut, tags=["scope"])
def scope(ctx: Ctx = Depends(deps.current)):
    """What this student may use. An instructor sees everything granted (or, while previewing, the previewed student's grants)."""
    allowed = ctx.allowed
    titles = set(allowed) if allowed is not None else None
    open_files = catalog.open_guides(allowed)
    return {"lectures": [{"id": l["id"], "title": l["title"], "granted": titles is None or l["title"] in titles} for l in catalog.lectures()],
            "guides": [{"id": g["id"], "class_number": g["class_number"], "title": g["title"], "lecture_ids": g["lecture_ids"],
                        "granted": g["file"] in open_files} for g in catalog.guides()]}
