"""Retrieval and Q&A-guard checks. Needs the index: .venv/bin/python -m src.retrieval.index"""
import json

import pytest

from src.modes import qa
from src.retrieval import index as idx
from src.retrieval.search import MIN_COSINE, TOP_K, Searcher

pytestmark = pytest.mark.skipif(not idx.CHUNKS_PATH.exists() or not idx.CHROMA_DIR.exists(),
                                reason="search index not built (run python -m src.retrieval.index)")


@pytest.fixture(scope="module")
def searcher():
    return Searcher()


@pytest.fixture(scope="module")
def chunks():
    return idx.load_jsonl(idx.CHUNKS_PATH)


# ---- the chunk table ------------------------------------------------------------------------------------

def test_every_chunk_has_metadata(chunks):
    for c in chunks:
        assert c["section_path"] and c["breadcrumb"] and c["text"].strip()
        assert (c["source_type"], c["priority"]) in {("notes", 2), ("dissection_guide", 2), ("open_text", 3)}


def test_openstax_chunks_are_short_and_keep_source_url(chunks):
    refs = [c for c in chunks if c["source_type"] == "open_text"]
    assert refs and all(c["source_url"].startswith("https://openstax.org/books/anatomy-and-physiology-2e/pages/")
                        for c in refs)
    assert max(len(c["text"]) for c in refs) <= 1700
    assert any(c["n_chunks"] > 1 for c in refs)           # long sections really were split


def test_chunks_cover_every_notes_section(chunks):
    notes = idx.load_jsonl(idx.NOTES_PATH)
    assert len({(c["lecture"], c["breadcrumb"]) for c in chunks if c["source_type"] == "notes"}) \
        == len({(n["lecture_title"], n["breadcrumb"]) for n in notes})


def test_chroma_has_every_chunk(searcher, chunks):
    assert searcher.col.count() == len(chunks)


def test_overlapping_chunker():
    text = " ".join(f"Sentence number {i} is here." for i in range(200))
    parts = idx.split_text(text)
    assert len(parts) > 1 and all(len(p) <= 1500 for p in parts)
    assert parts[1][:40] in parts[0] or parts[1].split(".")[0] in parts[0]   # neighbouring chunks overlap


# ---- retrieval ------------------------------------------------------------------------------------------

def paths(result):
    return [h.chunk["breadcrumb"] for h in result.hits]


@pytest.mark.parametrize("question, expected", [
    ("What are the walls of the middle ear?", "Walls of the Middle Ear"),
    ("What nerves supply the muscles of the hand?", "Lecture 09 - The Hand > Nerves of the Hand"),
    ("What does the popliteal artery continue from?", "Popliteal Artery"),
    ("Where do the plantar interossei originate?", "Plantar interossei"),
    ("What is the superior border of the femoral triangle?", "The Femoral Triangle"),
    ("What does the stapedius muscle do?", "Lecture 16b - Middle Ear"),
])
def test_known_questions_find_the_right_notes(searcher, question, expected):
    result = searcher.search(question)
    assert result.found
    assert any(expected in p for p in paths(result)), paths(result)


def test_returns_at_most_five_descending_scores(searcher):
    result = searcher.search("What are the walls of the middle ear?")
    assert 0 < len(result.hits) <= TOP_K
    scores = [h.score for h in result.hits]
    assert scores == sorted(scores, reverse=True)


def test_notes_outrank_openstax_when_both_cover_the_topic(searcher):
    result = searcher.search("What passes through the carpal tunnel?")
    assert result.found
    assert result.hits[0].chunk["source_type"] == "notes"
    assert result.hits[0].chunk["priority"] == 2


def test_openstax_is_used_when_notes_do_not_cover_it(searcher):
    result = searcher.search("How does the sodium-potassium pump maintain the resting membrane potential?")
    assert result.found
    assert any(h.chunk["source_type"] == "open_text" for h in result.hits)


@pytest.mark.parametrize("question", [
    "What is the normal dose of amoxicillin?",
    "How do I cook rice?",
    "Who won the world cup?",
])
def test_off_topic_questions_are_not_found(searcher, question):
    result = searcher.search(question)
    assert not result.found
    assert result.best_cosine < MIN_COSINE or result.reason


# ---- fact-check awareness and answer guards -------------------------------------------------------------

def test_confirmed_factual_lines_are_masked_before_the_model_sees_them(chunks):
    items = qa.load_review_items()
    assert items and all(i["tier"] == "likely_factual" for i in items)
    chunk = next(c for c in chunks if c["source_type"] == "notes" and "Superior – inguinal canal" in c["text"])
    text, applied = qa.annotate_review(chunk, items)
    assert applied and "Superior – inguinal canal" not in text
    assert "[LINE UNDER REVIEW U1]" in text


def test_openstax_chunks_are_never_masked(chunks):
    ref = next(c for c in chunks if c["source_type"] == "open_text")
    text, applied = qa.annotate_review(ref, qa.load_review_items())
    assert text == ref["text"] and applied == []


def test_verbatim_openstax_guard(chunks):
    ref = next(c for c in chunks if c["source_type"] == "open_text" and len(c["text"].split()) > 60)
    words = ref["text"].split()
    paraphrase = "The text describes this idea in different words and adds nothing copied from the source passage."
    assert qa.verbatim_spans(paraphrase, [ref["text"]]) == []
    copied = " ".join(words[5:20])
    assert qa.verbatim_spans(f"As the text puts it, {copied} and so on.", [ref["text"]]) == [len(qa.words_of(copied))]
    long_copy = " ".join(words[5:50])
    assert max(qa.verbatim_spans(long_copy, [ref["text"]])) > qa.MAX_VERBATIM_WORDS


def test_flags_are_deduplicated(tmp_path, monkeypatch):
    monkeypatch.setattr(qa, "FLAGS_PATH", tmp_path / "flags.jsonl")
    assert qa.append_flag({"type": "x"}, key="k1") is True
    assert qa.append_flag({"type": "x"}, key="k1") is False
    assert qa.append_flag({"type": "x"}, key="k2") is True
    assert len((tmp_path / "flags.jsonl").read_text().splitlines()) == 2
