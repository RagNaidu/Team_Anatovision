"""service.ask: structured result, real events, spending cap, audience redaction. The model is faked."""
import json
from types import SimpleNamespace

import pytest

from src import service, usage, verified
from src.modes import qa
from src.retrieval.search import Hit, SearchResult

LEC = "Lecture 99 - Test"
CRUMB = f"{LEC} > Walls"
QUOTE = "Overstated claim in the notes"
TEXT = f"- Fine line.\n- {QUOTE}.\n- Another fine line."


def chunk(text=TEXT, lecture=LEC, kind="notes", cid="n1"):
    if kind == "notes":
        return {"id": cid, "source_type": "notes", "priority": 2, "lecture": lecture, "breadcrumb": f"{lecture} > Walls",
                "section_path": ["Walls"], "text": text, "section_number": "", "source_url": ""}
    return {"id": cid, "source_type": "open_text", "priority": 3, "lecture": "Chapter 1", "breadcrumb": "OpenStax A&P 2e > Chapter 1 > Sec",
            "section_path": ["Sec"], "text": text, "section_number": "1.2", "source_url": "https://openstax.org/x"}


class FakeSearcher:
    def __init__(self, chunks, found=True, cosine=0.8):
        self.chunks, self.found, self.cosine, self.calls = chunks, found, cosine, []

    def search(self, question, k=5, allowed_lectures=None):
        self.calls.append(allowed_lectures)
        keep = [c for c in self.chunks if allowed_lectures is None or c["source_type"] != "notes"
                or c["lecture"] in allowed_lectures]
        hits = [Hit(c, 0.03, 0.03, self.cosine, 1.0, 1, 1) for c in keep]
        return SearchResult(question, self.found and bool(hits), hits, self.cosine if hits else 0.0,
                            "" if self.found else "best cosine 0.50 < 0.68")


    def outside_titles(self, question, allowed_lectures, limit=3):
        """Mirrors Searcher.outside_titles: titles only, from a search that is never reranked or sent to a model."""
        res = self.search(question)
        allowed = set(allowed_lectures or [])
        out = []
        for h in res.hits[:limit] if res.found else []:
            c = h.chunk
            if c["source_type"] in ("notes", "dissection_guide") and c["lecture"] and c["lecture"] not in allowed and c["lecture"] not in out:
                out.append(c["lecture"])
        return out


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(self.reply))],
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=100))


def reply(answer, **over):
    d = {"covered": True, "basis": "course_notes", "answer": answer, "conflicts": [], "under_review_addressed": [],
         "verified_used": [], "doubtful_used": []}
    d.update(over)
    return d


CLOSING = "Ask for more detail if you need it."


def runtime(chunks, model_reply=None, **kw):
    return service.Runtime(searcher=FakeSearcher(chunks, **kw), next_of={}, client=FakeClient(model_reply or reply("x")),
                           model="claude-sonnet-5-5")


def item(kind="likely_factual", verdict="confirmed"):
    return {"lecture": LEC, "breadcrumb": CRUMB, "claim_quote": QUOTE, "issue": "Standard statement here.",
            "severity": "high", "confidence": 0.9, "tier": kind, "type": "factual",
            "verification": {"reason": "Because the AI says so.", "verdict": verdict}}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(qa, "FLAGS_PATH", tmp_path / "flags.jsonl")
    monkeypatch.setattr(verified, "FLAGS_PATH", tmp_path / "flags.jsonl")
    monkeypatch.setattr(usage, "QUESTION_LOG_PATH", tmp_path / "qlog.jsonl")


CITE = f"[{LEC} > Walls]"
EMPTY = {"confirmed": [], "doubtful": [], "fixes": []}


def test_answer_has_the_documented_shape():
    rt = runtime([chunk()], reply(f"The walls are six. {CITE}\n{CLOSING}"))
    res = service.ask("walls?", "", True, None, runtime=rt, ctx=EMPTY)
    assert res["status"] == "answered" and res["answer_text"].startswith("The walls")
    for key in ("units", "citations", "retrieved_chunks", "events", "tokens", "cost", "flags_hit", "verified_fix_used"):
        assert key in res
    assert res["citations"][0]["matched"] and res["retrieved_chunks"][0]["breadcrumb"] == CRUMB
    assert res["tokens"] == {"input": 1000, "output": 100} and res["cost"] == pytest.approx(0.003)


def test_events_are_the_steps_that_really_ran_in_order():
    rt = runtime([chunk()], reply(f"Fact [{LEC} > Walls].\n{CLOSING}"))
    res = service.ask("walls?", "", True, None, runtime=rt, ctx=EMPTY)
    kinds = [e["kind"] for e in res["events"]]
    assert kinds == ["search", "threshold", "factcheck", "verified_check", "model_call", "guard_check", "citation_check"]
    by = {e["kind"]: e["detail"] for e in res["events"]}
    assert by["search"]["n_hits"] == 1 and by["search"]["hits"][0]["cosine"] == 0.8
    assert by["threshold"]["found"] is True and by["factcheck"]["withheld"] == [] and by["verified_check"]["found"] == []
    assert by["model_call"]["input_tokens"] == 1000 and by["citation_check"] == {
        "n_citations": 1, "n_matched": 1, "not_found": []}
    assert [e["i"] for e in res["events"]] == list(range(1, 8))


def test_events_report_what_the_factcheck_really_did():
    ctx = {"confirmed": [item()], "doubtful": [], "fixes": []}
    rt = runtime([chunk()], reply(f"This line is currently under review {CITE}.\n{CLOSING}", under_review_addressed=["U1"]))
    res = service.ask("walls?", "", True, None, runtime=rt, ctx=ctx, audience="professor")
    assert QUOTE not in rt.client.calls[0]["messages"][0]["content"]          # masked before the model saw it
    fc = next(e for e in res["events"] if e["kind"] == "factcheck")["detail"]
    assert fc["withheld"] == [{"id": "U1", "breadcrumb": CRUMB}]
    assert "[LINE UNDER REVIEW U1]" in res["retrieved_chunks"][0]["text"] and QUOTE not in res["retrieved_chunks"][0]["text"]
    assert res["units"][0]["status"][0]["kind"] == "review"
    assert any(e["kind"] == "flags" for e in res["events"])


def test_not_found_makes_no_model_call_and_shows_no_chunks():
    rt = runtime([chunk()], found=False, cosine=0.5)
    res = service.ask("something about quantum physics", "", True, None, runtime=rt, ctx=EMPTY)
    assert res["status"] == "not_found" and res["retrieved_chunks"] == []
    assert all("output_config" not in c for c in rt.client.calls)       # the answering model was never called
    assert [e["kind"] for e in res["events"]] == ["search", "threshold", "topic_check"]    # one tiny off-topic check
    assert res["events"][1]["detail"]["found"] is False


def test_model_decline_is_out_of_scope_without_chunks():
    rt = runtime([chunk()], reply("No clinical advice here.", covered=False, basis="not_covered"))
    res = service.ask("How do I treat X?", "", True, None, runtime=rt, ctx=EMPTY)
    assert res["status"] == "out_of_scope" and res["retrieved_chunks"] == [] and res["citations"] == []


def test_spending_cap_stops_all_api_calls():
    rt = runtime([chunk()])
    res = service.ask("walls?", "", True, None, runtime=rt, ctx=EMPTY, session_cost=2.0, cap=2.0)
    assert res["status"] == "capped" and "spending cap" in res["answer_text"] and rt.client.calls == []
    assert rt.searcher.calls == [] and res["events"][0]["kind"] == "cap"
    under = service.ask("walls?", "", True, None, runtime=runtime([chunk()], reply(f"A {CITE}\n{CLOSING}")),
                        ctx=EMPTY, session_cost=1.99, cap=2.0)
    assert under["status"] == "answered"


def test_student_result_has_no_factcheck_detail_but_professor_does():
    ctx = {"confirmed": [], "doubtful": [item("second_look", "doubtful")], "fixes": []}
    answer = f"Used the line (flagged for review, see fact-check) {CITE}\n{CLOSING}"
    for audience in ("student", "professor"):
        rt = runtime([chunk()], reply(answer, doubtful_used=["D1"]))
        res = service.ask("walls?", "", True, None, runtime=rt, ctx=ctx, audience=audience)
        (flag,) = res["flags_hit"]
        assert flag["kind"] == "doubtful" and flag["statement"]
        has_private = {"quote", "reason", "severity", "confidence"} & set(flag)
        assert bool(has_private) == (audience == "professor")
    student = service.ask("walls?", "", True, None, runtime=runtime([chunk()], reply(answer, doubtful_used=["D1"])),
                          ctx=ctx, audience="student")
    assert "Because the AI says so" not in json.dumps(student)


def test_verified_fix_is_reported_and_its_citation_matches():
    fix = {"id": "vf-0001", "lecture": LEC, "breadcrumb": CRUMB, "notes_quote": QUOTE, "correction": "The right statement.",
           "decision": "confirm_error", "by": "Dr. Inglis", "date": "2026-10-07"}
    ctx = {"confirmed": [], "doubtful": [], "fixes": [fix]}
    rt = runtime([chunk()], reply(f"The right statement [Verified by Dr. Inglis, 2026-10-07].\n{CLOSING}", verified_used=["V1"]))
    res = service.ask("walls?", "", True, None, runtime=rt, ctx=ctx)
    assert res["verified_fix_used"][0]["by"] == "Dr. Inglis" and res["verified_fix_used"][0]["marker"] == "V1"
    assert "notes_quote" not in res["verified_fix_used"][0]                    # the original wording is not repeated
    c = res["citations"][0]
    assert c["kind"] == "verified" and c["matched"] and c["fix"] == 0
    assert next(e for e in res["events"] if e["kind"] == "verified_check")["detail"]["found"][0]["fix"] == "vf-0001"


def test_unmatched_citation_is_dropped_with_its_claim_and_recorded_in_the_events():
    rt = runtime([chunk()], reply(f"Real {CITE}\nMade up [Lecture 5 - Nope > Nothing].\n{CLOSING}"))
    res = service.ask("walls?", "", True, None, runtime=rt, ctx=EMPTY)
    assert res["n_unmatched"] == 0 and "Made up" not in res["answer_text"] and "Nope" not in res["answer_text"]
    ev = next(e for e in res["events"] if e["kind"] == "citation_repair")["detail"]
    assert ev["dropped"] == ["Lecture 5 - Nope > Nothing"] and ev["claims_removed"] == 1


def test_every_question_is_logged_and_unanswered_ones_are_marked(tmp_path):
    service.ask("walls?", "", True, None, runtime=runtime([chunk()], reply(f"A {CITE}\n{CLOSING}")), ctx=EMPTY, user="s1")
    service.ask("quantum?", "", True, None, runtime=runtime([chunk()], found=False, cosine=0.5), ctx=EMPTY, user="s1")
    log = usage.read_log()
    assert [e["answered_from_notes"] for e in log] == [True, False] and log[0]["lectures"] == [LEC] and log[0]["user"] == "s1"
    s = usage.summary(log)
    assert s["chat"]["questions"] == 2 and s["chat"]["top_lectures"] == [(LEC, 1)]
    assert [e["question"] for e in s["chat"]["unanswered"]] == ["quantum?"]


def test_empty_and_overlong_questions_never_reach_the_model():
    rt = runtime([chunk()])
    assert service.ask("   ", "", True, None, runtime=rt, ctx=EMPTY)["status"] == "error"
    assert service.ask("x" * 5000, "", True, None, runtime=rt, ctx=EMPTY)["status"] == "error"
    assert rt.client.calls == [] and rt.searcher.calls == []


def test_notes_outside_the_grant_get_the_access_message():
    other = chunk(lecture="Lecture 12 - Other", cid="n2")
    rt = runtime([other])                                    # only notes from a lecture the student may not use
    res = service.ask("walls?", "", True, [LEC], runtime=rt, ctx=EMPTY)
    assert res["status"] == "access_limited" and res["answer_text"] == service.access_message(["Lecture 12 - Other"])
    assert "Lecture 12 - Other" in res["answer_text"] and "Ask Dr. Inglis to open it for you." in res["answer_text"]
    assert res["reason"] == "outside_access"
    assert res["retrieved_chunks"] == [] and rt.client.calls == []
    assert [e["kind"] for e in res["events"]] == ["access", "search", "threshold", "access_check"]
