"""Add or replace lecture notes from the web UI WITHOUT ever touching data/raw/notes (Dr. Inglis's originals).

An upload is saved as a new version under data/raw/notes_uploaded/<lecture_id>/v001__<name>.docx (older versions are kept),
recorded in data/raw/notes_uploaded/manifest.json, parsed with the normal parser, merged into data/processed/sections.jsonl
(replacing that lecture's sections, or adding a new lecture) and re-indexed for that lecture only. Uploaded sections are
source_type "notes" and carry `uploaded: <date>` so the UI can show an "uploaded" badge.

Re-running `python -m src.ingest.parse` rebuilds sections.jsonl from the originals and then re-applies the active uploads
(apply_uploads), so an upload is never lost by a re-parse. Nothing here deletes a file.

.doc uploads need LibreOffice (not installed here): they are saved as a version, the reason is recorded, and the UI asks for a
.docx instead. File names must start "Lecture NN - ..." (or "ANA407 Class NN - ...") so the lecture can be identified.
"""
import hashlib
import json
import re
import tempfile
from datetime import date
from pathlib import Path

import docx

from src.ingest import parse

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = ROOT / "data" / "raw" / "notes_uploaded"
SECTIONS_PATH = parse.OUT_PATH
ALLOWED_SUFFIXES = (".docx", ".doc")
MAX_BYTES = 25 * 1024 * 1024


class UploadError(ValueError):
    """A problem the person who uploaded can fix (shown as-is in the UI)."""


def manifest_path():
    return UPLOAD_DIR / "manifest.json"


def load_manifest():
    try:
        return json.loads(manifest_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_manifest(manifest):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    tmp = manifest_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(manifest_path())


def clean_name(filename):
    """The file name only (no folders), with characters that could escape the upload folder removed."""
    name = Path(str(filename).replace("\\", "/")).name
    name = re.sub(r"[^\w .,()&+'-]", "_", name).strip(" .")
    return name or "upload.docx"


def identify(filename):
    """-> (stem, lecture_title, lecture_id) from the file name, or UploadError."""
    stem = Path(clean_name(filename)).stem
    try:
        title, lecture_id = parse.lecture_info(stem)
    except (AttributeError, TypeError):
        raise UploadError(f'The file name "{filename}" does not say which lecture it is. Start it with "Lecture 09 - The '
                          'Hand" (a number and a title) or "ANA407 Class 28 - ...".') from None
    return stem, title, lecture_id


def validate(filename, data):
    if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:
        raise UploadError("Upload a Word file (.docx, or .doc).")
    if not data:
        raise UploadError("That file is empty.")
    if len(data) > MAX_BYTES:
        raise UploadError(f"That file is larger than {MAX_BYTES // 2 ** 20} MB.")
    if Path(filename).suffix.lower() == ".docx" and data[:2] != b"PK":
        raise UploadError("That file is not a real .docx (Word) document.")
    return identify(filename)


def parse_upload(path, stem):
    """Parse a stored upload with the normal parser. -> records (without the upload fields)."""
    path = Path(path)
    if path.suffix.lower() == ".doc":
        if parse.find_soffice() is None:
            raise UploadError("This is a .doc file and LibreOffice (needed to read it) is not installed here. "
                              "Save it as .docx in Word and upload that.")
    try:
        document = docx.Document(str(path)) if path.suffix.lower() == ".docx" else None
    except Exception as exc:                                    # a corrupt or password-protected file
        raise UploadError(f"Word could not open that file ({type(exc).__name__}).") from None
    with tempfile.TemporaryDirectory(prefix="anatovision_upload_") as tmp:
        text_copy = Path(tmp) / f"{stem}.txt"
        lines = [parse.para_text(p) for p in document.paragraphs] if document is not None else []
        text_copy.write_text("\n".join(lines), encoding="utf-8")
        records, _stats = parse.parse_file(text_copy, orig=path)
    if not records:
        raise UploadError("No text could be read from that file.")
    return records


def stamp(records, version, original_name, uploaded):
    for r in records:
        r.update(source_file=original_name, uploaded=uploaded, upload_version=version)
    return records


def merge_lecture(records, new_records):
    """Replace this lecture's records in place (or append it as a new lecture). Returns a new list."""
    if not new_records:
        return list(records)
    lecture_id = new_records[0]["lecture_id"]
    first = next((i for i, r in enumerate(records) if r["lecture_id"] == lecture_id), None)
    rest = [r for r in records if r["lecture_id"] != lecture_id]
    at = len(rest) if first is None else first
    return rest[:at] + new_records + rest[at:]


def active_files(manifest=None):
    """[(lecture_id, entry, version record, path)] for every lecture whose newest version was parsed successfully."""
    manifest = load_manifest() if manifest is None else manifest
    out = []
    for lecture_id, entry in manifest.items():
        v = next((v for v in entry["versions"] if v["version"] == entry.get("active")), None)
        if v:
            out.append((lecture_id, entry, v, UPLOAD_DIR / lecture_id / v["file"]))
    return out


def apply_uploads(records):
    """Re-apply every active upload on top of freshly parsed originals (used by `python -m src.ingest.parse`)."""
    for lecture_id, entry, v, path in active_files():
        if not path.exists():
            continue
        try:
            new = parse_upload(path, entry["stem"])
        except UploadError:
            continue
        records = merge_lecture(records, stamp(new, v["version"], v["original_name"], v["uploaded"]))
    return records


def read_sections(path=None):
    p = Path(path or SECTIONS_PATH)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def write_sections(records, path=None):
    p = Path(path or SECTIONS_PATH)
    tmp = p.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    tmp.replace(p)


def add_or_replace(filename, data, model=None, progress=None, today=None, reindex=True):
    """Save, parse and index one uploaded lecture file. -> {lecture, lecture_id, version, replaced, sections, index}.

    Raises UploadError for anything the uploader can fix. The new version is made active only after parsing succeeded,
    so a bad upload never changes what students can search.
    """
    say = progress or (lambda f, m: None)
    today = today or date.today().isoformat()
    stem, title, lecture_id = validate(filename, data)
    manifest = load_manifest()
    current = next((v for v in manifest.get(lecture_id, {}).get("versions", []) if v["version"] == manifest[lecture_id].get("active")), None) \
        if lecture_id in manifest else None
    if current and current["sha256"] == hashlib.sha256(data).hexdigest():
        raise UploadError(f"This file is identical to version {current['version']} already in use; nothing was changed.")
    say(0.02, "Saving a new version (older versions are kept)")
    entry = manifest.setdefault(lecture_id, {"title": title, "stem": stem, "active": None, "versions": []})
    version = max([v["version"] for v in entry["versions"]] + [0]) + 1
    stored = f"v{version:03d}__{clean_name(filename)}"
    folder = UPLOAD_DIR / lecture_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / stored
    if path.exists():
        raise UploadError("A file with that version name already exists; nothing was overwritten.")
    path.write_bytes(data)
    record = {"version": version, "file": stored, "original_name": clean_name(filename), "uploaded": today,
              "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "sections": 0, "error": ""}
    entry["versions"].append(record)
    entry["title"], entry["stem"] = title, stem
    try:
        say(0.1, "Reading the document")
        records = stamp(parse_upload(path, stem), version, record["original_name"], today)
    except UploadError as exc:
        record["error"] = str(exc)
        save_manifest(manifest)
        raise
    record["sections"] = len(records)
    existing = read_sections()
    replaced = any(r["lecture_id"] == lecture_id for r in existing)
    entry["active"] = version
    save_manifest(manifest)
    write_sections(merge_lecture(existing, records))
    say(0.2, f"Parsed {len(records)} sections")
    index = None
    if reindex:
        from src.retrieval import index as idx
        index = idx.update_lecture(lecture_id, records, model=model,
                                   progress=lambda f, m: say(0.2 + 0.8 * f, m))
    say(1.0, "Done")
    return {"lecture": title, "lecture_id": lecture_id, "version": version, "replaced": replaced,
            "sections": len(records), "index": index}


def library(sections=None, report_dates=None):
    """One row per lecture in sections.jsonl for the notes library table."""
    sections = sections if sections is not None else read_sections()
    manifest = load_manifest()
    rows, order = {}, []
    for s in sections:
        row = rows.get(s["lecture_id"])
        if row is None:
            versions = manifest.get(s["lecture_id"], {}).get("versions", [])
            row = rows[s["lecture_id"]] = {"lecture_id": s["lecture_id"], "title": s["lecture_title"], "file": s["source_file"],
                                           "sections": 0, "uploaded": s.get("uploaded", ""), "versions": len(versions) or 0,
                                           "version": s.get("upload_version")}
            order.append(s["lecture_id"])
        row["sections"] += 1
    return [rows[i] for i in order]


COST_PER_SECTION = 0.015      # measured over the whole job: $8.40 / 562 sections


def estimate_cost(sections):
    return sections * COST_PER_SECTION


def run_factcheck(title, line=None):
    """Run the normal fact-check for one lecture (a separate process). -> {"ok", "cost", "report", "output"}.

    Costs real money: the caller must have shown estimate_cost() and had it confirmed first. Writes
    reports/factcheck_<slug>.json; nothing in data/raw is touched.
    """
    import subprocess
    import sys

    from src import reports
    proc = subprocess.Popen([sys.executable, "-m", "src.audit.factcheck", "--lecture", title], cwd=str(ROOT),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out = []
    for text in proc.stdout:
        out.append(text.rstrip())
        if line:
            line(text.rstrip())
    proc.wait()
    joined = "\n".join(out)
    m = re.search(r"Cost: this session \$([0-9.]+)", joined)
    return {"ok": proc.returncode == 0, "cost": float(m.group(1)) if m else 0.0,
            "report": str(reports.per_file_report(title)), "output": joined}
