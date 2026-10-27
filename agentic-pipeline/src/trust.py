"""'Notes: Dr. Inglis, loaded 6 Oct 2026': when the notes were last loaded into the search index (never a Word file's old date).

An uploaded lecture carries its upload date in sections.jsonl; every other lecture takes the date the index was last built
(the modified time of data/index/chunks.jsonl). If neither is known, or the date is implausible, no date is shown.
"""
import json
from datetime import datetime
from pathlib import Path

from src.retrieval.index import CHUNKS_PATH

ROOT = Path(__file__).resolve().parents[1]
SECTIONS_PATH = ROOT / "data" / "processed" / "sections.jsonl"
MIN_YEAR = 2020
_cache = {"stamp": None, "dates": {}}


def index_date(index_path=None):
    p = Path(index_path or CHUNKS_PATH)
    if not p.exists():
        return ""
    d = datetime.fromtimestamp(p.stat().st_mtime)
    return d.strftime("%Y-%m-%d") if d.year >= MIN_YEAR else ""


def lecture_dates(sections_path=None, index_path=None):
    """{lecture title: 'YYYY-MM-DD'} (uploaded date, else the date the index was built)."""
    sections_path = Path(sections_path or SECTIONS_PATH)
    if not sections_path.exists():
        return {}
    built = index_date(index_path)
    stamp = (str(sections_path), sections_path.stat().st_mtime, built)
    if _cache["stamp"] == stamp:
        return _cache["dates"]
    dates = {}
    for line in sections_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        s = json.loads(line)
        title = s["lecture_title"]
        if title in dates:
            continue
        up = (s.get("uploaded") or "")[:10]
        date = up if up and int(up[:4]) >= MIN_YEAR else built
        if date:
            dates[title] = date
    _cache.update(stamp=stamp, dates=dates)
    return dates


def notes_updated(lecture_title, **kw):
    return lecture_dates(**kw).get(lecture_title, "")


def pretty(date):
    """'2026-10-06' -> '6 Oct 2026' ('' stays '')."""
    try:
        d = datetime.strptime(date, "%Y-%m-%d")
        return f"{d.day} {d.strftime('%b %Y')}"
    except ValueError:
        return ""
