"""Settings read from the environment (never from .env contents printed anywhere)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEV_ORIGIN = "http://localhost:5173"
COOKIE_NAME = "anatovision_session"
SESSION_HOURS = 12
MAX_QUESTION = 600
MAX_DESCRIPTION = 1000
MAX_TOPIC = 80
PAGE_SIZE = 25


def sessions_path():
    return Path(os.environ.get("ANATOVISION_API_SESSIONS_PATH") or ROOT / "data" / "api_sessions.db")


def development():
    """CORS for the Vite dev server exists only while APP_ENV is 'development' (the default)."""
    return os.environ.get("APP_ENV", "development").strip().lower() == "development"


def cookie_secure():
    """Set API_COOKIE_SECURE=1 behind HTTPS. Off by default so http://localhost works."""
    return os.environ.get("API_COOKIE_SECURE", "0").strip().lower() in ("1", "true", "yes", "on")


def login_ip_limit():
    try:
        return max(1, int(os.environ.get("LOGIN_IP_MAX", "20")))
    except ValueError:
        return 20
