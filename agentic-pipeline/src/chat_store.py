"""Chat history for the Q&A page: one SQLite file (data/chats.db, git-ignored), one owner per chat.

  ChatStore(path).create_chat(user, first_question) -> id          title = the first question, cut at a word (no model call)
  .add_turn(user, chat_id, question, view, brief)                  one question + the STUDENT-SAFE answer view, stored together
  .list_chats(user) -> [{id, title, updated, n_messages}]          newest first; group with group_label()
  .get_chat(user, chat_id) -> {id, title, messages} | None         messages are ready for the page: {"role": "user", "text"} /
                                                                    {"role": "assistant", "result": view, "instructor": None, "brief"}
  .rename_chat / .delete_chat / .purge(days)

What is stored is exactly what a student was shown (src/student_view.py): never the raw answer, fact-check text, scores, cost or
model, so reopening a chat cannot leak anything and never calls the model again.

Every method that reads or changes a chat takes the user name and matches it in SQL, so one user can never reach another's
chat, even with a guessed id. Limits: MAX_CHATS per user, MAX_MESSAGES per chat (ChatLimit has a friendly message).
Retention: chats with no activity for CHAT_RETENTION_DAYS (default 90) are deleted by purge(), which the app runs on start and on login.

This is separate from data/question_log.jsonl (the instructor's log of what students asked): deleting a chat does not touch that log.
"""
import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("ANATOVISION_CHATS_PATH") or ROOT / "data" / "chats.db")
MAX_CHATS = 50
MAX_MESSAGES = 200
TITLE_CHARS = 60
GROUPS = ("Today", "Yesterday", "Previous 7 days", "Older")
CHATS_FULL = f"You have {MAX_CHATS} saved chats, which is the most there can be. Delete one from the list to start a new chat."
CHAT_FULL = f"This chat has reached {MAX_MESSAGES} messages. Start a new chat to keep going."

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, user TEXT NOT NULL, title TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
CREATE INDEX IF NOT EXISTS chats_user ON chats (user, updated);
CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                                     seq INTEGER NOT NULL, role TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL);
CREATE INDEX IF NOT EXISTS messages_chat ON messages (chat_id, seq);
"""


class ChatLimit(Exception):
    """A limit was reached; str(exc) is a message fit to show a student."""


def retention_days():
    load_dotenv(ROOT / ".env")
    try:
        return max(1, int(os.environ.get("CHAT_RETENTION_DAYS") or 90))
    except ValueError:
        return 90


def make_title(question):
    """The first question, one line, cut at a word with an ellipsis. No model call."""
    text = re.sub(r"\s+", " ", question or "").strip() or "New chat"
    if len(text) <= TITLE_CHARS:
        return text
    return text[:TITLE_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:.") + "…"


def group_label(updated, now=None):
    """Today / Yesterday / Previous 7 days / Older, by calendar day on this machine."""
    now_d = datetime.fromtimestamp(now if now is not None else time.time()).date()
    days = (now_d - datetime.fromtimestamp(updated).date()).days
    return "Today" if days <= 0 else "Yesterday" if days == 1 else "Previous 7 days" if days <= 7 else "Older"


def grouped(chats, now=None):
    """[(group name, [chat, ...])] in the order GROUPS, skipping empty groups."""
    out = {g: [] for g in GROUPS}
    for c in chats:
        out[group_label(c["updated"], now)].append(c)
    return [(g, out[g]) for g in GROUPS if out[g]]


class ChatStore:
    def __init__(self, path=None):
        self.path = Path(path or DB_PATH)

    @contextmanager
    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA foreign_keys = ON")
            db.executescript(SCHEMA)
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ---- create / write -------------------------------------------------------------------------------------------

    def create_chat(self, user, first_question="", now=None):
        now = now if now is not None else time.time()
        with self._db() as db:
            if db.execute("SELECT COUNT(*) FROM chats WHERE user = ?", (user,)).fetchone()[0] >= MAX_CHATS:
                raise ChatLimit(CHATS_FULL)
            cid = uuid.uuid4().hex
            db.execute("INSERT INTO chats (id, user, title, created, updated) VALUES (?, ?, ?, ?, ?)",
                       (cid, user, make_title(first_question), now, now))
        return cid

    def can_add_turn(self, user, chat_id):
        with self._db() as db:
            row = db.execute("SELECT COUNT(*) FROM messages m JOIN chats c ON c.id = m.chat_id WHERE c.id = ? AND c.user = ?",
                             (chat_id, user)).fetchone()
        return row[0] + 2 <= MAX_MESSAGES

    def add_turn(self, user, chat_id, question, view, brief=True, now=None):
        """Store a question and its student-safe answer view together (so a chat never holds a question without its answer).
        Raises ChatLimit when the chat is full, KeyError when the chat is not this user's."""
        now = now if now is not None else time.time()
        with self._db() as db:
            if db.execute("SELECT 1 FROM chats WHERE id = ? AND user = ?", (chat_id, user)).fetchone() is None:
                raise KeyError(chat_id)
            n = db.execute("SELECT COUNT(*) FROM messages WHERE chat_id = ?", (chat_id,)).fetchone()[0]
            if n + 2 > MAX_MESSAGES:
                raise ChatLimit(CHAT_FULL)
            rows = [("user", {"text": question}), ("assistant", {"result": view, "brief": bool(brief)})]
            for k, (role, payload) in enumerate(rows):
                db.execute("INSERT INTO messages (chat_id, seq, role, payload, created) VALUES (?, ?, ?, ?, ?)",
                           (chat_id, n + k, role, json.dumps(payload, ensure_ascii=False, default=str), now))
            db.execute("UPDATE chats SET updated = ? WHERE id = ?", (now, chat_id))

    def rename_chat(self, user, chat_id, title):
        title = re.sub(r"\s+", " ", title or "").strip()
        if not title:
            raise ValueError("Type a name for the chat.")
        with self._db() as db:
            return db.execute("UPDATE chats SET title = ? WHERE id = ? AND user = ?",
                              (title[:TITLE_CHARS * 2], chat_id, user)).rowcount == 1

    def delete_chat(self, user, chat_id):
        """Permanent. -> True if a chat of this user was deleted."""
        with self._db() as db:
            return db.execute("DELETE FROM chats WHERE id = ? AND user = ?", (chat_id, user)).rowcount == 1

    # ---- read ----------------------------------------------------------------------------------------------------

    def list_chats(self, user):
        with self._db() as db:
            rows = db.execute("SELECT c.id, c.title, c.created, c.updated, COUNT(m.id) FROM chats c "
                              "LEFT JOIN messages m ON m.chat_id = c.id WHERE c.user = ? GROUP BY c.id ORDER BY c.updated DESC",
                              (user,)).fetchall()
        return [{"id": r[0], "title": r[1], "created": r[2], "updated": r[3], "n_messages": r[4]} for r in rows]

    def get_chat(self, user, chat_id):
        with self._db() as db:
            chat = db.execute("SELECT id, title, updated FROM chats WHERE id = ? AND user = ?", (chat_id, user)).fetchone()
            if chat is None:
                return None
            rows = db.execute("SELECT role, payload FROM messages WHERE chat_id = ? ORDER BY seq", (chat_id,)).fetchall()
        messages = []
        for role, payload in rows:
            p = json.loads(payload)
            messages.append({"role": "user", "text": p["text"]} if role == "user"
                            else {"role": "assistant", "result": p["result"], "instructor": None, "brief": p.get("brief", True)})
        return {"id": chat[0], "title": chat[1], "updated": chat[2], "messages": messages}

    # ---- retention -----------------------------------------------------------------------------------------------

    def purge(self, days=None, now=None):
        """Delete chats with no activity for `days` (default CHAT_RETENTION_DAYS = 90). -> number deleted."""
        days = retention_days() if days is None else days
        cutoff = (now if now is not None else time.time()) - days * 86400
        with self._db() as db:
            return db.execute("DELETE FROM chats WHERE updated < ?", (cutoff,)).rowcount
