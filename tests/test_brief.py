"""Brief answers and verified-fix citations in Q&A mode. The model is replaced by canned answers."""
import pytest

from src import verified
from src.modes import qa
from src.retrieval.search import Hit, SearchResult

CLOSING = "Ask for more detail if you need it."


def test_brief_is_a_short_markdown_answer_ending_with_the_closing_line():
    p = qa.system_prompt(True)
    assert "BRIEF mode" in p and CLOSING in p and "MARKDOWN" in p and "DETAILED" not in p
    assert "DETAILED" in qa.system_prompt(False) and "MARKDOWN" in qa.system_prompt(False) and CLOSING not in qa.system_prompt(False)
    assert "From reference text" not in p and "banner" in p                  # no label above the answer: the program lists the sources
    assert qa.SYSTEM_PROMPT == qa.system_prompt(False)                 # the long format is the detailed one


def test_brief_problems():
    good = "\n".join(["a [x].", "b [x].", "c [x].", "d [x].", "e [x].", "f [x].", "g [x].", CLOSING])
    assert qa.brief_problems(good) == []
    assert any("lines" in p for p in qa.brief_problems(good + "\nextra"))
    assert any("last line" in p for p in qa.brief_problems("a\nb"))
    assert qa.brief_problems("a\n\n" + CLOSING) == []                  # blank lines do not count
    wordy = " ".join(["word"] * 55)
    assert any("words" in p for p in qa.brief_problems(wordy + "\n" + CLOSING))
    cited = "Short claim [Lecture 16b - Middle Ear > III. Middle Ear (Tympanic Cavity) > 3. Walls of the Middle Ear and more words here]."
    assert qa.brief_problems(cited + "\n" + CLOSING) == []              # citations do not count toward the limit


FIX = {"id": "vf-0001", "by": "TEST", "date": "2026-10-06", "lecture": "L", "breadcrumb": "L > A",
       "notes_quote": "q", "correction": "c", "decision": "confirm_error"}


def test_verified_citation_shows_the_recorded_name_not_dr_inglis():
    assert verified.citation(FIX) == "Verified by TEST, 2026-10-06"
    answer, notes = qa.enforce_verified_citations("The border is the ligament [Verified by Dr. Inglis, 2026-10-06].", [FIX])
    assert "[Verified by TEST, 2026-10-06]" in answer and "Dr. Inglis" not in answer and notes


def test_correct_citation_is_left_alone_and_missing_one_is_added():
    ok = "Border is the ligament [Verified by TEST, 2026-10-06]."
    assert qa.enforce_verified_citations(ok, [FIX]) == (ok, [])
    answer, notes = qa.enforce_verified_citations("Border is the ligament.", [FIX])
    assert answer.endswith("[Verified by TEST, 2026-10-06]") and notes
    assert qa.enforce_verified_citations("untouched", []) == ("untouched", [])


def test_prompt_and_marker_never_assume_a_name():
    p = qa.system_prompt(True) + qa.system_prompt(False)
    assert "[Verified by Dr. Inglis" not in p and "CORRECTED BY DR. INGLIS" not in p
    chunk = {"id": "c", "source_type": "notes", "priority": 2, "lecture": "L", "breadcrumb": "L > A",
             "section_path": ["A"], "text": "- q", "section_number": "", "source_url": ""}
    hit = Hit(chunk=chunk, score=1, rrf=1, cosine=0.8, bm25=1, dense_rank=1, bm25_rank=1)
    msg, _ = qa.build_user_message("?", [hit], "", {"confirmed": [], "doubtful": [], "fixes": [FIX]}, {})
    assert 'by="TEST"' in msg and 'cite="Verified by TEST, 2026-10-06"' in msg and "[LINE CORRECTED V1]" in msg


class OneChunk:
    def search(self, q):
        chunk = {"id": "c", "source_type": "notes", "priority": 2, "lecture": "L", "breadcrumb": "L > A",
                 "section_path": ["A"], "text": "- q", "section_number": "", "source_url": ""}
        return SearchResult(q, True, [Hit(chunk, 1, 1, 0.8, 1, 1, 1)], 0.8)


def reply(answer, **over):
    d = {"covered": True, "basis": "course_notes", "answer": answer, "conflicts": [], "under_review_addressed": [],
         "verified_used": [], "doubtful_used": []}
    d.update(over)
    return d


def test_brief_answer_is_retried_once_when_it_is_too_long(tmp_path, monkeypatch):
    monkeypatch.setattr(qa, "FLAGS_PATH", tmp_path / "flags.jsonl")
    too_long = "\n".join(f"line {i}." for i in range(8))
    good = "Short answer [L > A].\n" + CLOSING
    seen = []

    def fake(client, model, msg, brief=False):
        seen.append((brief, msg))
        return reply(too_long if len(seen) == 1 else good), {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(qa, "call_claude", fake)
    out = qa.answer_question(OneChunk(), None, "m", "q", "", {"confirmed": [], "doubtful": [], "fixes": []}, {}, brief=True)
    assert len(seen) == 2 and all(b for b, _ in seen) and "BRIEF format" in seen[1][1]
    assert out["answer"] == good


def test_long_mode_is_not_checked_for_brevity(tmp_path, monkeypatch):
    monkeypatch.setattr(qa, "FLAGS_PATH", tmp_path / "flags.jsonl")
    seen = []
    monkeypatch.setattr(qa, "call_claude", lambda c, m, msg, brief=False: (seen.append(brief) or
                        (reply("long\n" * 20), {"input_tokens": 1, "output_tokens": 1})))
    qa.answer_question(OneChunk(), None, "m", "q", "", {"confirmed": [], "doubtful": [], "fixes": []}, {}, brief=False)
    assert seen == [False]


def test_wrong_name_in_a_model_answer_is_corrected_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(qa, "FLAGS_PATH", tmp_path / "flags.jsonl")
    ctx = {"confirmed": [], "doubtful": [], "fixes": [FIX]}
    answer = "Line one [Verified by Dr. Inglis, 2026-10-06].\n" + CLOSING
    monkeypatch.setattr(qa, "call_claude", lambda c, m, msg, brief=False: (reply(answer, verified_used=["V1"]),
                                                                          {"input_tokens": 1, "output_tokens": 1}))
    out = qa.answer_question(OneChunk(), None, "m", "q", "", ctx, {}, brief=True)
    assert "[Verified by TEST, 2026-10-06]" in out["answer"] and "Dr. Inglis" not in out["answer"]
    assert any("citation corrected" in n for n in out["notes"])


def test_closing_line_is_normalised():
    assert qa.normalize_brief("a\nAsk for more detail if you need it").endswith(CLOSING)
    assert qa.normalize_brief("a\nb").splitlines()[-1] == CLOSING            # missing: appended
    assert qa.normalize_brief("a\n" + CLOSING) == "a\n" + CLOSING          # already right: unchanged
    assert qa.brief_problems(qa.normalize_brief("a\nAsk for more detail if you need it")) == []
