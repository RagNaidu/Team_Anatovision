"""Checks for src/ingest/parse.py against the real notes in data/."""
import re

import docx
import pytest

from src.ingest import parse

TXT_FILES = sorted(p for p in parse.TEXT_DIR.glob("*.txt") if not p.name.startswith(".~lock"))
REQUIRED_FIELDS = {"lecture_id", "lecture_title", "section_path", "breadcrumb", "text", "text_clean",
                   "source_file", "source_type", "priority", "order"}


@pytest.fixture(scope="module")
def parsed():
    return {p: parse.parse_file(p) for p in TXT_FILES}


def test_notes_are_present():
    assert len(TXT_FILES) == 26


@pytest.mark.parametrize("path", TXT_FILES, ids=lambda p: p.stem[:40])
def test_file_produces_sections(parsed, path):
    records, _ = parsed[path]
    assert records, f"{path.name} produced no sections"


@pytest.mark.parametrize("path", TXT_FILES, ids=lambda p: p.stem[:40])
def test_coverage_at_least_90_percent(parsed, path):
    _, stats = parsed[path]
    assert parse.coverage(stats) >= 90, f"{path.name}: {parse.coverage(stats):.1f}%"


@pytest.mark.parametrize("path", TXT_FILES, ids=lambda p: p.stem[:40])
def test_no_empty_text_or_section_path(parsed, path):
    for r in parsed[path][0]:
        assert r["text"].strip() and r["text_clean"].strip(), r["breadcrumb"]
        assert r["section_path"] and all(x.strip() for x in r["section_path"]), r["breadcrumb"]


@pytest.mark.parametrize("path", TXT_FILES, ids=lambda p: p.stem[:40])
def test_fields_and_source_tags(parsed, path):
    records = parsed[path][0]
    for r in records:
        assert REQUIRED_FIELDS <= set(r)
        assert r["source_type"] == "notes" and r["priority"] == 2
        assert r["breadcrumb"].startswith(r["lecture_title"] + " > ")
    assert [r["order"] for r in records] == list(range(1, len(records) + 1))


@pytest.mark.parametrize("path", TXT_FILES, ids=lambda p: p.stem[:40])
def test_text_clean_only_changes_markup(parsed, path):
    for r in parsed[path][0]:
        assert not re.search(r"\^\([^)]*\)", r["text_clean"])
        assert "\n\n" not in r["text_clean"]
        # same words apart from superscript markup: nothing corrected or dropped
        strip = lambda t: re.sub(r"[\s^()]", "", t)
        assert strip(r["text_clean"]) == strip(r["text"]), r["breadcrumb"]


@pytest.mark.parametrize("path", TXT_FILES, ids=lambda p: p.stem[:40])
def test_no_oversize_sections_except_slides(parsed, path):
    records, stats = parsed[path]
    if stats["layout"] == "script":
        return
    for r in records:
        assert len(r["text"]) <= parse.SPLIT_LIMIT, f"{r['breadcrumb']}: {len(r['text'])} chars"


@pytest.mark.parametrize("path", TXT_FILES, ids=lambda p: p.stem[:40])
def test_every_docx_heading_is_in_some_section_path(parsed, path):
    records, stats = parsed[path]
    if stats["layout"] != "docx":
        pytest.skip("not a heading-style docx")
    d = docx.Document(str(parse.original_path(path.stem)))
    labels = {x for r in records for x in r["section_path"]}
    missing = [parse.para_text(p) for p in d.paragraphs
               if parse.HEADING_STYLE_RE.match(p.style.name) and p.text.strip()
               and parse.para_text(p) not in labels]
    assert not missing, missing


def test_hand_hierarchy_example(parsed):
    records = parsed[next(p for p in TXT_FILES if p.name.startswith("Lecture 09"))][0]
    fpb = next(r for r in records if r["section_path"][-1] == "Flexor Pollicis Brevis")
    assert fpb["section_path"] == ["Muscles of the Hand", "Thenar Muscles", "Flexor Pollicis Brevis"]
    assert fpb["breadcrumb"].endswith("Thenar Muscles > Flexor Pollicis Brevis")
    overview = records[0]
    assert "1^(st)" in overview["text"] and "1st digit" in overview["text_clean"]
