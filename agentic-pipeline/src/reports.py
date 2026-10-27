"""The fact-check report the app uses: reports/factcheck_all.json, plus the per-file reports of uploaded lectures.

When the professor uploads new notes for a lecture and runs the fact-check on that file, `python -m src.audit.factcheck
--lecture "<title>"` writes reports/factcheck_<slug>.json. For such a lecture the new report REPLACES the old items (they
were about text that is no longer in use); every other lecture keeps its items from factcheck_all.json.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACTCHECK_PATH = ROOT / "reports" / "factcheck_all.json"
REPORT_DIR = ROOT / "reports"


def slug(title):
    """The same scope name src/audit/factcheck.py uses for its output file."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def per_file_report(title):
    return REPORT_DIR / f"factcheck_{slug(title)}.json"


def uploaded_titles():
    from src import notes_upload
    return [e["title"] for _, e, v, _ in notes_upload.active_files()]


def load_merged(path=None):
    path = Path(path or FACTCHECK_PATH)
    if not path.exists():
        return {"issues": [], "date": "", "model": "", "sections_checked": 0}
    base = json.loads(path.read_text(encoding="utf-8"))
    if path != FACTCHECK_PATH:
        return base
    replaced = {}
    for title in uploaded_titles():
        extra = per_file_report(title)
        if extra.exists():
            replaced[title] = json.loads(extra.read_text(encoding="utf-8"))
    if replaced:
        base["issues"] = [i for i in base["issues"] if i["lecture"] not in replaced] + \
                         [i for r in replaced.values() for i in r["issues"]]
        base["merged_uploads"] = sorted(replaced)
    return base


def fact_check_dates(titles_uploaded):
    """lecture title -> date of its latest fact-check ('' if none since the last upload)."""
    base = load_merged()
    base_date = base.get("date", "")
    out = {}
    for title, uploaded in titles_uploaded.items():
        extra = per_file_report(title)
        if extra.exists():
            d = json.loads(extra.read_text(encoding="utf-8")).get("date", "")
            out[title] = d if d >= uploaded else ""
        else:
            out[title] = ""
    return base_date, out
