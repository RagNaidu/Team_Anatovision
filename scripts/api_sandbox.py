"""Run the JSON API against a throw-away data folder, so a live check never writes to the real question log, flags, accounts, chats or quizzes.

    SANDBOX_DIR=/some/folder  .venv/bin/python scripts/api_sandbox.py [--port 8000]

Accounts (a student with every lecture and guide, one with none, an instructor), chats, quizzes, sessions, the question log, flags, fixes,
settings and the web cache all live in SANDBOX_DIR. The search index, the notes and the BullsAI key are the real ones (read only).
Passwords are printed once to this terminal.
"""
import argparse
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# BullsAI only. These win over .env (load_dotenv never overrides a variable that is already set), because a .env may still name another provider.
os.environ.update(LLM_PROVIDER="bullsai", QUIZ_LLM_PROVIDER="bullsai", BULLSAI_MODEL="google/gemma-4-31B-it", RERANK="on", WEB_FALLBACK="on",
                  WEB_ALLOW_WIKIPEDIA="on")
os.environ.pop("BULLSAI_REWRITE_MODEL", None)
os.environ.setdefault("API_TIMING_LOG", str(Path(os.environ["SANDBOX_DIR"]) / "timing.jsonl"))
box = Path(os.environ["SANDBOX_DIR"])
box.mkdir(parents=True, exist_ok=True)
for var, name in (("ANATOVISION_USERS_PATH", "users.json"), ("ANATOVISION_CHATS_PATH", "chats.db"), ("ANATOVISION_GUIDE_SESSIONS_PATH", "guide_sessions.db"),
                  ("ANATOVISION_QUIZ_PATH", "quizzes.db"), ("ANATOVISION_API_SESSIONS_PATH", "api_sessions.db")):
    os.environ[var] = str(box / name)

from src import auth, chat_store, guide_store, usage, verified, web_fallback  # noqa: E402
from src.modes import qa  # noqa: E402
from src.quiz import store as quiz_store  # noqa: E402
from app_api import catalog  # noqa: E402

auth.USERS_PATH = Path(os.environ["ANATOVISION_USERS_PATH"])
chat_store.DB_PATH = Path(os.environ["ANATOVISION_CHATS_PATH"])
guide_store.DB_PATH = Path(os.environ["ANATOVISION_GUIDE_SESSIONS_PATH"])
quiz_store.DB_PATH = Path(os.environ["ANATOVISION_QUIZ_PATH"])
usage.QUESTION_LOG_PATH, usage.SETTINGS_PATH = box / "qlog.jsonl", box / "settings.json"
qa.FLAGS_PATH = verified.FLAGS_PATH = box / "flags.jsonl"
verified.FIXES_PATH = box / "fixes.jsonl"
web_fallback.CACHE_DIR = box / "web_cache"

from src import llm  # noqa: E402
assert llm.provider() == "bullsai" and llm.default_model() == "google/gemma-4-31B-it", "the sandbox must run on BullsAI only"

if not auth.USERS_PATH.exists():
    pw = secrets.token_urlsafe(12)
    everything = catalog.all_lecture_titles() + [g["label"] for g in catalog.guides()]
    auth.save_users({"student": auth.new_record("Sandbox Student", "student", pw, everything),
                     "nogrants": auth.new_record("No Grants", "student", pw, []),
                     "instructor": auth.new_record("Sandbox Instructor", "professor", pw)})
    (box / "PASSWORD.txt").write_text(pw + "\n")
    os.chmod(box / "PASSWORD.txt", 0o600)
    print(f"sandbox accounts created in {box}: student, nogrants, instructor (password in {box / 'PASSWORD.txt'})", flush=True)

if __name__ == "__main__":
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    uvicorn.run("app_api.main:app", host="127.0.0.1", port=args.port, log_level="info")
