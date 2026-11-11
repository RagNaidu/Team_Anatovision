"""Server-side sessions: one SQLite file (data/api_sessions.db, git-ignored).

The browser holds only a random token in an httpOnly cookie; the database holds sha256(token), so a copy of the file cannot be used
to sign in. A session lasts 12 hours from login (a page reload keeps it; a server restart keeps it too, because it is on disk).
A session also remembers the instructor's "preview as student" choice and the model spend of the session (for the spending cap).
"""
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from app_api import config

SCHEMA = """CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, created REAL NOT NULL,
            expires REAL NOT NULL, preview TEXT, cost REAL NOT NULL DEFAULT 0);"""


def _hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SessionStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else config.sessions_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def create(self, username, now=None):
        now = now if now is not None else time.time()
        token = secrets.token_urlsafe(32)
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE expires < ?", (now,))
            db.execute("INSERT INTO sessions (token_hash, username, created, expires) VALUES (?, ?, ?, ?)",
                       (_hash(token), username, now, now + config.SESSION_HOURS * 3600))
        return token

    def get(self, token, now=None):
        """-> {"username", "preview", "cost"} or None (unknown or expired)."""
        if not token:
            return None
        now = now if now is not None else time.time()
        with self._db() as db:
            row = db.execute("SELECT * FROM sessions WHERE token_hash = ?", (_hash(token),)).fetchone()
            if row is None:
                return None
            if row["expires"] < now:
                db.execute("DELETE FROM sessions WHERE token_hash = ?", (row["token_hash"],))
                return None
        return {"username": row["username"], "preview": json.loads(row["preview"]) if row["preview"] else None, "cost": row["cost"]}

    def set_preview(self, token, preview):
        with self._db() as db:
            db.execute("UPDATE sessions SET preview = ? WHERE token_hash = ?", (json.dumps(preview) if preview else None, _hash(token)))

    def add_cost(self, token, cost):
        if cost:
            with self._db() as db:
                db.execute("UPDATE sessions SET cost = cost + ? WHERE token_hash = ?", (cost, _hash(token)))

    def delete(self, token):
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))
