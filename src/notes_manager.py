"""The Notes manager: upload, preview, publish, edit, version, archive and purge lecture notes and dissection guides, from the instructor dashboard.

The AI never edits note text: it parses, maps and flags; the instructor approves everything (publishing is always a click).
Everything that changes the live data goes through ONE path, `_swap`: build a STAGED copy (sections / guides / map / fact-check report / index with every
unchanged chunk keeping its embedding) -> a quick retrieval check on the stage -> back up the live files -> swap -> (the API reloads its search). Reversible with a
version rollback, or from the backup folder named in the audit log.

State: data/notes_manager.db (documents, versions, audit log). Originals: data/raw/notes_managed/<doc_id>/v<N>/ (never modified). Parsed content of a version:
the same folder, content.json. Archived documents keep their versions for 30 days (purge needs the typed title).

Statuses of a document: draft -> processing -> ready -> published -> archived. A published document can also have a PENDING version (processing / ready) that is not live.
"""
import json
import re
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "notes_manager.db"
MANAGED_DIR = ROOT / "data" / "raw" / "notes_managed"
BACKUP_DIR = ROOT / "data" / "archive" / "notes_swaps"
STAGING_DIR = ROOT / "data" / "staging_notes"
ARCHIVE_DAYS = 30
OVERLAP_SUGGEST = 0.6            # whole-text tf-idf cosine at which "Replace <document>" is suggested
LIMITS = {".docx": 15 << 20, ".doc": 15 << 20, ".pdf": 30 << 20, ".pptx": 60 << 20}
MAGIC = {".docx": b"PK\x03\x04", ".pptx": b"PK\x03\x04", ".pdf": b"%PDF", ".doc": b"\xd0\xcf\x11\xe0"}
EMBEDDER = None                  # an object with .encode(list, ...) -> vectors; None = the real bge-small model (tests put a fake here)
FACT_CHECK = None                # fn(sections) -> issues; None = the real fact-checker (BullsAI); tests put a fake here
SYNC = False                     # tests run the processing job in the calling thread
STEPS = ["Reading the file and keeping its headings", "Matching region and lecture by content", "Checking overlap with existing documents",
         "Fact-checking new or changed sections", "Preparing the preview"]
_LOCK = threading.RLock()
SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (doc_id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, region TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
  live_version INTEGER, display_version INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL, updated REAL NOT NULL, published_at REAL, archived_at REAL,
  grants_mode TEXT NOT NULL DEFAULT 'none', grants TEXT NOT NULL DEFAULT '[]', replaces TEXT, lecture TEXT NOT NULL DEFAULT '', created_by TEXT NOT NULL DEFAULT '',
  overlap TEXT NOT NULL DEFAULT 'null', source_name TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS versions (doc_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, created_by TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '', step TEXT NOT NULL DEFAULT '', step_i INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', flags TEXT NOT NULL DEFAULT '[]',
  n_sections INTEGER NOT NULL DEFAULT 0, source_name TEXT NOT NULL DEFAULT '', PRIMARY KEY (doc_id, version));
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT NOT NULL, ts REAL NOT NULL, user TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
"""


class ManagerError(Exception):
    """str(exc) is a message fit to show the instructor."""

    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- storage
@contextmanager
def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def live():
    """The CURRENT live paths (read from the modules, so a staged copy or a test folder is honoured)."""
    from src import auth, review
    from src.ingest import guides as G
    from src.ingest import parse as P
    from src.retrieval import index as IDX
    return {"sections": Path(P.OUT_PATH), "slides": Path(G.SLIDES_PATH), "gchunks": Path(G.CHUNKS_PATH), "map": Path(G.MAP_PATH), "index": Path(IDX.INDEX_DIR),
            "factcheck": Path(review.FACTCHECK_PATH), "openstax": Path(IDX.REFS_PATH), "users": Path(auth.USERS_PATH)}


def _read_jsonl(path):
    p = Path(path)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def _write_jsonl(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def vdir(doc_id, version):
    return MANAGED_DIR / doc_id / f"v{version}"


def log(con, doc_id, user, action, detail=""):
    con.execute("INSERT INTO audit (doc_id, ts, user, action, detail) VALUES (?, ?, ?, ?, ?)", (doc_id, time.time(), user or "", action, detail))


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:48] or "document"


def clean_title(name):
    from src.ingest import revision as R
    stem = R.v2_stem(name)
    stem = re.sub(r"\s*[-–]\s*(Notes|Reviewed|Script|Slides)\b.*$", "", stem, flags=re.I)
    return stem.strip() or "Untitled"


# ---------------------------------------------------------------- the file
def check_upload(filename, data):
    """Type and size checks. -> the lower-case extension. Raises ManagerError."""
    ext = Path(filename or "").suffix.lower()
    if ext not in LIMITS:
        raise ManagerError("Upload a .docx, .doc, .pptx or .pdf file.")
    if not data:
        raise ManagerError("That file is empty.")
    if len(data) > LIMITS[ext]:
        raise ManagerError(f"That file is {len(data) / 1048576:.1f} MB. The limit for {ext} is {LIMITS[ext] >> 20} MB.", 413)
    if not data.startswith(MAGIC[ext]):
        raise ManagerError(f"That does not look like a real {ext} file (its first bytes are wrong). Open it and save it again.")
    return ext


# ---------------------------------------------------------------- parsing (the AI reads; it never rewrites)
def _record(lecture_id, title, path, text, order, source_file, kind="notes"):
    from src.ingest import parse as P
    crumb = " > ".join([title] + [P.clean_text(x) for x in path])
    return {"lecture_id": lecture_id, "lecture_title": title, "section_path": list(path), "breadcrumb": crumb, "text": text, "text_clean": P.clean_text(text),
            "source_file": source_file, "source_type": "notes", "priority": 2, "order": order}


def convert_doc(path):
    """A .doc -> .docx with LibreOffice (headless), next to the original in a throw-away folder. Raises ManagerError if it fails."""
    import subprocess
    import tempfile
    from src import guide_images as GI
    out = Path(tempfile.mkdtemp(prefix="doc2docx_"))
    try:
        subprocess.run([GI.soffice(), "--headless", "--convert-to", "docx", "--outdir", str(out), str(path)], check=True, capture_output=True, timeout=240)
    except Exception:
        raise ManagerError("That .doc file could not be converted. Open it in Word, save it as .docx and upload that.")
    conv = out / (Path(path).stem + ".docx")
    if not conv.exists():
        raise ManagerError("That .doc file could not be converted. Open it in Word, save it as .docx and upload that.")
    return conv


def parse_notes(path, title, lecture_id):
    """A Word, PDF or slide file -> section records with the heading hierarchy kept."""
    from src.ingest import parse as P
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".docx":
        from src.ingest import revision as R
        txt = path.parent / "_text" / (slug(title) + ".txt")
        R.docx_text_copy(path, txt)
        stats = {"heading_only_dropped": 0, "parent_only": 0, "heading_text_kept": 0, "split_sections": 0, "note": ""}
        lines = P.load_lines(txt)
        if P.has_heading_styles(path):
            sections = P.parse_docx(path, title, stats)
        else:
            layout = P.detect_layout(txt.name, lines)
            sections = (P.parse_script if layout == "script" else P.parse_outline)(lines, stats)
        recs = [_record(lecture_id, title, s["section_path"], s["text"], i, path.name) for i, s in enumerate(sections, 1)]
    elif ext == ".pdf":
        recs = _parse_pdf(path, title, lecture_id)
    elif ext == ".pptx":
        from src.ingest import guides as G
        recs = []
        for s in G.read_deck(path):
            text = "\n".join(s["texts"] + s["tables"]).strip()
            if text:
                recs.append(_record(lecture_id, title, [s["title"] or f"Slide {s['n']}"], text, len(recs) + 1, path.name))
    elif ext == ".doc":
        from src import guide_images as GI
        if not GI.soffice():
            raise ManagerError("A .doc file has to be converted first and LibreOffice is not installed on this computer. Open it in Word and save it as .docx, then upload that.")
        recs = parse_notes(convert_doc(path), title, lecture_id)
        for r in recs:
            r["source_file"] = path.name
    else:
        raise ManagerError("That file type is not supported.")
    recs = [r for r in recs if r["text_clean"].strip()]
    if not recs:
        raise ManagerError("No text could be read from that file (a scanned or picture-only file has none).")
    return recs


def _parse_pdf(path, title, lecture_id):
    try:
        from pypdf import PdfReader
    except ImportError:                                   # pragma: no cover
        raise ManagerError("PDF reading needs the pypdf package, which is not installed.")
    try:
        reader = PdfReader(str(path))
        pages = [(i, (p.extract_text() or "").strip()) for i, p in enumerate(reader.pages, 1)]
    except Exception:
        raise ManagerError("That PDF could not be read (it may be damaged or password protected).")
    recs, current, buf = [], None, []

    def flush():
        if buf:
            recs.append(_record(lecture_id, title, [current or f"Page {buf[0][0]}"], "\n".join(t for _, t in buf), len(recs) + 1, path.name))
            buf.clear()
    for i, text in pages:
        if not text:
            continue
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        head = lines[0] if lines and len(lines[0]) <= 70 and not lines[0].endswith(".") else None
        if head and buf:                                   # a new short first line starts a new section
            flush()
        if head:
            current = head
            lines = lines[1:]
        elif not buf:
            current = None
        buf.append((i, "\n".join(lines)))
    flush()
    return recs


def parse_guide(path, title, class_number, file_name):
    """A .pptx dissection guide -> (slide rows, section records for the preview)."""
    from src.ingest import guides as G
    rows = []
    for s in G.read_deck(path):
        rows.append({"file": file_name, "class_number": class_number, "kind": G.classify_slide(s), **s})
    preview = []
    for r in rows:
        if r["kind"] in ("title", "end", "empty") or r.get("hidden"):
            continue
        text = G.slide_text(r) if r["texts"] or r["tables"] else ""
        if text.strip():
            preview.append({"path": [f"Slide {r['n']}"], "text": text})
    if not preview:
        raise ManagerError("No text could be read from that guide (every slide is a picture).")
    return rows, preview


# ---------------------------------------------------------------- mapping, overlap, diff
def live_documents():
    """[{doc_id, kind, title, region, version, superseded, n_sections, file, text}] for everything in the live data (notes by lecture, guides by file)."""
    from app_api import catalog
    L = live()
    notes = {}
    for r in _read_jsonl(L["sections"]):
        d = notes.setdefault(r["lecture_id"], {"doc_id": r.get("doc_id", r["lecture_id"]), "kind": "note", "title": r["lecture_title"], "version": r.get("version", 1),
                                               "superseded": r.get("superseded", ""), "file": r["source_file"], "secs": []})
        d["secs"].append({"path": " > ".join(r["section_path"]), "text": r["text_clean"]})
    out = [{**d, "region": catalog.region_of(d["title"]), "n_sections": len(d["secs"]), "text": "\n".join(s["text"] for s in d["secs"])} for d in notes.values()]
    mp = json.loads(L["map"].read_text(encoding="utf-8")) if L["map"].exists() else {"guides": []}
    slides = {}
    for r in _read_jsonl(L["slides"]):
        slides.setdefault(r["file"], []).append(r)
    from src.ingest import guides as G
    for e in mp["guides"]:
        rows = slides.get(e["file"], [])
        secs = [{"path": f"Slide {r['n']}", "text": G.slide_text(r)} for r in rows if r["kind"] not in ("title", "end", "empty") and not r.get("hidden") and G.slide_text(r).strip()]
        out.append({"doc_id": f"guide-C{e['class_number']:02d}" + ("" if e["class_label"] == f"Class {e['class_number']}" else "-" + slug(e["title"])[:12]), "kind": "guide",
                    "title": e["display_name"], "region": catalog.region_of(e["title"]), "version": 2 if "Revised" in mp.get("zip", "") else 1, "superseded": "",
                    "file": e["file"], "secs": secs, "n_sections": len(secs), "text": "\n".join(s["text"] for s in secs), "entry": e})
    return out


def map_region(title, text, others):
    """Region by the title's words, else by the most similar existing document."""
    from app_api import catalog
    r = catalog.region_of(title)
    if r != "Other" or not others:
        return r, "title"
    from src.ingest import revision as R
    sim = R.similarity_matrix([text], [o["text"] for o in others])[0]
    j = int(sim.argmax())
    return (others[j]["region"] if float(sim[j]) >= 0.15 else "Other"), f"content (closest: {others[j]['title']})"


def best_overlap(kind, text, secs, others):
    """-> {doc_id, title, score, shared_sections, sections} for the most similar live document of the same kind, or None."""
    from src.ingest import revision as R
    pool = [o for o in others if o["kind"] == kind and o["text"].strip()]
    if not pool or not text.strip():
        return None
    sim = R.similarity_matrix([text], [o["text"] for o in pool])[0]
    j = int(sim.argmax())
    d = R.diff_sections(pool[j]["secs"], [{"path": s["path"], "text": s["text"]} for s in secs])
    shared = d["unchanged"] + d["edited"]
    return {"doc_id": pool[j]["doc_id"], "title": pool[j]["title"], "score": round(float(sim[j]), 2), "shared_sections": shared, "sections": len(pool[j]["secs"]),
            "suggest_replace": float(sim[j]) >= OVERLAP_SUGGEST}


def section_diff(old_secs, new_secs):
    """Per-section diff, in the order of the new document. Each row: {path, status: unchanged|edited|rewritten|added|removed, old, new}. Sections are {path, text}."""
    from src.ingest import revision as R
    if not old_secs and not new_secs:
        return []
    rows = []
    if old_secs and new_secs:
        sim = R.similarity_matrix([s["text"] for s in old_secs], [s["text"] for s in new_secs])
        used = set()
        for j, s in enumerate(new_secs):
            i = int(sim[:, j].argmax())
            sc = float(sim[i, j])
            status = "unchanged" if sc >= R.SAME else "edited" if sc >= R.EDITED else "rewritten" if sc >= R.REWRITTEN else "added"
            if status != "added":
                used.add(i)
            rows.append({"path": s["path"], "status": status, "old": old_secs[i]["text"][:600] if status != "added" else "", "new": s["text"][:600]})
        rows += [{"path": s["path"], "status": "removed", "old": s["text"][:600], "new": ""} for i, s in enumerate(old_secs) if i not in used and float(sim[i].max()) < R.REWRITTEN]
    else:
        rows = [{"path": s["path"], "status": "added", "old": "", "new": s["text"][:600]} for s in new_secs] + \
               [{"path": s["path"], "status": "removed", "old": s["text"][:600], "new": ""} for s in old_secs]
    return rows


def diff_counts(rows):
    c = {k: 0 for k in ("unchanged", "edited", "rewritten", "added", "removed")}
    for r in rows:
        c[r["status"]] += 1
    return c


# ---------------------------------------------------------------- payloads (the parsed content of one version)
def payload_secs(payload):
    if payload["kind"] == "note":
        return [{"path": " > ".join(r["section_path"]), "text": r["text_clean"]} for r in payload["records"]]
    return [{"path": " > ".join(s["path"]), "text": s["text"]} for s in payload["preview"]]


def save_payload(doc_id, version, payload):
    d = vdir(doc_id, version)
    d.mkdir(parents=True, exist_ok=True)
    (d / "content.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_payload(doc_id, version):
    p = vdir(doc_id, version) / "content.json"
    if not p.exists():
        raise ManagerError("That version has no saved content.", 404)
    return json.loads(p.read_text(encoding="utf-8"))


def _row(con, doc_id):
    r = con.execute("SELECT * FROM docs WHERE doc_id = ?", (doc_id,)).fetchone()
    return dict(r) if r else None


def _version(con, doc_id, version):
    r = con.execute("SELECT * FROM versions WHERE doc_id = ? AND version = ?", (doc_id, version)).fetchone()
    return dict(r) if r else None


def _next_version(con, doc_id):
    return (con.execute("SELECT MAX(version) FROM versions WHERE doc_id = ?", (doc_id,)).fetchone()[0] or 0) + 1


def ensure_managed(doc_id):
    """An existing live document (the revised notes and guides) enters the manager the first time it is edited or archived: its live sections become a version."""
    with db() as con:
        if _row(con, doc_id):
            return
    doc = next((d for d in live_documents() if d["doc_id"] == doc_id), None)
    if doc is None:
        raise ManagerError("That document was not found.", 404)
    L = live()
    if doc["kind"] == "note":
        recs = [r for r in _read_jsonl(L["sections"]) if r["lecture_id"] == doc_id]
        payload = {"kind": "note", "title": doc["title"], "lecture_id": doc_id, "records": recs}
        lecture_id = doc_id
    else:
        rows = [r for r in _read_jsonl(L["slides"]) if r["file"] == doc["file"]]
        entry = doc["entry"]
        payload = {"kind": "guide", "title": doc["title"], "class_number": entry["class_number"], "file": doc["file"], "rows": rows, "entry": entry,
                   "preview": [{"path": [s["path"]], "text": s["text"]} for s in doc["secs"]]}
    now = time.time()
    with db() as con:
        con.execute("INSERT INTO docs (doc_id, kind, title, region, status, live_version, display_version, created, updated, published_at, grants_mode, source_name, lecture) "
                    "VALUES (?, ?, ?, ?, 'published', ?, ?, ?, ?, ?, 'all', ?, '')",
                    (doc_id, doc["kind"], doc["title"], doc["region"], doc["version"], doc["version"], now, now, now, doc["file"]))
        con.execute("INSERT INTO versions (doc_id, version, status, created, note, n_sections, source_name) VALUES (?, ?, 'live', ?, 'the document as it was when it entered the manager', ?, ?)",
                    (doc_id, doc["version"], now, doc["n_sections"], doc["file"]))
        log(con, doc_id, "system", "adopted", f"live version {doc['version']} entered the manager")
    save_payload(doc_id, doc["version"], payload)


# ---------------------------------------------------------------- upload and the processing job
def create_upload(user, filename, data, kind=None, replaces=None, doc_id=None):
    """A new document (or, with doc_id, a new version of one). Returns {"doc_id", "version"}; the job runs in the background (or inline when SYNC)."""
    ext = check_upload(filename, data)
    kind = kind or ("guide" if ext == ".pptx" else "note")
    if kind not in ("note", "guide"):
        raise ManagerError("Choose lecture notes or a dissection guide.")
    if kind == "guide" and ext != ".pptx":
        raise ManagerError("A dissection guide must be a .pptx file.")
    title = clean_title(filename)
    now = time.time()
    with _LOCK, db() as con:
        if doc_id:
            doc = _row(con, doc_id)
            if doc is None:
                raise ManagerError("That document was not found.", 404)
            if doc["status"] == "archived":
                raise ManagerError("Restore the document before replacing its file.", 409)
            if con.execute("SELECT 1 FROM versions WHERE doc_id = ? AND status IN ('processing', 'ready')", (doc_id,)).fetchone():
                raise ManagerError("This document already has a new version waiting. Publish or discard it first.", 409)
            version = _next_version(con, doc_id)
            kind, title = doc["kind"], doc["title"]
            if kind == "guide" and ext != ".pptx":
                raise ManagerError("A dissection guide must be a .pptx file.")
        else:
            doc_id = ("G-" if kind == "guide" else "N-") + slug(title)[:36] + "-" + uuid.uuid4().hex[:4]
            version = 1
            con.execute("INSERT INTO docs (doc_id, kind, title, region, status, display_version, created, updated, replaces, created_by, source_name) "
                        "VALUES (?, ?, ?, '', 'draft', 1, ?, ?, ?, ?, ?)", (doc_id, kind, title, now, now, replaces, user, filename))
        con.execute("INSERT INTO versions (doc_id, version, status, created, created_by, source_name, step) VALUES (?, ?, 'processing', ?, ?, ?, ?)",
                    (doc_id, version, now, user, filename, STEPS[0]))
        log(con, doc_id, user, "uploaded" if version == 1 else "replaced the file", f"{filename} ({len(data) / 1024:.0f} KB), version {version}")
    d = vdir(doc_id, version)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"original{ext}").write_bytes(data)
    if SYNC:
        process(doc_id, version)
    else:
        threading.Thread(target=process, args=(doc_id, version), daemon=True).start()
    return {"doc_id": doc_id, "version": version}


def _step(doc_id, version, i, **extra):
    with db() as con:
        con.execute("UPDATE versions SET step = ?, step_i = ? WHERE doc_id = ? AND version = ?", (STEPS[min(i, len(STEPS) - 1)], i, doc_id, version))
        con.execute("UPDATE docs SET updated = ? WHERE doc_id = ?", (time.time(), doc_id))


def process(doc_id, version):
    """The background job: parse -> map -> overlap -> fact-check the new or changed sections -> preview. Never edits the text."""
    try:
        with db() as con:
            doc, ver = _row(con, doc_id), _version(con, doc_id, version)
            con.execute("UPDATE docs SET status = CASE WHEN status = 'draft' THEN 'processing' ELSE status END WHERE doc_id = ?", (doc_id,))
        src = next(vdir(doc_id, version).glob("original.*"))
        title, kind = doc["title"], doc["kind"]
        others = [d for d in live_documents() if d["doc_id"] != doc_id]
        _step(doc_id, version, 0)
        if kind == "note":
            recs = parse_notes(src, title, doc_id)                     # a document's lecture id IS its doc_id
            payload = {"kind": "note", "title": title, "lecture_id": doc_id, "records": recs}
        else:
            from src.ingest import guides as G
            num = G.parse_name(ver["source_name"])[0] or _free_class_number()
            rows, preview = parse_guide(src, title, num, ver["source_name"])
            payload = {"kind": "guide", "title": title, "class_number": num, "file": ver["source_name"], "rows": rows, "preview": preview, "entry": None}
        secs = payload_secs(payload)
        text = "\n".join(s["text"] for s in secs)
        _step(doc_id, version, 1)
        region, how = map_region(title, text, others)
        mapping = {"region": region, "region_basis": how}
        if kind == "guide":
            payload["entry"] = guide_entry(payload, text, others)
            mapping["lecture"] = payload["entry"]["matched_lecture"]
            mapping["lecture_basis"] = payload["entry"]["method"]
        _step(doc_id, version, 2)
        overlap = best_overlap(kind, text, secs, others) if version == 1 and not doc["live_version"] else None
        _step(doc_id, version, 3)
        flags = []
        if kind == "note":
            ref = None
            if doc["live_version"]:
                ref = payload_secs(load_payload(doc_id, doc["live_version"]))
            elif overlap and overlap["suggest_replace"]:
                ref = next((d["secs"] for d in others if d["doc_id"] == overlap["doc_id"]), None)
            changed = _new_or_changed(secs, ref)
            flags = _fact_check(payload, changed)
        _step(doc_id, version, 4)
        save_payload(doc_id, version, payload)
        with db() as con:
            con.execute("UPDATE versions SET status = 'ready', step = ?, step_i = ?, flags = ?, n_sections = ? WHERE doc_id = ? AND version = ?",
                        ("Ready for preview", len(STEPS), json.dumps(flags, ensure_ascii=False), len(secs), doc_id, version))
            if not doc["live_version"]:
                con.execute("UPDATE docs SET status = 'ready', region = ?, overlap = ?, updated = ? WHERE doc_id = ?", (region, json.dumps(overlap), time.time(), doc_id))
            else:
                con.execute("UPDATE docs SET updated = ? WHERE doc_id = ?", (time.time(), doc_id))
            log(con, doc_id, "system", "processed", f"{len(secs)} sections, {len(flags)} flags, region {region}")
    except ManagerError as exc:
        _fail(doc_id, version, str(exc))
    except Exception as exc:                              # the message is kept short and has no paths
        _fail(doc_id, version, f"The file could not be processed ({type(exc).__name__}). Try saving it again or uploading another copy.")


def _fail(doc_id, version, message):
    with db() as con:
        con.execute("UPDATE versions SET status = 'failed', error = ? WHERE doc_id = ? AND version = ?", (message, doc_id, version))
        con.execute("UPDATE docs SET status = CASE WHEN live_version IS NULL THEN 'ready' ELSE status END, updated = ? WHERE doc_id = ?", (time.time(), doc_id))
        log(con, doc_id, "system", "processing failed", message)


def _free_class_number():
    from app_api import catalog
    return max([g["class_number"] for g in catalog.guides()] + [99]) + 1


def guide_entry(payload, text, others):
    """The guide-map entry of an uploaded guide: the lecture whose text is most similar (tf-idf, offline)."""
    from src.ingest import guides as G
    from src.ingest import revision as R
    lectures = [o for o in others if o["kind"] == "note"]
    matched = {"matched_lecture": "", "matched_lecture_id": "", "confidence": "unmatched", "score": 0.0, "evidence": [], "candidates": []}
    if lectures:
        sim = R.similarity_matrix([text], [o["text"] for o in lectures])[0]
        order = sim.argsort()[::-1][:3]
        best = float(sim[order[0]])
        if best >= 0.15:
            matched.update(matched_lecture=lectures[order[0]]["title"], matched_lecture_id=lectures[order[0]]["doc_id"], score=round(best, 2),
                           confidence="high" if best >= 0.3 else "medium", evidence=[f"slide text vs this lecture: tf-idf {best:.2f}"])
        matched["candidates"] = [{"lecture": lectures[i]["title"], "score": round(float(sim[i]), 2)} for i in order]
    num, title = payload["class_number"], payload["title"]
    title = re.sub(r"^Class\s+\d+\s*[-–]\s*", "", title)
    return {"class_number": num, "title": title, "display_name": G.display_name(num, title), "class_label": f"Class {num}", "file": payload["file"], "n_slides": len(payload["rows"]),
            "also_lecture_id": "", "also_lecture": "", "method": "content only: tf-idf against the lectures (uploaded in the Notes manager)", "reason": "", "note": "", "locked": False, **matched}


def _new_or_changed(secs, ref):
    """The sections that need a fact-check: all of them for a new document; for a new version only those not identical to the version it replaces."""
    if not ref:
        return list(range(len(secs)))
    from src.ingest import revision as R
    old = {R.squash(s["text"]) for s in ref}
    return [i for i, s in enumerate(secs) if R.squash(s["text"]) not in old]


def _fact_check(payload, indexes):
    """Flags for the given sections (AI only; they go to the review queue when the version is published). FACT_CHECK is replaced in tests."""
    recs = [payload["records"][i] for i in indexes if len(payload["records"][i]["text_clean"]) > 40]
    if not recs:
        return []
    if FACT_CHECK is not None:
        return FACT_CHECK(recs)
    return default_fact_check(recs)


def default_fact_check(recs):
    from concurrent.futures import ThreadPoolExecutor
    from src import llm
    from src.audit import factcheck as FC
    model, effort = llm.default_model(), "medium"
    client = llm.make_client()
    retriever = FC.Retriever(FC.load_jsonl(live()["openstax"]))
    with ThreadPoolExecutor(max_workers=4) as pool:
        res = list(pool.map(lambda s: FC.check_section(client, retriever, model, effort, s, False), recs))
        jobs = [(i, r["note"]) for r in res for i in r["issues"] if i["type"] == "factual"]
        list(pool.map(lambda j: FC.verify_issue(client, model, effort, j[0], j[1], False), jobs))
    out = []
    for r in res:
        for i in r["issues"]:
            if i["type"] == "factual" and i["verification"]["verdict"] == "wrong":
                continue
            FC.apply_severity_rules(i)
            i["tier"] = FC.tier(i)
            out.append(i)
    return out


# ---------------------------------------------------------------- reading: the list and the preview
def _access_count(doc):
    """How many students can open this document (grants in users.json; a guide also opens through its matched lecture)."""
    from src import auth
    from src.ingest import guides as G
    n = 0
    students = [u for _, u in auth.students()]
    if doc["kind"] == "note":
        return sum(doc["title"] in set(u.get("allowed_lectures", [])) for u in students)
    entry = doc.get("entry")
    for u in students:
        allowed = set(u.get("allowed_lectures", []))
        if entry and (entry.get("matched_lecture") in allowed or (entry.get("also_lecture") and entry["also_lecture"] in allowed) or G.guide_label(entry) in allowed):
            n += 1
    return n


def list_documents(kind="", region="", status="", q=""):
    """Every note and guide: the live ones (Published), the ones in the manager (draft ... archived) and the ARCHIVED first version of the notes and guides."""
    from app_api import catalog
    rows, seen = [], set()
    with db() as con:
        managed = [dict(r) for r in con.execute("SELECT * FROM docs").fetchall()]
        pending = {r["doc_id"]: dict(r) for r in con.execute("SELECT * FROM versions WHERE status IN ('processing', 'ready', 'failed') ORDER BY version").fetchall()}
    live_docs = {d["doc_id"]: d for d in live_documents()}
    for m in managed:
        seen.add(m["doc_id"])
        d = live_docs.get(m["doc_id"])
        pv = pending.get(m["doc_id"])
        rows.append({"id": m["doc_id"], "kind": m["kind"], "title": m["title"], "region": m["region"] or (d["region"] if d else "Other"), "version": m["display_version"],
                     "status": m["status"], "updated_at": m["updated"], "access_count": _access_count(d) if d and m["status"] == "published" else 0,
                     "note": ("New version " + {"processing": "being prepared", "ready": "ready to publish", "failed": "failed"}[pv["status"]]) if pv and m["status"] == "published" else "",
                     "earlier_version": bool(d and d["superseded"]), "managed": True})
    mtimes = {}
    for d in live_docs.values():
        if d["doc_id"] in seen:
            continue
        p = live()["sections"] if d["kind"] == "note" else live()["map"]
        mtimes[d["doc_id"]] = p.stat().st_mtime if p.exists() else 0
        rows.append({"id": d["doc_id"], "kind": d["kind"], "title": d["title"], "region": d["region"], "version": d["version"], "status": "published", "updated_at": mtimes[d["doc_id"]],
                     "access_count": _access_count(d), "note": "Earlier version, not in revised notes" if d["superseded"] else "", "earlier_version": bool(d["superseded"]), "managed": False})
    rows += archived_first_version(seen | set(live_docs))
    out = []
    for r in rows:
        if kind and r["kind"] != kind or region and r["region"] != region or status and r["status"] != status:
            continue
        if q and q.lower() not in (r["title"] + " " + r["region"]).lower():
            continue
        out.append(r)
    out.sort(key=lambda r: (r["kind"], _natural(r["title"])))
    return {"items": out, "regions": sorted({r["region"] for r in rows if r["region"]}), "total": len(out)}


def _natural(title):
    m = re.match(r"(Lecture|Class)\s+(\d+)", title)
    return (0 if title.startswith("Lecture") else 1, int(m.group(2)) if m else 999, title)


def archived_first_version(skip):
    """The first set of notes and guides (kept in data/archive/v1_*) as read-only Archived rows."""
    from app_api import catalog
    rows = []
    for arch in sorted((ROOT / "data" / "archive").glob("v1_*")) if (ROOT / "data" / "archive").exists() else []:
        sec = arch / "data" / "processed" / "sections.jsonl"
        seen = {}
        for r in _read_jsonl(sec):
            seen.setdefault(r["lecture_id"], (r["lecture_title"], arch.stat().st_mtime))
        for lid, (title, mt) in seen.items():
            if lid in skip:
                continue
            rows.append({"id": f"v1:{lid}", "kind": "note", "title": title, "region": catalog.region_of(title), "version": 1, "status": "archived", "updated_at": mt, "access_count": 0,
                         "note": "First version, replaced by the revised notes", "earlier_version": False, "managed": False})
    return rows


def detail(doc_id):
    """Everything the preview page shows: the document, its pending (or live) version, the section tree, mapping, overlap, flags, diff and the job steps."""
    if doc_id.startswith("v1:"):
        raise ManagerError("This is the archived first version. It is kept for reference and cannot be opened here.", 404)
    ensure_managed_if_live(doc_id)
    with db() as con:
        doc = _row(con, doc_id)
        if doc is None:
            raise ManagerError("That document was not found.", 404)
        versions = [dict(r) for r in con.execute("SELECT * FROM versions WHERE doc_id = ? ORDER BY version DESC", (doc_id,)).fetchall()]
    pending = next((v for v in versions if v["status"] in ("processing", "ready", "failed")), None)
    shown = pending or next((v for v in versions if v["status"] == "live"), versions[0] if versions else None)
    out = {"id": doc_id, "kind": doc["kind"], "title": doc["title"], "region": doc["region"], "status": doc["status"], "version": doc["display_version"], "live_version": doc["live_version"],
           "created_at": doc["created"], "updated_at": doc["updated"], "replaces": doc["replaces"], "overlap": json.loads(doc["overlap"]), "source_name": doc["source_name"],
           "shown_version": shown["version"] if shown else None, "job": None, "sections": [], "mapping": {}, "flags": {"count": 0, "items": []}, "diff": None,
           "archived_at": doc["archived_at"], "purge_after": (doc["archived_at"] + ARCHIVE_DAYS * 86400) if doc["archived_at"] else None, "grants_mode": doc["grants_mode"]}
    if shown:
        out["job"] = {"status": shown["status"], "step": shown["step"], "step_index": shown["step_i"], "steps": STEPS, "error": shown["error"], "version": shown["version"]}
        if shown["status"] in ("ready", "live", "superseded", "archived"):
            payload = load_payload(doc_id, shown["version"])
            secs = payload_secs(payload)
            out["sections"] = [{"path": s["path"].split(" > "), "text": s["text"]} for s in secs]
            flags = json.loads(shown["flags"])
            out["flags"] = {"count": len(flags), "items": [{"quote": f.get("claim_quote", ""), "issue": f.get("issue", ""), "severity": f.get("severity", ""), "tier": f.get("tier", ""),
                                                           "section": " › ".join(f.get("section_path", []))} for f in flags[:50]]}
            out["mapping"] = {"region": doc["region"], "lecture": (payload.get("entry") or {}).get("matched_lecture", ""), "title": doc["title"]}
            ref = None
            if doc["replaces"]:
                ref = next((d["secs"] for d in live_documents() if d["doc_id"] == doc["replaces"]), None)
            elif doc["live_version"] and shown["version"] != doc["live_version"]:
                ref = payload_secs(load_payload(doc_id, doc["live_version"]))
            if ref is not None:
                rows = section_diff(ref, secs)
                out["diff"] = {"against": doc["replaces"] or f"version {doc['live_version']}", "counts": diff_counts(rows), "rows": [r for r in rows if r["status"] != "unchanged"][:200]}
    return out


def ensure_managed_if_live(doc_id):
    with db() as con:
        if _row(con, doc_id):
            return
    if any(d["doc_id"] == doc_id for d in live_documents()):
        ensure_managed(doc_id)


def update_mapping(user, doc_id, region=None, replaces=None, lecture=None):
    """The instructor edits the mapping on the preview: region, the document it replaces, a guide's lecture."""
    with db() as con:
        doc = _row(con, doc_id)
        if doc is None:
            raise ManagerError("That document was not found.", 404)
        if doc["status"] not in ("ready", "draft", "processing", "published"):
            raise ManagerError("This document cannot be edited now.", 409)
        if region is not None:
            con.execute("UPDATE docs SET region = ? WHERE doc_id = ?", (region.strip()[:60], doc_id))
            log(con, doc_id, user, "changed the region", region)
        if replaces is not None:
            if replaces:
                if not any(d["doc_id"] == replaces and d["kind"] == doc["kind"] for d in live_documents()):
                    raise ManagerError("That document cannot be replaced (not found, or a different kind).")
                if doc["live_version"]:
                    raise ManagerError("A published document cannot replace another.", 409)
            con.execute("UPDATE docs SET replaces = ? WHERE doc_id = ?", (replaces or None, doc_id))
            log(con, doc_id, user, "replaces" if replaces else "no longer replaces", replaces or "")
    if lecture is not None and doc["kind"] == "guide":
        ver = max(v["version"] for v in versions_of(doc_id) if v["status"] in ("ready",))
        payload = load_payload(doc_id, ver)
        match = next((d for d in live_documents() if d["kind"] == "note" and d["title"] == lecture), None)
        if match is None and lecture:
            raise ManagerError("That lecture was not found.")
        e = payload["entry"]
        e.update(matched_lecture=match["title"] if match else "", matched_lecture_id=match["doc_id"] if match else "", confidence="high" if match else "unmatched", locked=True,
                 note="chosen by the instructor")
        save_payload(doc_id, ver, payload)
        with db() as con:
            log(con, doc_id, user, "changed the lecture mapping", lecture)


def versions_of(doc_id):
    with db() as con:
        return [dict(r) for r in con.execute("SELECT * FROM versions WHERE doc_id = ? ORDER BY version DESC", (doc_id,)).fetchall()]


def version_history(doc_id):
    """[{version, status, created_at, created_by, note, n_sections, diff: counts against the version before}] newest first."""
    ensure_managed_if_live(doc_id)
    vs = versions_of(doc_id)
    if not vs:
        raise ManagerError("That document was not found.", 404)
    out = []
    for i, v in enumerate(vs):
        prev = vs[i + 1] if i + 1 < len(vs) else None
        counts = None
        if v["status"] in ("live", "superseded", "ready") and prev and prev["status"] in ("live", "superseded", "ready"):
            try:
                counts = diff_counts(section_diff(payload_secs(load_payload(doc_id, prev["version"])), payload_secs(load_payload(doc_id, v["version"]))))
            except ManagerError:
                counts = None
        out.append({"version": v["version"], "status": v["status"], "created_at": v["created"], "created_by": v["created_by"], "note": v["note"], "n_sections": v["n_sections"], "diff": counts,
                    "source_name": v["source_name"]})
    return out


def version_diff(doc_id, version):
    vs = {v["version"]: v for v in versions_of(doc_id)}
    if version not in vs:
        raise ManagerError("That version was not found.", 404)
    older = [n for n in vs if n < version and vs[n]["status"] in ("live", "superseded", "ready")]
    new = payload_secs(load_payload(doc_id, version))
    old = payload_secs(load_payload(doc_id, max(older))) if older else []
    rows = section_diff(old, new)
    return {"version": version, "against": max(older) if older else None, "counts": diff_counts(rows), "rows": [r for r in rows if r["status"] != "unchanged"]}


def audit_log(doc_id):
    with db() as con:
        return [{"ts": r["ts"], "user": r["user"], "action": r["action"], "detail": r["detail"]} for r in con.execute("SELECT * FROM audit WHERE doc_id = ? ORDER BY id DESC", (doc_id,)).fetchall()]


# ---------------------------------------------------------------- the one path that changes live data
RELOAD = []                     # callbacks run after a swap (the API reloads its search index)
MODEL_PROVIDER = None           # fn() -> the loaded embedding model of the running API (saves loading it again)
_REAL = {}


def embedder():
    if EMBEDDER is not None:
        return EMBEDDER
    if MODEL_PROVIDER is not None:
        m = MODEL_PROVIDER()
        if m is not None:
            return m
    if "m" not in _REAL:
        from sentence_transformers import SentenceTransformer
        from src.retrieval.index import EMBED_MODEL
        _REAL["m"] = SentenceTransformer(EMBED_MODEL)
    return _REAL["m"]


def _stage_copy(doc_id):
    from src.ingest import stage as ST
    L = live()
    stage = STAGING_DIR / f"{slug(doc_id)}-{int(time.time() * 1000)}"
    S = ST.layout(stage)
    for key in ("sections", "slides", "gchunks", "map", "factcheck", "openstax"):
        if L[key].exists():
            S[key].parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(L[key], S[key])
    return stage, S


def _apply_note(S, payload, version, remove_only):
    from src.ingest import revision as R
    lid = payload["lecture_id"]
    recs = [r for r in _read_jsonl(S["sections"]) if r["lecture_id"] != lid]
    if not remove_only:
        recs += [R.with_version(r, version, doc_id=lid) for r in payload["records"]]
    recs.sort(key=lambda r: (r["lecture_title"], r["order"]))
    _write_jsonl(S["sections"], recs)


def _apply_guide(S, payload, version, remove_only, doc_id=None):
    from src.ingest import guides as G
    f = payload["file"]
    slides = [r for r in _read_jsonl(S["slides"]) if r["file"] != f]
    chunks = [c for c in _read_jsonl(S["gchunks"]) if c["source_file"] != f]
    mp = json.loads(S["map"].read_text(encoding="utf-8")) if S["map"].exists() else {"generated": "", "zip": "", "guides": []}
    mp["guides"] = [e for e in mp["guides"] if e["file"] != f]
    if not remove_only:
        e = payload["entry"]
        slides += payload["rows"]
        mp["guides"].append(e)
        mp["guides"].sort(key=lambda x: (x["class_number"], x["file"]))
        new = G.guide_chunks({f: payload["rows"]}, [e])
        for c in new:
            c["doc_id"], c["version"], c["section_id"] = doc_id or c["id"].rsplit("-s", 1)[0], version, c["id"]
        chunks += new
    _write_jsonl(S["slides"], slides)
    _write_jsonl(S["gchunks"], chunks)
    S["map"].write_text(json.dumps(mp, indent=2, ensure_ascii=False), encoding="utf-8")


def _update_factcheck(S, doc_id, title, new_records, new_flags):
    """Items of this document: still there / moved / changed (the quote is gone) in the new text; its earlier new-in-revision items are replaced by the new version's flags."""
    from src.ingest import revision as R
    if not S["factcheck"].exists():
        return
    report = json.loads(S["factcheck"].read_text(encoding="utf-8"))
    mine = lambda i: i.get("lecture_id") == doc_id or (i.get("revision") or {}).get("doc_id") == doc_id
    keep = [i for i in report["issues"] if not ((i.get("revision") or {}).get("status") == "new_in_revision" and mine(i))]
    docs = [(title, [(r["section_path"], r["text"] + "\n" + r["text_clean"]) for r in (new_records or [])])]
    for i in keep:
        if i.get("lecture_id") != doc_id:
            continue
        hit = R.find_quote(i["claim_quote"], docs) if new_records else None
        if hit:
            rec = new_records[hit[1]]
            moved = rec["breadcrumb"] != i["breadcrumb"]
            if moved:
                i.update(section_path=rec["section_path"], breadcrumb=rec["breadcrumb"], order=rec["order"])
            i["revision"] = {"status": "moved" if moved else "unchanged", "old_breadcrumb": i["breadcrumb"]}
        else:
            texts = [r["text_clean"] for r in (new_records or [])]
            sentence = R.best_sentence(i["claim_quote"], texts)
            i["revision"] = {"status": "changed", "old_lecture": i["lecture"], "old_breadcrumb": i["breadcrumb"], "new_lecture": title if new_records else "", "new_text": sentence,
                             "new_breadcrumb": next((r["breadcrumb"] for r in (new_records or []) if sentence and sentence in r["text_clean"]), "")}
    for f in (new_flags or []):
        f = dict(f)
        f["revision"] = {"status": "new_in_revision", "doc_id": doc_id}
        keep.append(f)
    report["issues"] = keep
    S["factcheck"].write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


def _fresh_chroma():
    """chromadb keeps one open client per folder; after a folder is swapped the old client points at the old files. Forget them."""
    try:
        from chromadb.api.shared_system_client import SharedSystemClient
        SharedSystemClient.clear_system_cache()
    except Exception:
        pass


def rebuild_stage_index(stage, L):
    """The staged index: every unchanged chunk keeps its stored embedding; only new or changed chunks are embedded. The live index is only READ."""
    import chromadb
    from src.ingest import stage as ST
    _fresh_chroma()
    live_chunks = _read_jsonl(Path(L["index"]) / "chunks.jsonl")
    stored = {}
    if live_chunks and (Path(L["index"]) / "chroma").exists():
        from src.retrieval.index import COLLECTION
        col = chromadb.PersistentClient(path=str(Path(L["index"]) / "chroma")).get_collection(COLLECTION)
        got = col.get(ids=[c["id"] for c in live_chunks], include=["embeddings"])
        vec = dict(zip(got["ids"], got["embeddings"]))                    # get() does not keep the requested order: pair by id
        stored = {f"{c['breadcrumb']}\n{c['text']}": [float(x) for x in vec[c["id"]]] for c in live_chunks if c["id"] in vec}
    with ST.use(stage):
        from src.retrieval import index
        chunks = index.build_chunks()
        todo = [c for c in chunks if c["embed_text"] not in stored]
        fresh = {}
        if todo:
            enc = embedder().encode([c["embed_text"] for c in todo], batch_size=32, normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True)
            fresh = {c["id"]: [float(x) for x in v] for c, v in zip(todo, enc)}
        shutil.rmtree(index.INDEX_DIR, ignore_errors=True)
        index.INDEX_DIR.mkdir(parents=True)
        _write_jsonl(index.CHUNKS_PATH, [{k: v for k, v in c.items() if k != "embed_text"} for c in chunks])
        col = chromadb.PersistentClient(path=str(index.CHROMA_DIR)).create_collection(index.COLLECTION, configuration={"hnsw": {"space": "cosine"}})
        for i in range(0, len(chunks), 500):
            b = chunks[i:i + 500]
            col.add(ids=[c["id"] for c in b], embeddings=[fresh.get(c["id"]) or stored[c["embed_text"]] for c in b], documents=[c["text"] for c in b],
                    metadatas=[index.metadata_of(c) for c in b])
    del col
    _fresh_chroma()
    return {"chunks": len(chunks), "embedded": len(todo), "reused": len(chunks) - len(todo)}


def retrieval_check(stage, doc_id, payload):
    """The quick check before a swap: the new document must be FOUND, in the first five results, by queries made from its own headings (up to 3; at least half)."""
    import os
    from src.ingest import stage as ST
    secs = payload_secs(payload)
    pick = sorted(secs, key=lambda s: -len(s["text"]))[:3]
    queries = [(s["path"].split(" > ")[-1] + " " + " ".join(s["text"].split()[:14])).strip() for s in pick]
    old = os.environ.get("RERANK")
    os.environ["RERANK"] = "off"
    try:
        with ST.use(stage):
            from src.retrieval.search import Searcher
            s = Searcher()
            s._model = embedder()
            passed = 0
            for q in queries:
                res = s.search(q, k=8)
                if res.found and any(h.chunk.get("doc_id") == doc_id for h in res.hits[:5]):
                    passed += 1
    finally:
        if old is None:
            os.environ.pop("RERANK", None)
        else:
            os.environ["RERANK"] = old
    need = (len(queries) + 1) // 2
    if passed < need:
        raise ManagerError(f"The quick retrieval check failed: the new text was found for {passed} of {len(queries)} test questions made from its own headings (it needs {need}). "
                           "Nothing was changed. Check that the text was read correctly in the preview.", 409)
    return {"queries": len(queries), "passed": passed}


def _swap(doc_id, payload, version, title, flags=None):
    """payload None = remove the document from the live data (archive). Returns {"backup", "index", ...}. The only function that writes live data files."""
    with _LOCK:
        L = live()
        stage, S = _stage_copy(doc_id)
        try:
            body = payload if payload is not None else load_payload(doc_id, _live_or_last(doc_id))
            (_apply_note(S, body, version, payload is None) if body["kind"] == "note" else _apply_guide(S, body, version, payload is None, doc_id))
            if body["kind"] == "note":
                _update_factcheck(S, doc_id, title, body["records"] if payload is not None else None, flags if payload is not None else [])
            info = rebuild_stage_index(stage, L)
            if payload is not None:
                info["check"] = retrieval_check(stage, doc_id, payload)
            bdir = BACKUP_DIR / f"{slug(doc_id)}-{int(time.time() * 1000)}"
            bdir.mkdir(parents=True, exist_ok=True)
            for key in ("sections", "slides", "gchunks", "map", "factcheck", "users"):
                if Path(L[key]).exists():
                    shutil.copy2(L[key], bdir / Path(L[key]).name)
            if Path(L["index"]).exists():
                shutil.copytree(L["index"], bdir / "index")
            for key in ("sections", "slides", "gchunks", "map", "factcheck"):
                if Path(S[key]).exists():
                    shutil.copy2(S[key], L[key])
            idx = Path(L["index"])
            new_idx, old_idx = idx.with_name(idx.name + ".new"), idx.with_name(idx.name + ".old")
            shutil.rmtree(new_idx, ignore_errors=True)
            shutil.copytree(S["index"], new_idx)
            shutil.rmtree(old_idx, ignore_errors=True)
            if idx.exists():
                idx.rename(old_idx)
            new_idx.rename(idx)
            shutil.rmtree(old_idx, ignore_errors=True)
            info["backup"] = bdir.name
        finally:
            shutil.rmtree(stage, ignore_errors=True)
        _after_swap()
        return info


def _after_swap():
    _fresh_chroma()
    try:                                          # questions that cite a section that changed or went away get "needs re-check"
        from src.qbank import integrate
        integrate.recheck_after_swap(_read_jsonl(Path(live()["index"]) / "chunks.jsonl"))
    except Exception:
        pass
    try:
        from app_api import catalog
        catalog._cache.clear()
    except Exception:
        pass
    for fn in RELOAD:
        try:
            fn()
        except Exception:
            pass


def _live_or_last(doc_id):
    with db() as con:
        r = con.execute("SELECT version FROM versions WHERE doc_id = ? AND status IN ('live', 'archived', 'superseded') ORDER BY (status = 'live') DESC, (status = 'archived') DESC, version DESC LIMIT 1",
                        (doc_id,)).fetchone()
    if r is None:
        raise ManagerError("That document has no published version.", 409)
    return r[0]


# ---------------------------------------------------------------- knock-on effects
def _norm(t):
    return re.sub(r"\s+", " ", (t or "").replace("\u2019", "'")).strip().lower()


def _recheck_fixes(title, payload):
    """Verified fixes of this lecture whose quoted line is no longer in the notes get needs_recheck (they stay in force until the instructor decides)."""
    from src import verified
    if payload is None or payload["kind"] != "note" or not Path(verified.FIXES_PATH).exists():
        return 0
    text = _norm("\n".join(r["text_clean"] + "\n" + r["text"] for r in payload["records"]))
    fixes = verified.read_jsonl(verified.FIXES_PATH)
    n = 0
    for f in fixes:
        if f.get("lecture") != title:
            continue
        gone = _norm(f.get("notes_quote", "")) not in text
        if gone and not f.get("needs_recheck"):
            f["needs_recheck"] = True
            f["recheck_reason"] = "The notes were changed: the line this decision is about is no longer in them."
            n += 1
        elif not gone and f.get("needs_recheck"):
            f.pop("needs_recheck", None)
            f.pop("recheck_reason", None)
    if n or any(not f.get("needs_recheck") and "recheck_reason" in f for f in fixes):
        verified.write_jsonl(verified.FIXES_PATH, fixes)
    return n


def _guide_progress(old_payload, new_payload, doc_id):
    """Students' saved places in a guide: kept at the step that says the same thing in the new text (by content); else back to the start with a notice."""
    from src import guide_store
    from src.ingest import revision as R
    from src.modes import guide_chat
    try:
        gs = guide_store.GuideStore()
        import sqlite3
        with sqlite3.connect(gs.path) as con:
            hist = con.execute("SELECT user, item, ref, station, count FROM guide_history WHERE kind = 'guide'").fetchall()
    except Exception:
        return 0
    if old_payload is None or old_payload["kind"] != "guide":
        return 0
    from app_api import catalog
    g = next((x for x in catalog.guides() if x.get("file") == old_payload["file"]), None)
    if g is None:
        return 0
    mine = [h for h in hist if h[2] == g["id"]]
    if not mine:
        return 0
    old_steps = guide_chat.build_steps(old_payload["rows"], old_payload["entry"]["class_label"])
    new_steps = guide_chat.build_steps(new_payload["rows"], new_payload["entry"]["class_label"]) if new_payload else []
    n = 0
    for user, item, ref, station, count in mine:
        if not new_steps:
            gs.delete_history(user, item)
            continue
        at = None
        if station < len(old_steps):
            sim = R.similarity_matrix([old_steps[station]["text"]], [s["text"] for s in new_steps])[0]
            j = int(sim.argmax())
            at = j if float(sim[j]) >= 0.5 else None
        notice = "" if at == station and len(new_steps) == len(old_steps) else (
            "This guide was updated. Your place was moved to the step that says the same thing." if at is not None
            else "This guide was updated. Your place could not be matched, so you start again at station 1.")
        gs.put_history_row(user, item, "guide", ref, g.get("title", ""), at if at is not None else 0, len(new_steps), notice=notice)
        n += 1
    return n


# ---------------------------------------------------------------- grants
def grant_label(payload, title):
    from src.ingest import guides as G
    return title if payload["kind"] == "note" else G.guide_label(payload["entry"])


def _grant(label, mode, usernames, copy_from=None):
    from src import auth
    names = [u for u, _ in auth.students()]
    if mode == "all":
        chosen = names
    elif mode == "selected":
        unknown = [u for u in (usernames or []) if u not in names]
        if unknown:
            raise ManagerError("These accounts are not students: " + ", ".join(unknown))
        chosen = list(usernames or [])
    elif mode == "same" and copy_from:
        chosen = [u for u, r in auth.students() if copy_from in r.get("allowed_lectures", [])]
    else:
        chosen = []
    users = auth.load_users()
    for u in chosen:
        cur = set(users[u].get("allowed_lectures", []))
        cur.add(label)
        users[u]["allowed_lectures"] = sorted(cur)
    if chosen:
        auth.save_users(users)
    return chosen


def _ungrant(label):
    from src import auth
    users = auth.load_users()
    changed = False
    for u, r in users.items():
        if r.get("role") == "student" and label in r.get("allowed_lectures", []):
            r["allowed_lectures"] = [x for x in r["allowed_lectures"] if x != label]
            changed = True
    if changed:
        auth.save_users(users)


# ---------------------------------------------------------------- the actions
def _pending(con, doc_id):
    r = con.execute("SELECT * FROM versions WHERE doc_id = ? AND status IN ('processing', 'ready', 'failed') ORDER BY version DESC LIMIT 1", (doc_id,)).fetchone()
    return dict(r) if r else None


def _mark_live(con, doc_id, version, user, note=None):
    con.execute("UPDATE versions SET status = 'superseded' WHERE doc_id = ? AND status = 'live'", (doc_id,))
    con.execute("UPDATE versions SET status = 'live' WHERE doc_id = ? AND version = ?", (doc_id, version))
    if note is not None:
        con.execute("UPDATE versions SET note = ?, created_by = COALESCE(NULLIF(created_by, ''), ?) WHERE doc_id = ? AND version = ?", (note, user, doc_id, version))
    con.execute("UPDATE docs SET status = 'published', live_version = ?, display_version = ?, published_at = ?, updated = ?, archived_at = NULL WHERE doc_id = ?",
                (version, version, time.time(), time.time(), doc_id))


def publish(user, doc_id, access="none", students=None):
    """Make the ready version live. access: all | selected (students = usernames) | none | same (the grants of the document it replaces). First publish only."""
    if access not in ("all", "selected", "none", "same"):
        raise ManagerError("Choose who can see it: everyone, selected students, or no one yet.")
    with _LOCK:
        with db() as con:
            doc = _row(con, doc_id)
            if doc is None:
                raise ManagerError("That document was not found.", 404)
            if doc["status"] == "archived":
                raise ManagerError("Restore this document first.", 409)
            pend = _pending(con, doc_id)
            if pend is None or pend["status"] != "ready":
                raise ManagerError("There is no prepared version to publish." if pend is None else "This version is not ready yet." if pend["status"] == "processing"
                                   else "This version failed to process. Discard it and upload the file again.", 409)
        version, first = pend["version"], doc["live_version"] is None
        if access == "same" and not doc["replaces"]:
            raise ManagerError("There is no document to copy access from.")
        payload = load_payload(doc_id, version)
        if payload["kind"] == "guide" and first:
            payload["entry"]["class_number"] = payload["class_number"]
        old_payload = load_payload(doc_id, doc["live_version"]) if doc["live_version"] else None
        replaced = next((d for d in live_documents() if d["doc_id"] == doc["replaces"]), None) if doc["replaces"] and first else None
        flags = json.loads(pend["flags"])
        info = _swap(doc_id, payload, version, doc["title"], flags)
        with db() as con:
            _mark_live(con, doc_id, version, user)
            if first:
                con.execute("UPDATE docs SET grants_mode = ? WHERE doc_id = ?", (access, doc_id))
            log(con, doc_id, user, "published", f"version {version}; {info['chunks']} passages in the index ({info['embedded']} embedded); backup {info['backup']}")
        granted = []
        if first:
            granted = _grant(grant_label(payload, doc["title"]), access, students, replaced["title"] if replaced and access == "same" else None)
            with db() as con:
                con.execute("UPDATE docs SET grants = ? WHERE doc_id = ?", (json.dumps(granted), doc_id))
                log(con, doc_id, user, "set access", f"{access}: {len(granted)} students")
        fixes = _recheck_fixes(doc["title"], payload)
        progress = _guide_progress(old_payload, payload, doc_id) if old_payload else 0
        if payload["kind"] == "guide" and old_payload is not None:
            guide_changed(doc_id, payload, version)
        if replaced:
            archive(user, replaced["doc_id"], reason=f"replaced by {doc['title']}")
        return {"doc_id": doc_id, "version": version, "granted": len(granted), "flags_added": len(flags), "fixes_to_recheck": fixes, "progress_moved": progress, "backup": info["backup"]}


def discard(user, doc_id):
    """Throw away the pending version (or a never-published document). Live data is not touched."""
    with _LOCK, db() as con:
        doc = _row(con, doc_id)
        if doc is None:
            raise ManagerError("That document was not found.", 404)
        pend = _pending(con, doc_id)
        if doc["live_version"] is None:
            if doc["status"] == "archived":
                raise ManagerError("Use Purge to delete an archived document.", 409)
            con.execute("DELETE FROM versions WHERE doc_id = ?", (doc_id,))
            con.execute("DELETE FROM docs WHERE doc_id = ?", (doc_id,))
            log(con, doc_id, user, "discarded", "the document was never published")
            shutil.rmtree(MANAGED_DIR / doc_id, ignore_errors=True)
            return {"discarded": "document"}
        if pend is None:
            raise ManagerError("There is no waiting version to discard.", 409)
        con.execute("DELETE FROM versions WHERE doc_id = ? AND version = ?", (doc_id, pend["version"]))
        log(con, doc_id, user, "discarded", f"version {pend['version']}")
        shutil.rmtree(vdir(doc_id, pend["version"]), ignore_errors=True)
        return {"discarded": "version"}


def _new_live_version(user, doc_id, payload, note, action):
    """A new version made by the instructor (edit / rollback / restore): saved, indexed, swapped in at once. Fact-check flags of the version it follows are kept."""
    with _LOCK:
        with db() as con:
            doc = _row(con, doc_id)
            if _pending(con, doc_id):
                raise ManagerError("This document has a new version waiting. Publish or discard it first.", 409)
            prev = con.execute("SELECT * FROM versions WHERE doc_id = ? AND status = 'live'", (doc_id,)).fetchone()
            version = _next_version(con, doc_id)
            flags = json.loads(prev["flags"]) if prev else []
            con.execute("INSERT INTO versions (doc_id, version, status, created, created_by, note, n_sections, flags, source_name, step, step_i) VALUES (?, ?, 'ready', ?, ?, ?, ?, ?, ?, 'Ready', ?)",
                        (doc_id, version, time.time(), user, note, len(payload_secs(payload)), json.dumps(flags), prev["source_name"] if prev else "", len(STEPS)))
        save_payload(doc_id, version, payload)
        old_payload = load_payload(doc_id, prev["version"]) if prev else None
        try:
            info = _swap(doc_id, payload, version, doc["title"], flags)
        except Exception:
            with db() as con:
                con.execute("DELETE FROM versions WHERE doc_id = ? AND version = ?", (doc_id, version))
            shutil.rmtree(vdir(doc_id, version), ignore_errors=True)
            raise
        with db() as con:
            _mark_live(con, doc_id, version, user, note)
            log(con, doc_id, user, action, f"version {version}: {note}; backup {info['backup']}")
        fixes = _recheck_fixes(doc["title"], payload)
        progress = _guide_progress(old_payload, payload, doc_id) if old_payload else 0
        if payload["kind"] == "guide":
            guide_changed(doc_id, payload, version)
        return {"doc_id": doc_id, "version": version, "fixes_to_recheck": fixes, "progress_moved": progress, "backup": info["backup"]}


def edit_sections(user, doc_id, edits, note=""):
    """The in-browser editor: edits = [{"index": section number in the preview, "text": new text}]. Saves a NEW version and publishes it (the instructor's own edit is the approval)."""
    ensure_managed_if_live(doc_id)
    with db() as con:
        doc = _row(con, doc_id)
    if doc is None:
        raise ManagerError("That document was not found.", 404)
    if doc["status"] != "published":
        raise ManagerError("Only a published document can be edited. Publish it first.", 409)
    if doc["kind"] != "note":
        raise ManagerError("Dissection guides are changed by uploading a new file (Replace file).", 409)
    payload = load_payload(doc_id, doc["live_version"])
    recs = payload["records"]
    changed = 0
    for e in edits or []:
        i, text = e.get("index"), (e.get("text") or "").strip()
        if not isinstance(i, int) or not 0 <= i < len(recs):
            raise ManagerError("One of the edited sections was not found.")
        if not text:
            raise ManagerError("A section cannot be empty. To remove material, replace the file.")
        if text != recs[i]["text_clean"].strip():
            recs[i]["text"] = text
            recs[i]["text_clean"] = text
            changed += 1
    if not changed:
        raise ManagerError("Nothing was changed.")
    return _new_live_version(user, doc_id, payload, (note or f"edited {changed} section{'s' if changed != 1 else ''} in the browser").strip()[:200], "edited")


def rollback(user, doc_id, version):
    ensure_managed_if_live(doc_id)
    with db() as con:
        doc = _row(con, doc_id)
        v = _version(con, doc_id, version) if doc else None
    if doc is None or v is None:
        raise ManagerError("That version was not found.", 404)
    if doc["status"] != "published":
        raise ManagerError("Only a published document can be rolled back.", 409)
    if version == doc["live_version"]:
        raise ManagerError("That version is already live.", 409)
    if v["status"] not in ("superseded", "live"):
        raise ManagerError("That version cannot be restored.", 409)
    return _new_live_version(user, doc_id, load_payload(doc_id, version), f"rolled back to version {version}", "rolled back")


def archive(user, doc_id, reason=""):
    """Removed from answers at once (the index is rebuilt without it). Restorable for 30 days."""
    ensure_managed_if_live(doc_id)
    with _LOCK:
        with db() as con:
            doc = _row(con, doc_id)
        if doc is None:
            raise ManagerError("That document was not found.", 404)
        if doc["status"] == "archived":
            raise ManagerError("This document is already archived.", 409)
        old_payload = None
        if doc["live_version"] is not None:
            old_payload = load_payload(doc_id, doc["live_version"])
            info = _swap(doc_id, None, doc["live_version"], doc["title"])
        else:
            info = {"backup": ""}
        with db() as con:
            con.execute("UPDATE versions SET status = 'archived' WHERE doc_id = ? AND status = 'live'", (doc_id,))
            con.execute("UPDATE docs SET status = 'archived', archived_at = ?, updated = ? WHERE doc_id = ?", (time.time(), time.time(), doc_id))
            log(con, doc_id, user, "archived", (reason + "; " if reason else "") + (f"backup {info['backup']}" if info["backup"] else "never published"))
        _guide_progress(old_payload, None, doc_id) if old_payload else None
        return {"doc_id": doc_id, "restorable_until": time.time() + ARCHIVE_DAYS * 86400}


def restore(user, doc_id):
    with _LOCK:
        with db() as con:
            doc = _row(con, doc_id)
        if doc is None:
            raise ManagerError("That document was not found.", 404)
        if doc["status"] != "archived":
            raise ManagerError("This document is not archived.", 409)
        if doc["archived_at"] and time.time() - doc["archived_at"] > ARCHIVE_DAYS * 86400:
            raise ManagerError(f"This document was archived more than {ARCHIVE_DAYS} days ago and can no longer be restored. Upload the file again.", 409)
        if doc["live_version"] is None:
            with db() as con:
                con.execute("UPDATE docs SET status = 'ready', archived_at = NULL WHERE doc_id = ?", (doc_id,))
                log(con, doc_id, user, "restored", "")
            return {"doc_id": doc_id, "version": None}
        version = doc["live_version"]
        payload = load_payload(doc_id, version)
        with db() as con:
            flags = json.loads(_version(con, doc_id, version)["flags"])
        info = _swap(doc_id, payload, version, doc["title"], flags)
        with db() as con:
            con.execute("UPDATE versions SET status = 'live' WHERE doc_id = ? AND version = ?", (doc_id, version))
            con.execute("UPDATE docs SET status = 'published', archived_at = NULL, updated = ? WHERE doc_id = ?", (time.time(), doc_id))
            log(con, doc_id, user, "restored", f"version {version}; backup {info['backup']}")
        _recheck_fixes(doc["title"], payload)
        return {"doc_id": doc_id, "version": version}


def purge(user, doc_id, confirm_title):
    """Permanently deletes an ARCHIVED document: its versions, parsed content and uploaded originals. The audit trail stays."""
    with _LOCK, db() as con:
        doc = _row(con, doc_id)
        if doc is None:
            raise ManagerError("That document was not found.", 404)
        if doc["status"] != "archived":
            raise ManagerError("Archive the document first. Only archived documents can be purged.", 409)
        if (confirm_title or "").strip() != doc["title"]:
            raise ManagerError("Type the document's title exactly to confirm.")
        label = None
        try:
            if doc["live_version"] is not None:
                label = grant_label(load_payload(doc_id, doc["live_version"]), doc["title"])
        except ManagerError:
            label = doc["title"]
        con.execute("DELETE FROM versions WHERE doc_id = ?", (doc_id,))
        con.execute("DELETE FROM docs WHERE doc_id = ?", (doc_id,))
        log(con, doc_id, user, "purged", f"{doc['title']} (all versions and original files deleted)")
    shutil.rmtree(MANAGED_DIR / doc_id, ignore_errors=True)
    if label:
        _ungrant(label)
    return {"doc_id": doc_id}


def guide_changed(doc_id, payload, version):
    """A dissection guide's file was replaced or restored: send every approved mark back to draft (the marks were drawn on the old pictures), then render and crop its slides again when the
    original file and LibreOffice are there. Best effort: never fails a publish. -> {"rendered", "demoted"}"""
    out = {"rendered": False, "demoted": 0}
    try:
        from app_api import catalog
        from src import guide_images as GI
        from src import guide_marks as GM
        from src.modes import guide_slides as GS
        g = next((x for x in catalog.guides() if x["file"] == payload["file"]), None)
        if g is None:
            return out
        out["demoted"] = GM.MarkStore().demote_all(g["id"])
        orig = next(vdir(doc_id, version).glob("original.pptx"), None)
        if orig is not None and GI.soffice():
            stations = GS.build_stations(payload["rows"], g["entry"]["class_label"])
            by_slide = {n: st["steps"] for st in stations for n in st["slides"]}
            out["rendered"] = bool(GI.build_guide(orig, g["id"], payload["rows"], lambda n: by_slide.get(n, []), force=True).get("crops", 0) >= 0)
    except Exception:
        pass
    return out
