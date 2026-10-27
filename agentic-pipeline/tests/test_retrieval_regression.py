"""Retrieval regressions found by the 8-question check: (1) the chunk that states the answer is BM25's top hit but absent from the
dense list, so fusion pushed it out of the top 5; (2) a short question that names a section by its heading ('the sartorius') scored
0.599 < 0.68 and was refused. The search backend is faked: no index, no model."""
import numpy as np
import pytest

from src.retrieval import search as S


def chunk(i, crumb, priority=2, text="x"):
    return {"id": f"c{i}", "breadcrumb": crumb, "text": text, "priority": priority, "source_type": "notes", "lecture": "L"}


class Col:
    """Fake chroma: query() returns dense_ids in order; get() returns the stored embeddings."""
    def __init__(self, dense_ids, emb):
        self.dense_ids, self.emb = dense_ids, emb

    def query(self, query_embeddings, n_results, where=None):
        return {"ids": [self.dense_ids[:n_results]]}

    def get(self, ids, include):
        return {"ids": list(ids), "embeddings": [self.emb[i] for i in ids]}


class Model:
    def encode(self, texts, **kw):
        return np.array([[1.0, 0.0]])


def make(chunks, dense, bm25_scores, cosines):
    s = object.__new__(S.Searcher)
    s.chunks, s.by_id, s.ids = chunks, {c["id"]: c for c in chunks}, [c["id"] for c in chunks]
    s.bm25 = type("B", (), {"get_scores": lambda self, q: np.array(bm25_scores, dtype=float)})()
    s.col = Col(dense, {cid: np.array([c, (1 - c * c) ** 0.5]) for cid, c in cosines.items()})
    s._model = Model()
    return s


CRUMBS = ["Hand > Thenar Muscles", "Hand > Thenar Compartment", "Arm > Median Nerve > Muscular Branches", "Back > Nerves of the Back",
          "Leg > Innervation", "Hand > Nerves of the Hand > Median Nerve"]


# the five dense hits also match on words (so fusion ranks them first); c5 is BM25's best match but not in the dense list
BM25 = [8, 7, 6, 5, 4, 9]


def test_the_bm25_top_hit_is_kept_in_the_top_five_when_it_is_relevant_on_its_own():
    chunks = [chunk(i, c) for i, c in enumerate(CRUMBS)]
    cos = {"c0": 0.74, "c1": 0.745, "c2": 0.73, "c3": 0.73, "c4": 0.76, "c5": 0.70}
    # dense knows c0..c4; BM25's best word-for-word match is c5, which the dense list does not contain
    s = make(chunks, ["c0", "c1", "c2", "c3", "c4"], BM25, cos)
    s.search("What nerves supply the thenar muscles?")
    fused = S.RRF_K                                                                              # (sanity: the rule, not fusion, brings c5 in)
    res = s.search("What nerves supply the thenar muscles?")
    assert "c5" in [h.chunk["id"] for h in res.hits] and len(res.hits) == 5 and res.found


def test_the_champion_is_not_promoted_if_it_is_not_relevant_on_its_own():
    chunks = [chunk(i, c) for i, c in enumerate(CRUMBS)]
    cos = {"c0": 0.74, "c1": 0.745, "c2": 0.73, "c3": 0.73, "c4": 0.76, "c5": 0.60}          # c5 is under MIN_COSINE: no free pass
    res = make(chunks, ["c0", "c1", "c2", "c3", "c4"], BM25, cos).search("q about thenar")
    assert "c5" not in [h.chunk["id"] for h in res.hits]


def test_a_champion_outside_the_grant_is_never_promoted():
    chunks = [chunk(i, c) for i, c in enumerate(CRUMBS)]
    s = make(chunks, ["c0", "c1", "c2", "c3", "c4"], [0, 0, 0, 0, 0, 0], {f"c{i}": 0.75 for i in range(6)})
    res = s.search("anything")                                                                  # BM25 found nothing (as after the grant mask)
    assert [h.chunk["id"] for h in res.hits] == ["c0", "c1", "c2", "c3", "c4"]


@pytest.mark.parametrize("query,crumb,expected", [
    ("What does the sartorius do?", "Thigh > Muscles of the Anterior Compartment > Sartorius", True),
    ("What is the amoxicillin dose?", "Heart > Cardiac Physiology > Heart Rates", False),
    ("What are the contents of a sandwich?", "Thigh > The Femoral Triangle > Contents", False),         # generic heading: no rescue
    ("What does the ilium do?", "Pelvis > Bones > Ilium", True),
    ("Tell me about the femoral vein", "Thigh > Femoral Triangle > Femoral Vein", False)])           # two-word heading: not a title match
def test_title_match(query, crumb, expected):
    assert S.title_match(query, {"breadcrumb": crumb}) is expected


def test_a_borderline_question_naming_a_heading_is_rescued_but_global_threshold_is_unchanged():
    assert S.MIN_COSINE == 0.68                                                                    # never lowered globally
    chunks = [chunk(0, "Thigh > Muscles of the Anterior Compartment > Sartorius"), chunk(1, "Thigh > Gracilis"), chunk(2, "Thigh > Canal")]
    cos = {"c0": 0.599, "c1": 0.597, "c2": 0.557}
    res = make(chunks, ["c1", "c0", "c2"], [3, 5, 0], cos).search("What does the sartorius do?")
    assert res.found and res.best_cosine == pytest.approx(0.599, abs=1e-6)


def test_an_off_topic_question_is_still_refused_below_the_threshold():
    chunks = [chunk(0, "Heart > Cardiac Physiology > Heart Rates"), chunk(1, "Kidney > Acid-Base Balance"), chunk(2, "Kidney > Roles of Electrolytes")]
    res = make(chunks, ["c0", "c1", "c2"], [1, 1, 1], {"c0": 0.466, "c1": 0.568, "c2": 0.562}).search("What is the amoxicillin dose?")
    assert res.found is False and "0.57 < 0.68" in res.reason


def test_a_borderline_question_below_the_rescue_floor_is_refused_even_with_a_heading_match():
    chunks = [chunk(0, "Thigh > Sartorius"), chunk(1, "x > y")]
    res = make(chunks, ["c0", "c1"], [1, 0], {"c0": 0.50, "c1": 0.40}).search("What does the sartorius do?")
    assert res.found is False


class ShuffledCol(Col):
    """Chroma does not return get() rows in the order requested: this one reverses them (ids are returned beside the vectors)."""
    def get(self, ids, include):
        ids = list(ids)[::-1]
        return {"ids": ids, "embeddings": [self.emb[i] for i in ids]}


def shuffled(chunks, dense, bm25, cos):
    s = make(chunks, dense, bm25, cos)
    s.col = ShuffledCol(dense, s.col.emb)
    return s


def test_cosines_follow_the_returned_ids_when_chroma_shuffles_the_rows():
    chunks = [chunk(i, c) for i, c in enumerate(CRUMBS)]
    cos = {"c0": 0.74, "c1": 0.745, "c2": 0.73, "c3": 0.71, "c4": 0.76, "c5": 0.70}
    res = shuffled(chunks, ["c0", "c1", "c2", "c3", "c4"], BM25, cos).search("What nerves supply the thenar muscles?")
    for h in res.hits:
        assert h.cosine == pytest.approx(cos[h.chunk["id"]], abs=1e-6)


def test_the_champion_rule_still_decides_correctly_with_shuffled_rows():
    chunks = [chunk(i, c) for i, c in enumerate(CRUMBS)]
    ok = {"c0": 0.74, "c1": 0.745, "c2": 0.73, "c3": 0.73, "c4": 0.76, "c5": 0.70}
    res = shuffled(chunks, ["c0", "c1", "c2", "c3", "c4"], BM25, ok).search("What nerves supply the thenar muscles?")
    assert "c5" in [h.chunk["id"] for h in res.hits]                                       # relevant on its own: promoted
    low = dict(ok, c5=0.60)
    res = shuffled(chunks, ["c0", "c1", "c2", "c3", "c4"], BM25, low).search("q about thenar")
    assert "c5" not in [h.chunk["id"] for h in res.hits]                                   # under MIN_COSINE: not promoted


def test_the_found_decision_uses_the_right_cosines_with_shuffled_rows():
    chunks = [chunk(i, c) for i, c in enumerate(CRUMBS)]
    cos = {"c0": 0.50, "c1": 0.50, "c2": 0.50, "c3": 0.50, "c4": 0.90, "c5": 0.50}          # only c4 is relevant
    res = shuffled(chunks, ["c0", "c1", "c2", "c3", "c4"], [0] * 6, cos).search("thenar muscles")
    assert res.found and res.best_cosine == pytest.approx(0.90, abs=1e-6)


def test_rerank_cosines_are_paired_by_id_too(monkeypatch):
    monkeypatch.setenv("RERANK", "on")
    chunks = [chunk(i, c) for i, c in enumerate(CRUMBS)]
    cos = {"c0": 0.74, "c1": 0.745, "c2": 0.73, "c3": 0.71, "c4": 0.76, "c5": 0.70}
    s = shuffled(chunks, ["c0", "c1", "c2", "c3", "c4"], BM25, cos)
    s.rerank_fn = lambda q, docs, timeout: [0.5] * len(docs)
    res = s.search("What nerves supply the thenar muscles?")
    assert res.reranked
    for h in res.hits:
        assert h.cosine == pytest.approx(cos[h.chunk["id"]], abs=1e-6)
