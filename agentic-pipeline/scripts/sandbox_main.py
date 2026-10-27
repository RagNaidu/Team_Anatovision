"""Run the web app against a throw-away data folder, so a demo or a screenshot session never touches real data.

  SANDBOX_DIR=/some/folder  .venv/bin/streamlit run scripts/sandbox_main.py

Accounts (ANATOVISION_USERS_PATH), chats (ANATOVISION_CHATS_PATH), the question log, flags and settings all live in SANDBOX_DIR.
The search index, the notes and the model key are the real ones (read only).
"""
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
box = Path(os.environ["SANDBOX_DIR"])
box.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("ANATOVISION_USERS_PATH", str(box / "users.json"))
os.environ.setdefault("ANATOVISION_CHATS_PATH", str(box / "chats.db"))
os.environ.setdefault("ANATOVISION_GUIDE_SESSIONS_PATH", str(box / "guide_sessions.db"))
os.environ.setdefault("ANATOVISION_QUIZ_PATH", str(box / "quizzes.db"))

from src import auth, chat_store, guide_store, usage, verified, web_fallback  # noqa: E402
from src.modes import qa  # noqa: E402

auth.USERS_PATH = Path(os.environ["ANATOVISION_USERS_PATH"])
chat_store.DB_PATH = Path(os.environ["ANATOVISION_CHATS_PATH"])
guide_store.DB_PATH = Path(os.environ["ANATOVISION_GUIDE_SESSIONS_PATH"])
from src.quiz import store as quiz_store  # noqa: E402
quiz_store.DB_PATH = Path(os.environ["ANATOVISION_QUIZ_PATH"])
usage.QUESTION_LOG_PATH, usage.SETTINGS_PATH = box / "qlog.jsonl", box / "settings.json"
qa.FLAGS_PATH = verified.FLAGS_PATH = box / "flags.jsonl"
verified.FIXES_PATH = box / "fixes.jsonl"
web_fallback.CACHE_DIR = box / "web_cache"
runpy.run_path(str(ROOT / "app" / "main.py"), run_name="__main__")
