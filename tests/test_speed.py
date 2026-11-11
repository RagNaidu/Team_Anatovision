"""Step D (faster answers): stage timing, the progress status, the local closing-line fix, the brief token cap, keep-alive and the short cache.
Every change must leave the answer's content as it was; the model, the search and the network are faked."""
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app_api.main import create_app
from src import llm, query, service, stagetime, ttlcache
from src.modes import qa
from tests.test_api import HAND, NOTE_TEXT, NotesSearcher, PW, EMPTY_CTX, ask, login, new_chat, world, client, stud  # noqa: F401
from tests.test_llm import FakeOpenAI
from tests.test_service import CLOSING, FakeClient, FakeSearcher, chunk, reply

CITE = f"[{HAND} > Walls]"


def rt_for(answer):
    return service.Runtime(searcher=NotesSearcher([chunk(NOTE_TEXT, lecture=HAND)]), next_of={}, client=FakeClient(answer), model="m")


def run(answer, brief=True):
    rt = rt_for(answer)
    res = service.ask("median nerve?", "", brief, None, runtime=rt, ctx=EMPTY_CTX, audience="student", log=False)
    return res, rt.client.calls


# ---------------------------------------------------------------------------------------------------------------
# the closing-line fix: no second model call, same content
# ---------------------------------------------------------------------------------------------------------------

BODY = f"The median nerve passes through the carpal tunnel. {CITE}"


@pytest.mark.parametrize("closing", ["Ask for more detail if you need it", "Ask for more detail.", "", "Anything else?"])
def test_a_wrong_closing_line_alone_costs_one_model_call_and_ends_exactly(closing):
    answer = BODY + ("\n" + closing if closing else "")
    fast, calls = run(reply(answer))
    assert len(calls) == 1
    assert fast["answer_text"].splitlines()[-1] == CLOSING
    assert fast["answer_text"].splitlines()[:-1][:1] == [BODY] or BODY in fast["answer_text"]
    assert any("closing line set locally" in n for n in fast["notes"])


@pytest.mark.parametrize("closing", ["Ask for more detail if you need it", "", "Anything else?"])
def test_the_final_answer_is_the_one_a_retry_returning_the_same_text_would_give(closing, monkeypatch):
    answer = BODY + ("\n" + closing if closing else "")
    fast, fast_calls = run(reply(answer))
    monkeypatch.setenv("FAST_BRIEF_FIX", "off")
    slow, slow_calls = run(reply(answer))
    assert len(fast_calls) == 1 and len(slow_calls) == 2
    assert fast["answer_text"] == slow["answer_text"] and fast["status"] == slow["status"] == "answered"
    assert fast["citations"] == slow["citations"]


def test_too_many_lines_still_retries():
    many = "\n".join(f"- Fact {i} about the median nerve. {CITE}" for i in range(12)) + "\n" + CLOSING
    res, calls = run(reply(many))
    assert len(calls) == 2 and any("retry: brief format broken" in n for n in res["notes"])


def test_a_closing_problem_together_with_another_problem_still_retries():
    many = "\n".join(f"- Fact {i} about the median nerve. {CITE}" for i in range(12)) + "\nAsk more."
    _, calls = run(reply(many))
    assert len(calls) == 2


def test_a_copied_openstax_answer_still_retries():
    text = " ".join(["the femoral triangle contains the pectineus muscle and the femoral nerve artery and vein and it lies below the inguinal ligament"
                     " in the upper medial thigh where the sartorius forms the lateral border and the adductor longus forms the medial border"] * 1)
    ref = {"id": "r1", "source_type": "open_text", "priority": 3, "lecture": "Chapter 1", "breadcrumb": "OpenStax A&P 2e > Chapter 1 > Sec",
           "section_path": ["Sec"], "text": text + " " + text, "section_number": "1.2", "source_url": ""}
    rt = service.Runtime(searcher=FakeSearcher([ref]), next_of={}, client=FakeClient(reply(f"{text} [OpenStax A&P 2e §1.2]\n{CLOSING}", basis="open_text")), model="m")
    res = service.ask("femoral triangle contents?", "", True, None, runtime=rt, ctx=EMPTY_CTX, audience="student", log=False)
    assert len(rt.client.calls) >= 2 and any("copied OpenStax" in n for n in res["notes"])


def test_a_good_first_answer_is_untouched():
    res, calls = run(reply(f"{BODY}\n{CLOSING}"))
    assert len(calls) == 1 and not any("closing line" in n or "retry" in n for n in res["notes"])


def test_brief_answers_cap_output_tokens_and_detailed_ones_keep_the_old_limit():
    _, calls = run(reply(f"{BODY}\n{CLOSING}"), brief=True)
    assert calls[0]["max_tokens"] == qa.BRIEF_MAX_TOKENS == 3000
    _, calls = run(reply(BODY), brief=False)
    assert calls[0]["max_tokens"] == 8000


# ---------------------------------------------------------------------------------------------------------------
# short cache and keep-alive
# ---------------------------------------------------------------------------------------------------------------

HIST = [{"question": "femoral triangle?", "answer": "a"}]


def test_the_helper_cache_is_off_unless_turned_on():
    assert ttlcache.settings["seconds"] == 0
    c = FakeOpenAI("femoral triangle apex")
    query.rewrite_query(c, "What is its apex?", HIST, "m")
    query.rewrite_query(c, "What is its apex?", HIST, "m")
    assert len(c.calls) == 2


def test_an_identical_follow_up_is_rewritten_once_while_the_cache_is_on():
    ttlcache.configure(60)
    try:
        c = FakeOpenAI("femoral triangle apex")
        first = query.rewrite_query(c, "What is its apex?", HIST, "m")
        again = query.rewrite_query(c, "What is its apex?", HIST, "m")
        other = query.rewrite_query(c, "What is its roof?", HIST, "m")
        assert len(c.calls) == 2 and first[0] == again[0] == "femoral triangle apex" and again[2] == "rewritten"
        assert again[1] == {"input_tokens": 0, "output_tokens": 0} and other[0] == "femoral triangle apex"
    finally:
        ttlcache.configure(0)


class FakeSession:
    def __init__(self):
        self.posts = 0

    def post(self, url, **kw):
        self.posts += 1
        n = len(kw["json"]["documents"])
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"results": [{"index": i, "relevance_score": 1 - i / 10} for i in range(n)]})


def test_rerank_reuses_one_session_and_caches_identical_calls(monkeypatch):
    monkeypatch.setenv("BULLSAI_API_KEY", "k")
    monkeypatch.setenv("BULLSAI_BASE_URL", "http://example.invalid/v1")
    sess = FakeSession()
    monkeypatch.setattr(llm, "_SESSION", sess)
    assert llm._session() is sess is llm._session()
    docs = ["a", "b", "c"]
    llm.rerank("q", docs)
    llm.rerank("q", docs)
    assert sess.posts == 2                                           # cache off: both calls go out
    ttlcache.configure(60)
    try:
        s1 = llm.rerank("q", docs)
        s2 = llm.rerank("q", docs)
        s3 = llm.rerank("q", docs + ["d"])
        assert sess.posts == 4 and s1 == s2 == [1.0, 0.9, 0.8] and len(s3) == 4
    finally:
        ttlcache.configure(0)


def test_turning_the_cache_off_empties_it():
    ttlcache.configure(60)
    c = FakeOpenAI("x y z")
    query.rewrite_query(c, "What is its apex?", HIST, "m")
    ttlcache.configure(0)
    ttlcache.configure(60)
    try:
        query.rewrite_query(c, "What is its apex?", HIST, "m")
        assert len(c.calls) == 2
    finally:
        ttlcache.configure(0)


# ---------------------------------------------------------------------------------------------------------------
# stage timing
# ---------------------------------------------------------------------------------------------------------------

def test_stages_are_recorded_only_when_a_recorder_is_installed():
    with stagetime.stage("nothing"):
        pass
    phases = []
    rec = stagetime.Recorder(on_phase=phases.append)
    with stagetime.use(rec):
        with stagetime.stage("search", "searching"):
            time.sleep(0.01)
        with stagetime.stage("answer", "writing"):
            pass
    assert [r["name"] for r in rec.rows] == ["search", "answer"] and rec.rows[0]["seconds"] >= 0.01 and phases == ["searching", "writing"]
    done = []
    with stagetime.use(stagetime.Recorder()) as r2:
        t = threading.Thread(target=stagetime.in_context(lambda: done.append(stagetime.stage("worker").__enter__ and 1)))
        t.start(); t.join()
    assert done == [1]


def test_a_real_question_records_the_stages_that_ran():
    rec = stagetime.Recorder()
    with stagetime.use(rec):
        service.ask_for_student("median nerve?", "", True, None, runtime=rt_for(reply(f"{BODY}\n{CLOSING}")), log=False)
    names = [r["name"] for r in rec.rows]
    assert {"term_check", "answer", "citations", "safe_layer"} <= set(names) and "web_lookup" not in names


# ---------------------------------------------------------------------------------------------------------------
# progress status
# ---------------------------------------------------------------------------------------------------------------

def test_the_status_follows_the_stage_words_and_the_answer_comes_whole(world, client, stud, monkeypatch):
    gate_writing, release = threading.Event(), threading.Event()
    real = service.ask_for_student

    def slow(*a, **kw):
        with stagetime.stage("search", "searching"):
            pass
        with stagetime.stage("rerank", "reading"):
            pass
        with stagetime.stage("answer", "writing"):
            gate_writing.set()
            release.wait(5)
        return real(*a, **kw)
    monkeypatch.setattr(service, "ask_for_student", slow)
    cid = new_chat(stud)
    out = {}
    t = threading.Thread(target=lambda: out.update(r=stud.post("/api/ask", json={"chat_id": cid, "question": "median nerve?", "request_id": "req-1"})))
    t.start()
    assert gate_writing.wait(5)
    mid = stud.get("/api/ask/status/req-1")
    assert mid.status_code == 200 and mid.json() == {"stage": "writing"}                   # a stage word and nothing else
    release.set()
    t.join(10)
    assert out["r"].status_code == 200 and out["r"].json()["kind"] == "answer"
    assert stud.get("/api/ask/status/req-1").json() == {"stage": "done"}


def test_the_status_never_goes_backwards_and_belongs_to_one_user(world, client, stud):
    from app_api.routers.ask import Progress
    p = Progress()
    p.start("a", "stud")
    p.move("a", "writing")
    p.move("a", "reading")
    assert p.get("a", "stud") == "writing"
    p.move("a", "done")
    assert p.get("a", "stud") == "done"


def test_status_errors_and_old_clients(world, client, stud):
    assert stud.get("/api/ask/status/unknown").status_code == 404
    cid = new_chat(stud)
    assert ask(stud, "median nerve?", cid).status_code == 200                                # no request_id: works as before
    r = ask(stud, "median nerve?", cid, request_id="mine")
    assert r.status_code == 200 and stud.get("/api/ask/status/mine").json() == {"stage": "done"}
    assert ask(stud, "median nerve?", cid, request_id="bad id!").status_code == 422
    other = TestClient(world)
    login(other, "other")
    assert other.get("/api/ask/status/mine").status_code == 404                              # another user's id
    assert other.post("/api/ask", json={"chat_id": new_chat(other), "question": "median nerve?", "request_id": "mine"}).status_code == 409
    anon = TestClient(world)
    assert anon.get("/api/ask/status/mine").status_code == 401


def test_the_status_carries_no_answer_text(world, client, stud):
    ask(stud, "median nerve?", request_id="leakcheck")
    body = stud.get("/api/ask/status/leakcheck")
    assert set(body.json()) == {"stage"} and "median" not in body.text.lower()


def test_the_api_turns_the_helper_cache_on_and_resets_it_when_it_stops(world):
    with TestClient(world):
        assert ttlcache.settings["seconds"] == 120
    assert ttlcache.settings["seconds"] == 0
