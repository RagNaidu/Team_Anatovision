"""Step-by-step marks on the guide slide images: arrows, cut lines, highlights (ellipses) and numbered label pins.

Coordinates are normalised 0-1 on the CROPPED picture it belongs to (x from the left, y from the top), so a mark lands on the same spot at any display size. A mark belongs to one
picture (slide + crop number). Marks made before the slides were cropped are in slide coordinates (`space` = "slide") until `remap_to_crops` moves them; one that falls outside every
crop becomes a flagged draft. Each mark belongs to one slide, may be linked to a step of the station that holds the slide (`step`, 0-based; None = always shown with the image), and is
`draft` or `approved`. Only APPROVED marks ever reach a student (`student_marks`). Auto-drafts read from the pptx shapes are always drafts; editing an approved
mark sends it back to draft. Marks are drawn by an instructor or read from his own slides: nothing here is AI-generated.

Store: data/guide_annotations.db (git-ignored with the rest of data/).
"""
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("ANATOVISION_MARKS_PATH") or ROOT / "data" / "guide_annotations.db")
KINDS = ("arrow", "cut", "highlight", "label")
STATUSES = ("draft", "approved")
SCHEMA = """
CREATE TABLE IF NOT EXISTS marks (id TEXT PRIMARY KEY, guide_id TEXT NOT NULL, slide INTEGER NOT NULL, kind TEXT NOT NULL, geom TEXT NOT NULL, text TEXT NOT NULL DEFAULT '',
  step INTEGER, ord INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'draft', author TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1,
  source TEXT NOT NULL DEFAULT 'manual', created REAL NOT NULL, updated REAL NOT NULL, crop INTEGER NOT NULL DEFAULT 1, flag TEXT NOT NULL DEFAULT '', space TEXT NOT NULL DEFAULT 'crop');
CREATE TABLE IF NOT EXISTS crop_review (guide_id TEXT NOT NULL, slide INTEGER NOT NULL, crop INTEGER NOT NULL, by TEXT NOT NULL DEFAULT '', ts REAL NOT NULL, PRIMARY KEY (guide_id, slide, crop));
CREATE INDEX IF NOT EXISTS marks_slide ON marks (guide_id, slide);
CREATE TABLE IF NOT EXISTS history (mark_id TEXT NOT NULL, version INTEGER NOT NULL, ts REAL NOT NULL, by TEXT NOT NULL, action TEXT NOT NULL, data TEXT NOT NULL);
"""


class MarkError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def _unit(v, name):
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise MarkError(f"{name} must be a number between 0 and 1.")
    if not 0.0 <= v <= 1.0:
        raise MarkError(f"{name} must be between 0 and 1 (a position on the slide).")
    return round(v, 4)


def _pt(p, name):
    if not isinstance(p, (list, tuple)) or len(p) != 2:
        raise MarkError(f"{name} must be a point [x, y].")
    return [_unit(p[0], name + " x"), _unit(p[1], name + " y")]


def clean_geom(kind, geom):
    """Validate and normalise a mark's geometry. Raises MarkError."""
    if kind not in KINDS:
        raise MarkError("A mark is an arrow, a cut line, a highlight or a label.")
    g = geom or {}
    if kind == "arrow":
        a, b = _pt(g.get("from"), "from"), _pt(g.get("to"), "to")
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) < 0.01:
            raise MarkError("An arrow needs two different points.")
        return {"from": a, "to": b}
    if kind == "cut":
        pts = [_pt(p, "point") for p in (g.get("points") or [])]
        if not 2 <= len(pts) <= 40:
            raise MarkError("A cut line needs 2 to 40 points.")
        return {"points": pts}
    if kind == "highlight":
        rx, ry = _unit(g.get("rx"), "rx"), _unit(g.get("ry"), "ry")
        if rx < 0.005 or ry < 0.005:
            raise MarkError("A highlight needs a visible size.")
        return {"cx": _unit(g.get("cx"), "cx"), "cy": _unit(g.get("cy"), "cy"), "rx": rx, "ry": ry}
    return {"x": _unit(g.get("x"), "x"), "y": _unit(g.get("y"), "y")}


def scale_geom(kind, geom, w, h):
    """Normalised geometry -> pixel geometry for an image of w x h (how every display sizes a mark). Ellipse radii scale on each axis."""
    P = lambda p: [round(p[0] * w, 2), round(p[1] * h, 2)]
    if kind == "arrow":
        return {"from": P(geom["from"]), "to": P(geom["to"])}
    if kind == "cut":
        return {"points": [P(p) for p in geom["points"]]}
    if kind == "highlight":
        return {"cx": round(geom["cx"] * w, 2), "cy": round(geom["cy"] * h, 2), "rx": round(geom["rx"] * w, 2), "ry": round(geom["ry"] * h, 2)}
    return {"x": round(geom["x"] * w, 2), "y": round(geom["y"] * h, 2)}


class MarkStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            tables = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
            if "marks" in tables:
                self._migrate(db)
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

    def _migrate(self, db):
        cols = {r["name"] for r in db.execute("PRAGMA table_info(marks)").fetchall()}
        if "crop" not in cols:                                    # an older database: its marks are in SLIDE coordinates until remap_to_crops moves them
            db.execute("ALTER TABLE marks ADD COLUMN crop INTEGER NOT NULL DEFAULT 1")
            db.execute("ALTER TABLE marks ADD COLUMN flag TEXT NOT NULL DEFAULT ''")
            db.execute("ALTER TABLE marks ADD COLUMN space TEXT NOT NULL DEFAULT 'slide'")

    @staticmethod
    def _m(r):
        return {"id": r["id"], "guide_id": r["guide_id"], "slide": r["slide"], "kind": r["kind"], "geom": json.loads(r["geom"]), "text": r["text"], "step": r["step"], "order": r["ord"],
                "status": r["status"], "author": r["author"], "version": r["version"], "source": r["source"], "updated": r["updated"], "crop": r["crop"], "flag": r["flag"], "space": r["space"]}

    def _log(self, db, m, by, action):
        db.execute("INSERT INTO history VALUES (?, ?, ?, ?, ?, ?)", (m["id"], m["version"], time.time(), by, action, json.dumps({k: m[k] for k in ("kind", "geom", "text", "step", "status", "slide")})))

    def get(self, mark_id):
        with self._db() as db:
            r = db.execute("SELECT * FROM marks WHERE id = ?", (mark_id,)).fetchone()
        return self._m(r) if r else None

    def list(self, guide_id, slides=None, status=None):
        with self._db() as db:
            rows = db.execute("SELECT * FROM marks WHERE guide_id = ? ORDER BY slide, ord, created", (guide_id,)).fetchall()
        out = [self._m(r) for r in rows]
        if slides is not None:
            out = [m for m in out if m["slide"] in set(slides)]
        return [m for m in out if not status or m["status"] == status]

    def history(self, mark_id):
        with self._db() as db:
            return [{"version": r["version"], "ts": r["ts"], "by": r["by"], "action": r["action"], "data": json.loads(r["data"])} for r in
                    db.execute("SELECT * FROM history WHERE mark_id = ? ORDER BY version", (mark_id,)).fetchall()]

    def create(self, guide_id, slide, kind, geom, text="", step=None, by="", source="manual", status="draft", crop=1):
        g = clean_geom(kind, geom)
        text = (text or "").strip()[:80]
        if kind == "label" and not text:
            raise MarkError("A label needs its text.")
        if step is not None and (not isinstance(step, int) or step < 0):
            raise MarkError("The step must be a number from 0.")
        now, mid = time.time(), "m-" + uuid.uuid4().hex[:10]
        with self._db() as db:
            nxt = (db.execute("SELECT COALESCE(MAX(ord), -1) + 1 FROM marks WHERE guide_id = ? AND slide = ? AND crop = ?", (guide_id, slide, crop)).fetchone()[0])
            db.execute("INSERT INTO marks (id, guide_id, slide, kind, geom, text, step, ord, status, author, version, source, created, updated, crop, flag, space) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, '', 'crop')",
                       (mid, guide_id, int(slide), kind, json.dumps(g), text, step, nxt, status, by, source, now, now, int(crop)))
            m = self._m(db.execute("SELECT * FROM marks WHERE id = ?", (mid,)).fetchone())
            self._log(db, m, by, "created" if source == "manual" else "auto-drafted")
        return m

    def update(self, mark_id, patch, by=""):
        m = self.get(mark_id)
        if m is None:
            raise MarkError("That mark was not found.", 404)
        geom = clean_geom(m["kind"], patch["geom"]) if "geom" in patch else m["geom"]
        text = (patch.get("text", m["text"]) or "").strip()[:80]
        if m["kind"] == "label" and not text:
            raise MarkError("A label needs its text.")
        step = patch.get("step", m["step"])
        if step is not None and (not isinstance(step, int) or step < 0):
            raise MarkError("The step must be a number from 0.")
        if (geom, text, step) == (m["geom"], m["text"], m["step"]):
            return m
        with self._db() as db:                          # an edit always sends an approved mark back to draft: the instructor approves what students see
            clear = "flag = ''" if "geom" in patch else "flag = flag"
            db.execute(f"UPDATE marks SET geom = ?, text = ?, step = ?, status = 'draft', version = version + 1, author = ?, updated = ?, {clear}, space = CASE WHEN ? THEN 'crop' ELSE space END WHERE id = ?",
                       (json.dumps(geom), text, step, by or m["author"], time.time(), 1 if "geom" in patch else 0, mark_id))
            m = self._m(db.execute("SELECT * FROM marks WHERE id = ?", (mark_id,)).fetchone())
            self._log(db, m, by, "edited")
        return m

    def delete(self, mark_id, by=""):
        m = self.get(mark_id)
        if m is None:
            raise MarkError("That mark was not found.", 404)
        with self._db() as db:
            self._log(db, m, by, "deleted")
            db.execute("DELETE FROM marks WHERE id = ?", (mark_id,))

    def reorder(self, guide_id, slide, ids, crop=None):
        have = [m["id"] for m in self.list(guide_id, [slide]) if crop is None or m["crop"] == crop]
        if sorted(have) != sorted(ids):
            raise MarkError("The order must list every mark on that slide once.")
        with self._db() as db:
            for i, mid in enumerate(ids):
                db.execute("UPDATE marks SET ord = ? WHERE id = ?", (i, mid))

    def set_status(self, guide_id, slides, status, by=""):
        """Approve (or send back to draft) every mark on these slides. -> number changed."""
        if status not in STATUSES:
            raise MarkError("Unknown status.")
        n = 0
        for m in self.list(guide_id, slides):
            if status == "approved" and (m["flag"] or m["space"] != "crop"):
                continue                                        # a flagged mark (outside the crop) is never approved by a bulk action: the instructor fixes or deletes it first
            if m["status"] != status:
                with self._db() as db:
                    db.execute("UPDATE marks SET status = ?, version = version + 1, updated = ? WHERE id = ?", (status, time.time(), m["id"]))
                    m2 = self._m(db.execute("SELECT * FROM marks WHERE id = ?", (m["id"],)).fetchone())
                    self._log(db, m2, by, "approved" if status == "approved" else "set to draft")
                n += 1
        return n

    def demote_all(self, guide_id, by="system"):
        """The guide file was replaced: every approved mark goes back to draft until the instructor looks at it again."""
        return self.set_status(guide_id, sorted({m["slide"] for m in self.list(guide_id)}), "draft", by)

    def replace_auto_drafts(self, guide_id, slide, marks, by="auto", crop=1, source="auto"):
        """Auto-drafts of one picture are redone: older marks of the same source that are still drafts are removed; approved and hand-made marks are never touched."""
        for m in self.list(guide_id, [slide]):
            if m["source"] == source and m["status"] == "draft" and m["crop"] == crop:
                self.delete(m["id"], by)
        return [self.create(guide_id, slide, k["kind"], k["geom"], k.get("text", ""), k.get("step"), by, source, "draft", crop) for k in marks]

    # -- picture checks (a low-confidence crop is shown to students only after the instructor has looked at it)
    def reviewed(self, guide_id):
        with self._db() as db:
            return {(r["slide"], r["crop"]) for r in db.execute("SELECT slide, crop FROM crop_review WHERE guide_id = ?", (guide_id,)).fetchall()}

    def set_reviewed(self, guide_id, slide, crop, ok=True, by=""):
        with self._db() as db:
            if ok:
                db.execute("INSERT OR REPLACE INTO crop_review VALUES (?, ?, ?, ?, ?)", (guide_id, slide, crop, by, time.time()))
            else:
                db.execute("DELETE FROM crop_review WHERE guide_id = ? AND slide = ? AND crop = ?", (guide_id, slide, crop))

    def remap_to_crops(self, guide_id, crops_of, by="system"):
        """Marks drawn on the whole slide (space = "slide") are moved onto the cropped pictures. crops_of(slide) = [{"k", "box"}]. A mark whose anchor lies inside a crop is converted and keeps
        its status; a mark partly outside is converted, set to draft and flagged; a mark outside every crop becomes a flagged draft (its coordinates stay as they were). -> {"moved", "flagged"}"""
        moved = flagged = 0
        for m in self.list(guide_id):
            if m["space"] != "slide":
                continue
            crops = crops_of(m["slide"])
            hit = next((c for c in crops if inside(anchor(m["kind"], m["geom"]), c["box"])), None)
            with self._db() as db:
                if hit is None:
                    db.execute("UPDATE marks SET status = 'draft', flag = ?, updated = ? WHERE id = ?", ("Outside the cropped picture: move it onto the picture or delete it.", time.time(), m["id"]))
                    flagged += 1
                else:
                    g, partly = to_crop_geom(m["kind"], m["geom"], hit["box"])
                    db.execute("UPDATE marks SET geom = ?, crop = ?, space = 'crop', status = ?, flag = ?, version = version + 1, updated = ? WHERE id = ?",
                               (json.dumps(g), hit["k"], "draft" if partly else m["status"], "Partly outside the cropped picture: check it." if partly else "", time.time(), m["id"]))
                    moved += 1
                    flagged += bool(partly)
        return {"moved": moved, "flagged": flagged}


def anchor(kind, geom):
    """The point that decides which crop a slide-coordinate mark belongs to."""
    if kind == "arrow":
        return geom["to"]
    if kind == "cut":
        return geom["points"][-1]
    if kind == "highlight":
        return [geom["cx"], geom["cy"]]
    return [geom["x"], geom["y"]]


def inside(p, box, tol=0.0):
    return box[0] - tol <= p[0] <= box[2] + tol and box[1] - tol <= p[1] <= box[3] + tol


def to_crop_geom(kind, geom, box):
    """Slide-normalised geometry -> crop-normalised, clamped to the crop. -> (geom, partly_outside)"""
    bw, bh = (box[2] - box[0]) or 1e-9, (box[3] - box[1]) or 1e-9
    partly = False

    def P(p):
        nonlocal partly
        x, y = (p[0] - box[0]) / bw, (p[1] - box[1]) / bh
        if not (0 <= x <= 1 and 0 <= y <= 1):
            partly = True
        return [round(min(1, max(0, x)), 4), round(min(1, max(0, y)), 4)]
    if kind == "arrow":
        return {"from": P(geom["from"]), "to": P(geom["to"])}, partly
    if kind == "cut":
        return {"points": [P(p) for p in geom["points"]]}, partly
    if kind == "highlight":
        c = P([geom["cx"], geom["cy"]])
        return {"cx": c[0], "cy": c[1], "rx": round(min(1, geom["rx"] / bw), 4), "ry": round(min(1, geom["ry"] / bh), 4)}, partly
    return dict(zip(("x", "y"), P([geom["x"], geom["y"]]))), partly


def student_marks(marks):
    """What a student may receive: approved marks only, with no author, version or status."""
    return [{"id": m["id"], "slide": m["slide"], "crop": m["crop"], "kind": m["kind"], "geom": m["geom"], "text": m["text"], "step": m["step"], "n": i + 1}
            for i, m in enumerate(x for x in marks if x["status"] == "approved" and x["space"] == "crop" and not x["flag"])]
