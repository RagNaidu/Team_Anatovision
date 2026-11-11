"""AnatoVision JSON API.   Run:  .venv/bin/uvicorn app_api.main:app --port 8000      (docs/api_dev.md)

The contract is docs/api_contract.md; docs/openapi.json is exported from this app by scripts/export_openapi.py.
"""
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app_api import config, errors  # noqa: E402
from app_api.routers import admin, ask, auth, bank, chats, guide, guide_admin, notes, quiz  # noqa: E402

UNSAFE = ("POST", "PUT", "PATCH", "DELETE")


def warm(app):
    """Load the index and the embedding model in the background so the first question is not slow. Failure is left for the first request."""
    try:
        from app_api import deps
        from src import service
        if getattr(app.state, "runtime", None) is None:
            with deps._runtime_lock:
                if getattr(app.state, "runtime", None) is None:
                    app.state.runtime = service.build_runtime()
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src import auth as users, chat_store, guide_store
    from src.quiz import store as quiz_store
    from src import ttlcache
    try:
        ttlcache.configure(int(os.environ.get("HELPER_CACHE_SECONDS", "120")))       # identical rewrite/rerank calls within 2 minutes are not repeated
    except ValueError:
        ttlcache.configure(120)
    users.ensure_seed()                                    # prints generated demo passwords once, only if data/users.json does not exist
    try:
        chat_store.ChatStore().purge()
        guide_store.GuideStore().purge()
        quiz_store.QuizStore().purge()
    except Exception:
        pass
    if getattr(app.state, "warm_runtime", True):
        threading.Thread(target=warm, args=(app,), daemon=True, name="warm-runtime").start()
    yield
    ttlcache.configure(0)


def _hook_reload(app):
    """After a Notes-manager swap the running search must read the new index; it keeps the loaded embedding model."""
    from src import notes_manager as NM
    from src.modes import qa
    from src.retrieval.search import Searcher

    def reload():
        rt = getattr(app.state, "runtime", None)
        old = getattr(rt, "searcher", None)
        if old is None or not hasattr(old, "_model"):
            return
        s = Searcher()
        s._model = old._model
        rt.searcher = s
        rt.next_of = qa.next_sections(s)

    NM.RELOAD = [reload]
    NM.MODEL_PROVIDER = lambda: getattr(getattr(getattr(app.state, "runtime", None), "searcher", None), "_model", None)


def create_app(warm_runtime=True):
    app = FastAPI(title="AnatoVision API", version="1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json",
                  redoc_url=None, description="See docs/api_contract.md. Errors are always {\"error\": string}.")
    app.state.warm_runtime = warm_runtime
    errors.install(app)

    allowed_origins = [config.DEV_ORIGIN] if config.development() else []
    if allowed_origins:
        app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                           allow_headers=["Content-Type"])

    @app.middleware("http")
    async def same_site_only(request: Request, call_next):
        """Writes must come from this site (or the dev server): a browser sends Origin on cross-site requests, and the cookie is SameSite=Lax too."""
        origin = request.headers.get("origin")
        if request.method in UNSAFE and origin and origin not in allowed_origins and urlparse(origin).netloc != request.headers.get("host"):
            return errors.respond(403, "That request came from another site, so it was not accepted.")
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    _hook_reload(app)
    for module in (auth, chats, ask, guide, quiz, admin, notes, bank, guide_admin):
        app.include_router(module.router, prefix="/api")
    return app


app = create_app()
