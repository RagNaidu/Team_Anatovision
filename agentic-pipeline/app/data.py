"""Cached read-only data for the UI: the search runtime, the lecture list, the OpenStax credit line."""
import json
import re
from pathlib import Path

import streamlit as st

from src import service

ROOT = Path(__file__).resolve().parents[1]
SECTIONS_PATH = ROOT / "data" / "processed" / "sections.jsonl"
ATTRIBUTION_PATH = ROOT / "data" / "raw" / "open_text" / "ATTRIBUTION.md"


@st.cache_resource(show_spinner=False)
def get_runtime():
    """Index + embedding model + API client, loaded once per server process (warmed at start-up)."""
    return service.build_runtime()


def lectures_of(path=None):
    """[{title, file, n_sections, uploaded}] in file order (one row per lecture title)."""
    rows, order = {}, []
    for line in Path(path or SECTIONS_PATH).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        s = json.loads(line)
        row = rows.get(s["lecture_title"])
        if row is None:
            row = rows[s["lecture_title"]] = {"title": s["lecture_title"], "file": s["source_file"], "n_sections": 0,
                                              "uploaded": s.get("uploaded", ""), "lecture_id": s["lecture_id"]}
            order.append(s["lecture_title"])
        row["n_sections"] += 1
    return [rows[t] for t in order]


@st.cache_data(show_spinner=False)
def _lectures(mtime):
    return lectures_of()


def lectures():
    return _lectures(SECTIONS_PATH.stat().st_mtime if SECTIONS_PATH.exists() else 0)


def openstax_credit():
    """Credit line and links, read from data/raw/open_text/ATTRIBUTION.md (not hard-coded)."""
    text = ATTRIBUTION_PATH.read_text(encoding="utf-8") if ATTRIBUTION_PATH.exists() else ""
    book = re.search(r"Access for free at\s*>?\s*(https?://\S+?)\.?\s", text)
    licence = re.search(r"\((https://creativecommons\.org/licenses/by-nc-sa/4\.0/)\)|(https://creativecommons\.org/licenses/by-nc-sa/4\.0/)", text)
    return {"text": "OpenStax Anatomy & Physiology 2e, CC BY-NC-SA 4.0",
            "book_url": book.group(1) if book else "https://openstax.org/details/books/anatomy-and-physiology-2e",
            "licence_url": (licence.group(1) or licence.group(2)) if licence else "https://creativecommons.org/licenses/by-nc-sa/4.0/"}
