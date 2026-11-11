"""Saved Guide sessions: one SQLite file (data/guide_sessions.db, git-ignored), one row per (user, guide).

What is stored is the student-safe session state of src/modes/guide_chat.py: position, what the student said they did or are missing,
and the conversation text the student was shown. No raw model output, no scores, no fact-check or instructor detail, no cost.

  GuideStore(path).load(user, guide_file) -> state | None
  .save(user, guide_file, state)           replaces that user's row for that guide
  .delete(user, guide_file)                the explicit reset
  .purge(days)                             rows untouched for CHAT_RETENTION_DAYS (default 90) are deleted (app start and login)

Every read and write matches the user in SQL, so one user can never reach another's session. Limits: it is a local file (demo-grade, no
encryption at rest); a professor previewing as a student saves nothing; a session for a guide whose slides changed is repaired on load
(unknown steps are dropped by guide_chat.sanitize_state).
"""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from src import chat_store

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("ANATOVISION_GUIDE_SESSIONS_PATH") or ROOT / "data" / "guide_sessions.db")
SCHEMA = """CREATE TABLE IF NOT EXISTS guide_sessions (user TEXT NOT NULL, guide TEXT NOT NULL, state TEXT NOT NULL, updated REAL NOT NULL,
                                                PRIMARY KEY (user, guide));
CREATE TABLE IF NOT EXISTS guide_history (user TEXT NOT NULL, item TEXT NOT NULL, kind TEXT NOT NULL, ref TEXT NOT NULL, title TEXT NOT NULL,
                                          station INTEGER NOT NULL, count INTEGER NOT NULL, updated REAL NOT NULL, body_type TEXT NOT NULL DEFAULT '',
                                          notice TEXT NOT NULL DEFAULT '', PRIMARY KEY (user, item));"""
SAFE_KEYS = ("v", "file", "class_label", "display_name", "started", "pos", "done", "missing", "visited", "checked", "pending", "expects",
             "last_question", "body_type", "messages")


def student_safe(state):
    """Only the known keys, and only the fields of a message the student saw."""
    out = {k: state[k] for k in SAFE_KEYS if k in state}
    out["messages"] = [{"role": m["role"], "text": m["text"], "cites": list(m.get("cites", [])), "kind": m.get("kind", ""),
                        "fallback": bool(m.get("fallback")), "match": m.get("match", "na")} for m in state.get("messages", [])]
    return out


class GuideStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)
            cols = {r[1] for r in db.execute("PRAGMA table_info(guide_history)")}
            if "body_type" not in cols:                                   # a history table made before body types existed
                db.execute("ALTER TABLE guide_history ADD COLUMN body_type TEXT NOT NULL DEFAULT ''")
            if "notice" not in cols:                                      # ... or before a revised guide could reset a place (shown to the student once)
                db.execute("ALTER TABLE guide_history ADD COLUMN notice TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path)
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def load(self, user, guide):
        with self._db() as db:
            row = db.execute("SELECT state FROM guide_sessions WHERE user = ? AND guide = ?", (user, guide)).fetchone()
        try:
            return json.loads(row[0]) if row else None
        except ValueError:
            return None

    def save(self, user, guide, state):
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO guide_sessions (user, guide, state, updated) VALUES (?, ?, ?, ?)",
                       (user, guide, json.dumps(student_safe(state)), time.time()))

    def delete(self, user, guide):
        with self._db() as db:
            db.execute("DELETE FROM guide_sessions WHERE user = ? AND guide = ?", (user, guide))

    def guides_of(self, user):
        with self._db() as db:
            return [r[0] for r in db.execute("SELECT guide FROM guide_sessions WHERE user = ?", (user,))]

    # -- history: which guide (or lecture sample) a student worked on, and the furthest station they reached ----------------
    def touch_history(self, user, kind, ref, title, station, count, body_type=None):
        """Remember that `user` is at `station` (0-based) of this guide. The furthest station reached is kept; the title and count follow the source;
        the body type is saved when given and kept as it was when None."""
        item = f"{kind}:{ref}"
        with self._db() as db:
            row = db.execute("SELECT station, body_type FROM guide_history WHERE user = ? AND item = ?", (user, item)).fetchone()
            best = max(station, row[0]) if row else station
            bt = body_type if body_type is not None else (row[1] if row else "")
            db.execute("INSERT OR REPLACE INTO guide_history (user, item, kind, ref, title, station, count, updated, body_type, notice) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '')",
                       (user, item, kind, ref, title, min(best, max(0, count - 1)), count, time.time(), bt))
        return item

    def put_history_row(self, user, item, kind, ref, title, station, count, body_type="", notice="", updated=None):
        """Write one row as it is (used when a revised guide moves a student's place). The notice is shown once and cleared by the next touch."""
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO guide_history (user, item, kind, ref, title, station, count, updated, body_type, notice) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (user, item, kind, ref, title, station, count, updated or time.time(), body_type, notice))

    def history_of(self, user, limit=50):
        with self._db() as db:
            rows = db.execute("SELECT item, kind, ref, title, station, count, updated, body_type, notice FROM guide_history WHERE user = ? ORDER BY updated DESC LIMIT ?",
                              (user, limit)).fetchall()
        return [{"id": r[0], "kind": r[1], "ref": r[2], "title": r[3], "station": r[4], "count": r[5], "updated": r[6], "body_type": r[7] or None,
                 "notice": r[8] or None} for r in rows]

    def body_type_of(self, user, kind, ref):
        with self._db() as db:
            row = db.execute("SELECT body_type FROM guide_history WHERE user = ? AND item = ?", (user, f"{kind}:{ref}")).fetchone()
        return (row[0] if row else "") or ""

    def delete_history(self, user, item):
        """-> True if one of this user's rows was removed (another user's row is never touched)."""
        with self._db() as db:
            return db.execute("DELETE FROM guide_history WHERE user = ? AND item = ?", (user, item)).rowcount > 0

    def purge(self, days=None):
        cutoff = time.time() - 86400 * (days or chat_store.retention_days())
        with self._db() as db:
            db.execute("DELETE FROM guide_history WHERE updated < ?", (cutoff,))
            return db.execute("DELETE FROM guide_sessions WHERE updated < ?", (cutoff,)).rowcount
