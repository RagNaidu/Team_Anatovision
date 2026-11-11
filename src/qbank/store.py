"""The bank store. One row per question (its CURRENT data), a full copy of every earlier version, comments and flags.

Rules that matter for students: only status = approved AND use = practice items can ever reach a quiz (see integrate.py); an item the instructor imported is
draft + exam_secure until he changes it; flags are AI opinions and never change status; nothing here auto-retires anything.
"""
import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("ANATOVISION_BANK_PATH") or ROOT / "data" / "question_bank" / "bank.db")
STATUSES = ("draft", "approved", "retired")
USES = ("practice", "exam_secure")
SOURCES = ("instructor", "ai", "web", "imported")
DIFFICULTIES = ("", "easy", "medium", "hard")
IDS = "ABCDE"
SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (id TEXT PRIMARY KEY, data TEXT NOT NULL, version INTEGER NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
    quiz_item_id TEXT, flags TEXT NOT NULL DEFAULT '[]', recheck TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS q_item ON questions (quiz_item_id);
CREATE TABLE IF NOT EXISTS versions (qid TEXT NOT NULL, version INTEGER NOT NULL, ts REAL NOT NULL, by TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL, PRIMARY KEY (qid, version));
CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, qid TEXT NOT NULL, ts REAL NOT NULL, by TEXT NOT NULL DEFAULT '', text TEXT NOT NULL);
"""


class BankError(Exception):
    """str(exc) is a message fit for the instructor."""

    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def words(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def normalize(d):
    """Validate and normalise one question's data. Raises BankError."""
    d = dict(d)
    lead = (d.get("lead_in") or "").strip()
    stem = (d.get("stem") or "").strip()
    if not lead:
        raise BankError("The lead-in (the actual question) is required.")
    opts = []
    for o in d.get("options") or []:
        text = (o.get("text") if isinstance(o, dict) else str(o) or "").strip()
        if text:
            opts.append(text)
    if not 2 <= len(opts) <= 5:
        raise BankError("A question needs 2 to 5 options.")
    if len({w for w in (" ".join(words(t)) for t in opts)}) != len(opts):
        raise BankError("Two options are the same.")
    ids = IDS[:len(opts)]
    answer = (d.get("answer") or "").strip().upper()
    if answer not in ids:
        raise BankError(f"The answer must be one of {', '.join(ids)}.")
    for k, lim in (("stem", 2000), ("lead_in", 500), ("explanation", 3000)):
        if len(d.get(k) or "") > lim:
            raise BankError(f"The {k.replace('_', ' ')} is too long (limit {lim} characters).")
    status, use, source = d.get("status") or "draft", d.get("use") or "practice", d.get("source") or "instructor"
    diff = d.get("difficulty") or ""
    if status not in STATUSES or use not in USES or source not in SOURCES or diff not in DIFFICULTIES:
        raise BankError("Status, use, source or difficulty is not a known value.")
    tags = []
    for t in d.get("tags") or []:
        t = re.sub(r"\s+", " ", str(t)).strip()[:40]
        if t and t.lower() not in [x.lower() for x in tags]:
            tags.append(t)
    return {"stem": stem, "lead_in": lead, "options": [{"id": i, "text": t} for i, t in zip(ids, opts)], "answer": answer, "explanation": (d.get("explanation") or "").strip(),
            "lecture": (d.get("lecture") or "").strip()[:200], "guide": (d.get("guide") or "").strip()[:200], "section": (d.get("section") or "").strip()[:400],
            "links": [{"doc_id": l.get("doc_id", ""), "section_id": l.get("section_id", ""), "breadcrumb": l.get("breadcrumb", ""), "hash": l.get("hash", "")} for l in (d.get("links") or [])][:6],
            "region": (d.get("region") or "").strip()[:60], "tags": tags[:12], "difficulty": diff, "source": source, "status": status, "use": use,
            "objective": (d.get("objective") or "").strip()[:300], "sample": bool(d.get("sample"))}


def diff_data(old, new):
    out = []
    for k in new:
        if old.get(k) != new.get(k):
            out.append({"field": k, "old": old.get(k), "new": new.get(k)})
    return out


def text_hash(text):
    return hashlib.sha1(re.sub(r"\s+", " ", (text or "").lower()).strip().encode()).hexdigest()[:16]


class BankStore:
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

    @staticmethod
    def _q(row):
        return {"id": row["id"], "version": row["version"], "created": row["created"], "updated": row["updated"], "quiz_item_id": row["quiz_item_id"], "data": json.loads(row["data"]),
                "flags": json.loads(row["flags"]), "recheck": row["recheck"]}

    # -- reading
    def get(self, qid):
        with self._db() as db:
            r = db.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()
        return self._q(r) if r else None

    def all(self):
        with self._db() as db:
            return [self._q(r) for r in db.execute("SELECT * FROM questions ORDER BY created DESC, id").fetchall()]

    def by_quiz_item(self, item_id):
        with self._db() as db:
            r = db.execute("SELECT * FROM questions WHERE quiz_item_id = ?", (item_id,)).fetchone()
        return self._q(r) if r else None

    def versions(self, qid):
        with self._db() as db:
            return [{"version": r["version"], "ts": r["ts"], "by": r["by"], "note": r["note"], "data": json.loads(r["data"])}
                    for r in db.execute("SELECT * FROM versions WHERE qid = ? ORDER BY version DESC", (qid,)).fetchall()]

    def comments(self, qid):
        with self._db() as db:
            return [{"id": r["id"], "ts": r["ts"], "by": r["by"], "text": r["text"]} for r in db.execute("SELECT * FROM comments WHERE qid = ? ORDER BY id", (qid,)).fetchall()]

    # -- writing (every change to the data is a new version)
    def create(self, data, by="", note="created", quiz_item_id=None, qid=None):
        d = normalize(data)
        qid = qid or "q-" + uuid.uuid4().hex[:10]
        now = time.time()
        with self._db() as db:
            db.execute("INSERT INTO questions (id, data, version, created, updated, quiz_item_id) VALUES (?, ?, 1, ?, ?, ?)", (qid, json.dumps(d), now, now, quiz_item_id))
            db.execute("INSERT INTO versions (qid, version, ts, by, note, data) VALUES (?, 1, ?, ?, ?, ?)", (qid, now, by, note, json.dumps(d)))
        return self.get(qid)

    def update(self, qid, patch, by="", note=""):
        q = self.get(qid)
        if q is None:
            raise BankError("That question was not found.", 404)
        d = normalize({**q["data"], **patch})
        if d == q["data"]:
            return q
        now, v = time.time(), q["version"] + 1
        with self._db() as db:
            db.execute("UPDATE questions SET data = ?, version = ?, updated = ? WHERE id = ?", (json.dumps(d), v, now, qid))
            db.execute("INSERT INTO versions (qid, version, ts, by, note, data) VALUES (?, ?, ?, ?, ?, ?)", (qid, v, now, by, note or "edited", json.dumps(d)))
        return self.get(qid)

    def restore(self, qid, version, by=""):
        old = next((v for v in self.versions(qid) if v["version"] == version), None)
        if old is None:
            raise BankError("That version was not found.", 404)
        return self.update(qid, old["data"], by, f"restored version {version}")

    def bulk(self, ids, patch=None, add_tags=(), remove_tags=(), by="", note="bulk change"):
        n = 0
        for qid in ids:
            q = self.get(qid)
            if q is None:
                continue
            p = dict(patch or {})
            if add_tags or remove_tags:
                tags = [t for t in q["data"]["tags"] if t.lower() not in {x.lower() for x in remove_tags}]
                tags += [t for t in add_tags if t.lower() not in {x.lower() for x in tags}]
                p["tags"] = tags
            if self.update(qid, p, by, note)["version"] != q["version"]:
                n += 1
        return n

    def add_comment(self, qid, by, text):
        if self.get(qid) is None:
            raise BankError("That question was not found.", 404)
        text = (text or "").strip()[:2000]
        if not text:
            raise BankError("Write a comment first.")
        with self._db() as db:
            db.execute("INSERT INTO comments (qid, ts, by, text) VALUES (?, ?, ?, ?)", (qid, time.time(), by, text))

    # -- flags and re-check marks (not versions: they are about the question, not part of it)
    def replace_flags(self, qid, kinds, new):
        q = self.get(qid)
        if q is None:
            return
        keep = [f for f in q["flags"] if f["kind"] not in kinds]
        old = {(f["kind"], f["code"]): f for f in q["flags"] if f["kind"] in kinds}
        merged = []
        for f in new:
            f = {**f, "at": time.time(), "dismissed": bool(old.get((f["kind"], f["code"]), {}).get("dismissed"))}
            merged.append(f)
        with self._db() as db:
            db.execute("UPDATE questions SET flags = ? WHERE id = ?", (json.dumps(keep + merged), qid))

    def dismiss_flag(self, qid, kind, code, dismissed=True):
        q = self.get(qid)
        if q is None:
            raise BankError("That question was not found.", 404)
        for f in q["flags"]:
            if f["kind"] == kind and f["code"] == code:
                f["dismissed"] = dismissed
        with self._db() as db:
            db.execute("UPDATE questions SET flags = ? WHERE id = ?", (json.dumps(q["flags"]), qid))

    def set_recheck(self, qid, reason):
        with self._db() as db:
            db.execute("UPDATE questions SET recheck = ? WHERE id = ?", (reason, qid))

    def link_quiz_item(self, qid, item_id):
        with self._db() as db:
            db.execute("UPDATE questions SET quiz_item_id = ? WHERE id = ?", (item_id, qid))


# ---------------------------------------------------------------- listing
def open_flags(q, extra=()):
    return [f for f in q["flags"] if not f.get("dismissed")] + list(extra)


def row_of(q, stat=None):
    d = q["data"]
    stat_flags = (stat or {}).get("flags") or []
    return {"id": q["id"], "lead_in": d["lead_in"], "stem": d["stem"], "status": d["status"], "use": d["use"], "source": d["source"], "lecture": d["lecture"] or d["guide"], "region": d["region"],
            "tags": d["tags"], "difficulty": d["difficulty"], "version": q["version"], "updated_at": q["updated"], "flagged": bool(open_flags(q, stat_flags)) or bool(q["recheck"]),
            "n_flags": len(open_flags(q, stat_flags)), "needs_recheck": bool(q["recheck"]), "sample": d["sample"], "used": (stat or {}).get("n", 0)}


def matches(q, f, stat=None):
    d = q["data"]
    if f.get("status") and d["status"] != f["status"] or f.get("use") and d["use"] != f["use"] or f.get("source") and d["source"] != f["source"]:
        return False
    if f.get("region") and d["region"] != f["region"] or f.get("difficulty") and d["difficulty"] != f["difficulty"]:
        return False
    if f.get("lecture") and f["lecture"] not in (d["lecture"], d["guide"]):
        return False
    if f.get("tag") and f["tag"].lower() not in [t.lower() for t in d["tags"]]:
        return False
    if f.get("flagged") and not (open_flags(q, (stat or {}).get("flags") or []) or q["recheck"]):
        return False
    if f.get("q"):
        hay = " ".join([d["stem"], d["lead_in"], d["explanation"], d["lecture"], d["section"], " ".join(o["text"] for o in d["options"]), " ".join(d["tags"])]).lower()
        if not all(w in hay for w in words(f["q"])):
            return False
    return True


def counts(qs, stats=None):
    stats = stats or {}
    c = {"total": len(qs), "draft": 0, "approved": 0, "retired": 0, "exam_secure": 0, "flagged": 0, "needs_recheck": 0}
    for q in qs:
        d = q["data"]
        c[d["status"]] += 1
        c["exam_secure"] += d["use"] == "exam_secure"
        c["flagged"] += bool(open_flags(q, (stats.get(q["id"]) or {}).get("flags") or []))
        c["needs_recheck"] += bool(q["recheck"])
    return c


COLUMNS = ["id", "stem", "lead_in", "option_a", "option_b", "option_c", "option_d", "option_e", "answer", "explanation", "lecture", "guide", "section", "region", "tags", "difficulty",
           "source", "status", "use"]


def csv_row(q):
    d = q["data"]
    opts = {o["id"]: o["text"] for o in d["options"]}
    return [q["id"], d["stem"], d["lead_in"], *[opts.get(i, "") for i in IDS], d["answer"], d["explanation"], d["lecture"], d["guide"], d["section"], d["region"], "; ".join(d["tags"]),
            d["difficulty"], d["source"], d["status"], d["use"]]


def export_csv(qs):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(COLUMNS)
    for q in qs:
        w.writerow([("'" + c if isinstance(c, str) and c and c[0] in "=+-@" else c) for c in csv_row(q)])      # a cell that starts like a formula is neutralised
    return out.getvalue()
