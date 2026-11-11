"""The rerank stage with a mocked reranker (no network, no index, no model)."""
import numpy as np
import pytest

from src.retrieval import search as S
from tests.test_retrieval_regression import Col, make


def ch(i, crumb, lecture="Lecture 09 - The Hand", source_type="notes", text=None):
    return {"id": f"c{i}", "breadcrumb": crumb, "text": text or f"text of {crumb}", "priority": 2 if source_type == "notes" else 3,
            "source_type": source_type, "lecture": lecture}


@pytest.fixture(autouse=True)
def rerank_on(monkeypatch):
    monkeypatch.setenv("RERANK", "on")


def scorer(best):
    """A fake reranker: documents containing `best` score 0.95, the rest 0.1. Records what it was given."""
    calls = []

    def fn(query, docs, timeout):
        calls.append({"query": query, "docs": list(docs), "timeout": timeout})
        return [0.95 if best in d else 0.1 for d in docs]
    fn.calls = calls
    return fn


def hypothenar_world(n=20):
    chunks = [ch(i, f"Lecture 09 - The Hand > Filler {i}") for i in range(n)]
    chunks.append(ch(n, "Lecture 09 - The Hand > Nerves of the Hand > Ulnar Nerve", text="supplies the hypothenar eminence ULNARANSWER"))
    cos = {c["id"]: 0.75 for c in chunks}
    dense = [c["id"] for c in chunks[:n]] + [f"c{n}"]               # the answer is the 21st dense hit
    return chunks, dense, cos


def test_a_passage_that_ranked_far_below_the_top_five_is_pulled_into_the_top_five():
    chunks, dense, cos = hypothenar_world()
    s = make(chunks, dense, [0] * len(chunks), cos)
    s.rerank_fn = scorer("ULNARANSWER")
    res = s.search("text nerve supply of the hypothenar muscles")
    assert res.reranked and res.found and len(res.hits) == 5
    assert res.hits[0].chunk["id"] == "c20"
    plain = make(chunks, dense, [0] * len(chunks), cos)
    plain.rerank_fn = lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called when off"))
    import os
    os.environ["RERANK"] = "off"
    assert "c20" not in [h.chunk["id"] for h in plain.search("text nerve supply of the hypothenar muscles").hits]


def test_a_short_list_of_parts_comes_along_with_its_parent():
    parent = "Lecture 04 - The Shoulder > Scapular Region > The Rotator Cuff"
    chunks = [ch(0, parent, text="Set of 4 muscles ROTATORCUFF"),
              ch(1, parent + " > Supraspinatus"), ch(2, parent + " > Infraspinatus"), ch(3, parent + " > Teres Minor"),
              ch(4, parent + " > Subscapularis")]
    chunks += [ch(5 + i, f"OpenStax > Joints > Topic {i}", source_type="open_text", lecture="") for i in range(6)]
    s = make(chunks, [c["id"] for c in chunks[5:]] + ["c0", "c1"], [0] * len(chunks), {c["id"]: 0.75 for c in chunks})
    s.rerank_fn = scorer("ROTATORCUFF")
    res = s.search("text Which muscles make up the rotator cuff?")
    ids = [h.chunk["id"] for h in res.hits]
    assert ids[0] == "c0" and "c4" in ids                       # Subscapularis is in the answer's passages


def test_any_reranker_failure_silently_keeps_the_fusion_order():
    chunks, dense, cos = hypothenar_world()
    base = make(chunks, dense, [0] * len(chunks), cos)
    import os
    os.environ["RERANK"] = "off"
    want = [h.chunk["id"] for h in base.search("text q").hits]
    os.environ["RERANK"] = "on"
    for bad in (lambda q, d, timeout: (_ for _ in ()).throw(TimeoutError("slow")), lambda q, d, timeout: [], lambda q, d, timeout: [0.5]):
        s = make(chunks, dense, [0] * len(chunks), cos)
        s.rerank_fn = bad
        res = s.search("text q")
        assert [h.chunk["id"] for h in res.hits] == want and res.found and not res.reranked and res.rerank_note


def test_not_found_is_decided_before_and_without_the_reranker():
    chunks, dense, cos = hypothenar_world()
    cos = {k: 0.60 for k in cos}                                # under MIN_COSINE: not found
    s = make(chunks, dense, [0] * len(chunks), cos)
    fn = scorer("ULNARANSWER")
    s.rerank_fn = fn
    res = s.search("text pizza")
    assert not res.found and fn.calls == [] and not res.reranked


def test_the_found_decision_is_the_same_with_and_without_the_reranker():
    chunks, dense, cos = hypothenar_world()
    cos["c3"] = 0.70                                            # best cosine of the original top hits stays what it was
    s = make(chunks, dense, [0] * len(chunks), cos)
    s.rerank_fn = scorer("ULNARANSWER")
    on = s.search("text q")
    import os
    os.environ["RERANK"] = "off"
    off = make(chunks, dense, [0] * len(chunks), cos).search("text q")
    assert (on.found, on.reason, on.best_cosine) == (off.found, off.reason, off.best_cosine)


def test_out_of_access_notes_never_reach_the_reranker_or_the_result():
    secret = ch(30, "Lecture 99 - Secret > Hidden", lecture="Lecture 99 - Secret", text="SECRETANSWER")
    chunks, dense, cos = hypothenar_world(6)
    chunks.append(secret)
    cos["c30"] = 0.9

    class FilteringCol(Col):
        def query(self, query_embeddings, n_results, where=None):
            ids = [i for i in self.dense_ids if self_chunks[i]["source_type"] != "notes"
                   or where is None or self_chunks[i]["lecture"] in where["$or"][1]["lecture"]["$in"]]
            return {"ids": [ids[:n_results]]}

    self_chunks = {c["id"]: c for c in chunks}
    s = make(chunks, ["c30"] + dense, [0] * (len(chunks) - 1) + [9], cos)        # the secret is the best dense AND BM25 hit
    s.col = FilteringCol(["c30"] + dense, s.col.emb)
    fn = scorer("SECRETANSWER")
    s.rerank_fn = fn
    res = s.search("text q", allowed_lectures=["Lecture 09 - The Hand"])
    assert fn.calls and not any("SECRETANSWER" in d or "Secret" in d for d in fn.calls[0]["docs"])
    assert "c30" not in [h.chunk["id"] for h in res.hits]


def test_the_outside_title_check_is_local_and_sends_no_restricted_text_to_the_reranker():
    secret = ch(30, "Lecture 99 - Secret > Hidden", lecture="Lecture 99 - Secret", text="SECRETANSWER")
    chunks, dense, cos = hypothenar_world(6)
    chunks.append(secret)
    cos["c30"] = 0.9
    s = make(chunks, ["c30"] + dense, [0] * (len(chunks) - 1) + [9], cos)
    fn = scorer("SECRETANSWER")
    s.rerank_fn = fn
    titles = s.outside_titles("text q", ["Lecture 09 - The Hand"])
    assert titles == ["Lecture 99 - Secret"]                      # the useful access message still has its title
    assert fn.calls == []                                         # the reranker (a model call) was never used for it
    assert all(isinstance(t, str) and "SECRETANSWER" not in t for t in titles)
    assert s.outside_titles("text q", None) == []                  # no restriction: nothing is "outside"


def test_a_restricted_student_ask_sends_no_ungranted_text_to_any_model(monkeypatch):
    """End to end through service.ask with the real Searcher logic and a recording reranker and model client."""
    from tests.test_service import FakeClient
    from src import service
    secret = ch(30, "Lecture 99 - Secret > Hidden", lecture="Lecture 99 - Secret", text="SECRETANSWER")
    chunks, dense, cos = hypothenar_world(3)
    chunks.append(secret)
    cos["c30"] = 0.9
    s = make(chunks, ["c30"] + dense, [0] * (len(chunks) - 1) + [9], cos)
    by = {c["id"]: c for c in chunks}

    class FilteringCol(Col):                       # honours the grant filter like Chroma does
        def query(self, query_embeddings, n_results, where=None):
            ids = [i for i in self.dense_ids if where is None or by[i]["lecture"] in where["$or"][1]["lecture"]["$in"]]
            return {"ids": [ids[:n_results]]}
    s.col = FilteringCol(["c30"] + dense, s.col.emb)
    rr = scorer("SECRETANSWER")
    s.rerank_fn = rr
    import src.service as svc
    seen = []
    orig = svc.qa.answer_question
    def spy(*a, **k):
        seen.append(repr((a, k)))
        return orig(*a, **k)
    monkeypatch.setattr(svc.qa, "answer_question", spy)
    client = FakeClient({"covered": False, "basis": "not_covered", "answer": "", "conflicts": [], "under_review_addressed": [],
                         "verified_used": [], "doubtful_used": []})
    rt = service.Runtime(searcher=s, next_of={}, client=client, model="m", rewrite_model="m")
    try:
        service.ask("text q", allowed_lectures=["Lecture 09 - The Hand"], runtime=rt, log=False)
    except (KeyError, ValueError, TypeError, RuntimeError):
        pass                                                      # only the model/reranker inputs matter here
    assert rr.calls, "the granted search should have used the reranker (otherwise this test proves nothing)"
    blob = repr(client.calls) + repr(rr.calls)
    assert "SECRETANSWER" not in blob and "Lecture 99" not in repr(rr.calls)
