"""Quiz storage: one SQLite file (data/quizzes.db, git-ignored). Private keys live ONLY here and in server memory while a request runs.

  items     every question that passed all gates, frozen (private JSON: key, explanation, evidence) plus its review status
  quizzes   one attempt per row: the ordered item ids, the student's saved selections, position, status, score
  runs      one line per build (what was asked, how many passed, why drafts were rejected): for the professor

Statuses of a quiz: offer (only 5 of 10 passed: waiting for the student's explicit choice) -> open -> submitted. Every read or change of a quiz
matches the user in SQL, so one user can never reach another's attempt, even with a guessed id. Selections are checked against the item's real
option ids. Items are never edited after they are saved; only their review columns change (professor approval).
"""
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from src import chat_store

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("ANATOVISION_QUIZ_PATH") or ROOT / "data" / "quizzes.db")
SCHEMA = """
CREATE TABLE IF NOT EXISTS items (item_id TEXT PRIMARY KEY, private TEXT NOT NULL, created REAL NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'unreviewed', review_by TEXT NOT NULL DEFAULT '', review_date TEXT NOT NULL DEFAULT '',
    review_note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS quizzes (id TEXT PRIMARY KEY, user TEXT NOT NULL, status TEXT NOT NULL, length INTEGER NOT NULL,
    requested INTEGER NOT NULL, scope TEXT NOT NULL, item_ids TEXT NOT NULL, selections TEXT NOT NULL DEFAULT '{}',
    current INTEGER NOT NULL DEFAULT 0, reviewed_only INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL,
    submitted REAL, score INTEGER);
CREATE INDEX IF NOT EXISTS quizzes_user ON quizzes (user, updated);
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT NOT NULL, ts REAL NOT NULL, detail TEXT NOT NULL);
"""
LENGTHS = (5, 10)


class QuizError(Exception):
    """str(exc) is a message fit to show the student."""


class QuizStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    # -- items (the bank) -----------------------------------------------------------------------------------------
    def save_items(self, items):
        with self._db() as db:
            for it in items:
                db.execute("INSERT OR IGNORE INTO items (item_id, private, created) VALUES (?, ?, ?)",
                           (it["item_id"], json.dumps(it), it["created"]))

    def item(self, item_id):
        with self._db() as db:
            row = db.execute("SELECT * FROM items WHERE item_id = ?", (item_id,)).fetchone()
        return self._item(row) if row else None

    @staticmethod
    def _item(row):
        it = json.loads(row["private"])
        it["review"] = {"status": row["review_status"], "by": row["review_by"], "date": row["review_date"], "note": row["review_note"]}
        return it

    def list_items(self, status=None, limit=200):
        q, args = "SELECT * FROM items", []
        if status:
            q += " WHERE review_status = ?"
            args.append(status)
        q += " ORDER BY created DESC LIMIT ?"
        with self._db() as db:
            return [self._item(r) for r in db.execute(q, (*args, limit))]

    def approved_items(self):
        return self.list_items("approved", 1000)

    def set_review(self, item_id, status, by, note="", date=None):
        if status not in ("unreviewed", "approved", "rejected"):
            raise QuizError("unknown review status")
        with self._db() as db:
            db.execute("UPDATE items SET review_status = ?, review_by = ?, review_date = ?, review_note = ? WHERE item_id = ?",
                       (status, by if status != "unreviewed" else "", (date or time.strftime("%Y-%m-%d")) if status != "unreviewed" else "",
                        note, item_id))

    # -- attempts -------------------------------------------------------------------------------------------------
    def create_quiz(self, user, item_ids, requested, scope, status="open", reviewed_only=False):
        if len(item_ids) not in LENGTHS:
            raise QuizError("A quiz has exactly 5 or 10 questions.")
        qid, now = uuid.uuid4().hex[:12], time.time()
        with self._db() as db:
            db.execute("INSERT INTO quizzes (id, user, status, length, requested, scope, item_ids, reviewed_only, created, updated) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (qid, user, status, len(item_ids), requested, json.dumps(scope), json.dumps(item_ids), int(reviewed_only), now, now))
        return qid

    @staticmethod
    def _quiz(row):
        q = dict(row)
        q["scope"], q["item_ids"], q["selections"] = json.loads(q["scope"]), json.loads(q["item_ids"]), json.loads(q["selections"])
        return q

    def get_quiz(self, user, qid):
        with self._db() as db:
            row = db.execute("SELECT * FROM quizzes WHERE id = ? AND user = ?", (qid, user)).fetchone()
        return self._quiz(row) if row else None

    def latest(self, user, statuses=("open", "offer")):
        marks = ",".join("?" * len(statuses))
        with self._db() as db:
            row = db.execute(f"SELECT * FROM quizzes WHERE user = ? AND status IN ({marks}) ORDER BY updated DESC LIMIT 1", (user, *statuses)).fetchone()
        return self._quiz(row) if row else None

    def list_quizzes(self, user, status="submitted", limit=20):
        with self._db() as db:
            return [self._quiz(r) for r in db.execute("SELECT * FROM quizzes WHERE user = ? AND status = ? ORDER BY updated DESC LIMIT ?", (user, status, limit))]

    def set_status(self, user, qid, status):
        with self._db() as db:
            db.execute("UPDATE quizzes SET status = ?, updated = ? WHERE id = ? AND user = ?", (status, time.time(), qid, user))

    def select(self, user, qid, index, option_ids):
        """Save the student's choice for question `index` (any time before submitting). Validated against the real options."""
        q = self.get_quiz(user, qid)
        if q is None or q["status"] != "open":
            raise QuizError("This quiz is not open.")
        if not 0 <= index < q["length"]:
            raise QuizError("No such question.")
        item = self.item(q["item_ids"][index])
        valid = {o["id"] for o in item["options"]}
        option_ids = [o for o in dict.fromkeys(option_ids) if o in valid]
        if item["selection_mode"] == "single":
            option_ids = option_ids[:1]
        q["selections"][str(index)] = option_ids
        with self._db() as db:
            db.execute("UPDATE quizzes SET selections = ?, updated = ? WHERE id = ? AND user = ?", (json.dumps(q["selections"]), time.time(), qid, user))

    def goto(self, user, qid, index):
        q = self.get_quiz(user, qid)
        if q is None or q["status"] != "open":
            raise QuizError("This quiz is not open.")
        with self._db() as db:
            db.execute("UPDATE quizzes SET current = ?, updated = ? WHERE id = ? AND user = ?", (max(0, min(index, q["length"] - 1)), time.time(), qid, user))

    def finish(self, user, qid, score):
        with self._db() as db:
            db.execute("UPDATE quizzes SET status = 'submitted', score = ?, submitted = ?, updated = ? WHERE id = ? AND user = ? AND status = 'open'",
                       (score, time.time(), time.time(), qid, user))

    def delete_quiz(self, user, qid):
        with self._db() as db:
            db.execute("DELETE FROM quizzes WHERE id = ? AND user = ? AND status != 'submitted'", (qid, user))

    def log_run(self, user, detail):
        with self._db() as db:
            db.execute("INSERT INTO runs (user, ts, detail) VALUES (?, ?, ?)", (user, time.time(), json.dumps(detail)))

    def runs(self, limit=50):
        with self._db() as db:
            return [{"user": r["user"], "ts": r["ts"], **json.loads(r["detail"])} for r in db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))]

    def purge(self, days=None):
        cutoff = time.time() - 86400 * (days or chat_store.retention_days())
        with self._db() as db:
            return db.execute("DELETE FROM quizzes WHERE updated < ?", (cutoff,)).rowcount
