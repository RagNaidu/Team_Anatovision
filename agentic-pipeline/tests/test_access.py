"""Access control is enforced in the search layer, before anything reaches the model. Uses the real index."""
import json
from types import SimpleNamespace

import pytest

from src import service, usage, verified
from src.modes import qa
from src.retrieval import index as idx
from src.retrieval.search import Searcher

pytestmark = pytest.mark.skipif(not idx.CHUNKS_PATH.exists() or not idx.CHROMA_DIR.exists(),
                                reason="search index not built (run python -m src.retrieval.index)")

HAND = "Lecture 09 - The Hand"
QUESTIONS = ["What are the walls of the middle ear?", "What are the boundaries of the femoral triangle?",
             "What is the larynx cartilage framework?", "What nerves supply the thenar muscles?",
             "Which muscles are in the posterior compartment of the leg?"]


@pytest.fixture(scope="module")
def searcher():
    return Searcher()


def notes_lectures(result):
    return {h.chunk["lecture"] for h in result.hits if h.chunk["source_type"] == "notes"}


@pytest.mark.parametrize("question", QUESTIONS)
def test_student_with_only_lecture_09_never_receives_other_lectures(searcher, question):
    res = searcher.search(question, allowed_lectures=[HAND])
    assert notes_lectures(res) <= {HAND}
    assert all(h.chunk["source_type"] in ("notes", "open_text") for h in res.hits)


def test_the_professor_sees_everything(searcher):
    ear = searcher.search("What are the walls of the middle ear?")
    assert any("Middle Ear" in l for l in notes_lectures(ear))
    restricted = searcher.search("What are the walls of the middle ear?", allowed_lectures=[HAND])
    assert not any("Middle Ear" in l for l in notes_lectures(restricted))


def test_a_student_with_no_grants_gets_only_openstax(searcher):
    res = searcher.search("What are the walls of the middle ear?", allowed_lectures=[])
    assert notes_lectures(res) == set() and res.hits and all(h.chunk["source_type"] == "open_text" for h in res.hits)


def test_the_hand_is_still_found_for_the_student_who_has_it(searcher):
    res = searcher.search("What nerves supply the thenar muscles of the hand?", allowed_lectures=[HAND])
    assert res.found and HAND in notes_lectures(res)


def test_nothing_from_other_lectures_is_sent_to_the_model(searcher, tmp_path, monkeypatch):
    monkeypatch.setattr(qa, "FLAGS_PATH", tmp_path / "flags.jsonl")
    monkeypatch.setattr(verified, "FLAGS_PATH", tmp_path / "flags.jsonl")
    monkeypatch.setattr(usage, "QUESTION_LOG_PATH", tmp_path / "q.jsonl")
    sent = []

    def create(**kw):
        sent.append(kw["messages"][0]["content"])
        answer = json.dumps({"covered": True, "basis": "course_notes", "answer": "ok", "conflicts": [],
                             "under_review_addressed": [], "verified_used": [], "doubtful_used": []})
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=answer)],
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))

    rt = service.Runtime(searcher=searcher, next_of={}, client=SimpleNamespace(messages=SimpleNamespace(create=create)),
                         model="claude-sonnet-5-5")
    empty = {"confirmed": [], "doubtful": [], "fixes": []}
    for q in QUESTIONS:
        res = service.ask(q, "", True, [HAND], runtime=rt, ctx=empty)
        assert {c["lecture"] for c in res["retrieved_chunks"] if c["source_type"] == "notes"} <= {HAND}
    others = {c["lecture"] for c in searcher.chunks if c["source_type"] == "notes" and c["lecture"] != HAND}
    for message in sent:
        for lecture in others:
            assert f'path="{lecture}' not in message and f"{lecture} >" not in message
    assert sent, "the model should have been called for at least one question"
