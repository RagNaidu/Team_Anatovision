"""Hybrid search over the index built by src/retrieval/index.py.

1. Dense: bge-small-en-v1.5 cosine search in Chroma (top POOL).
2. Sparse: BM25 over the same chunk text (top POOL).
3. Reciprocal rank fusion of the two rankings (k = 60).
4. Boost: course notes (priority 2) x NOTES_BOOST over OpenStax (priority 3), so notes win near-ties.
5. Return the top 5 with scores. If even the best candidates look unrelated to the question
   (best cosine below MIN_COSINE), return found=False: RRF only measures rank, so relevance is judged
   from the real cosine similarity and from BM25 term overlap.

Run a quick query:  .venv/bin/python -m src.retrieval.search "walls of the middle ear"
"""
import json
import sys
import time
from dataclasses import dataclass, field

import numpy as np
from rank_bm25 import BM25Okapi

from src import llm, terms
from src.retrieval.index import (CHROMA_DIR, CHUNKS_PATH, COLLECTION, EMBED_MODEL, QUERY_PREFIX, load_jsonl,
                                 tokenize)

POOL = 30           # candidates taken from each ranking
RRF_K = 60
TOP_K = 5
BOOST = {2: 1.25, 3: 1.0}   # by priority: notes (2) over open_text (3)
MIN_COSINE = 0.68           # calibrated: on-topic questions score 0.73-0.83 best cosine, off-topic 0.49-0.65
TITLE_FLOOR = 0.55          # a question that names a section's own heading may be rescued from MIN_COSINE down to this
GENERIC_HEADINGS = {"contents", "overview", "introduction", "summary", "terms", "features", "function", "functions", "boundaries"}
RERANK_POOL = 25           # candidates (after fusion and the access filter) sent to the reranker
RERANK_TIMEOUT = 3.0
RERANK_CHARS = 1500        # text of a candidate sent to the reranker
RERANK_BOOST = {2: 1.3, 3: 1.0}   # notes win near-ties over OpenStax (the reranker score is 0-1)
MAX_EXPAND = 5            # a top note hit with at most this many sub-sections brings them all along (a list of parts)
RERANK_CHILDREN = 8        # sub-sections of the best note hits added to the pool ('Rotator Cuff' -> its four muscles)
MIN_BM25_TERMS = 1          # at least this many distinct query terms must appear in a returned chunk
GUIDE_FLOOR = 0.60          # a dissection-guide slide below MIN_COSINE is still relevant if it contains most of the question's words
GUIDE_COVER = 0.6           # ... at least this share of them (and at least two)


def covers(query, chunk):
    """True if at least two of the question's meaningful words, and at least GUIDE_COVER of them, appear (by stem) in the chunk.
    Guide slides are short imperative paragraphs ('cut the sartorius ... to expose the adductor canal'), so a how-to question
    can score a little below MIN_COSINE although the slide has exactly the words asked for."""
    words = terms.stems_of(terms.meaningful_words(query))
    if len(words) < 2:
        return False
    have = terms.stem_set(chunk["breadcrumb"] + " " + chunk["text"])
    n = sum(w in have for w in words)
    return n >= 2 and n / len(words) >= GUIDE_COVER


EXERCISE_SECTIONS = {"key terms", "review questions", "interactive link questions", "critical thinking questions"}


def is_exercise(chunk):
    """OpenStax end-of-chapter material (key-term lists, questions): not a basis for an answer when a body-text passage exists."""
    return chunk["source_type"] == "open_text" and (chunk.get("section_path") or [""])[-1].strip().lower() in EXERCISE_SECTIONS


def drop_exercises(hits):
    body = [h for h in hits if not is_exercise(h.chunk)]
    return body if body else hits


def title_match(query, chunk):
    """True if the query names the chunk's own heading: the last breadcrumb segment is ONE distinctive word (5+ letters, not a
    generic heading such as 'Contents') and the query contains it. 'What does the sartorius do?' matches '... > Sartorius'."""
    leaf = tokenize(chunk["breadcrumb"].split(" > ")[-1])
    return len(leaf) == 1 and len(leaf[0]) >= 5 and leaf[0] not in GENERIC_HEADINGS and leaf[0] in set(tokenize(query))


@dataclass
class Hit:
    chunk: dict
    score: float            # boosted RRF, used for ranking
    rrf: float
    cosine: float
    bm25: float
    dense_rank: int | None
    bm25_rank: int | None


@dataclass
class SearchResult:
    query: str
    found: bool
    hits: list[Hit] = field(default_factory=list)
    best_cosine: float = 0.0
    reason: str = ""
    reranked: bool = False
    rerank_note: str = ""       # why the order was NOT changed (error, timeout), or empty
    rerank_seconds: float = 0.0


def embeddings_by_id(col, ids):
    """{id: vector} from a Chroma collection. collection.get() does NOT return rows in the order of the requested ids, so each vector
    is paired with the id returned beside it, never with its position in the request."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {}
    got = col.get(ids=ids, include=["embeddings"])
    return {i: np.asarray(e) for i, e in zip(got["ids"], got["embeddings"])}


class Searcher:
    def __init__(self):
        import chromadb
        self.chunks = load_jsonl(CHUNKS_PATH)
        self.by_id = {c["id"]: c for c in self.chunks}
        self.ids = [c["id"] for c in self.chunks]
        self.bm25 = BM25Okapi([tokenize(c["breadcrumb"] + " " + c["text"]) for c in self.chunks])
        self.col = chromadb.PersistentClient(path=str(CHROMA_DIR)).get_collection(COLLECTION)
        self._model = None
        self.rerank_fn = llm.rerank      # replaced in tests

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(EMBED_MODEL)
        return self._model

    @property
    def note_lectures(self):
        if getattr(self, "_note_lectures", None) is None:
            self._note_lectures = {c["lecture"] for c in self.chunks if c["source_type"] == "notes"}
        return self._note_lectures

    def access_filter(self, allowed_lectures):
        """-> (chroma where, boolean mask over self.chunks), or (None, None) for no restriction.

        Course material (notes AND dissection guides) is limited to the granted lectures: a guide carries the title of the
        lecture it was matched to (and of a second one when it covers two), so it follows that lecture's grant. A guide can also be
        granted on its own ('Dissection Guide, Class 17'); a guide matched to no lecture is reachable only that way, or by a user who
        may open EVERY lecture (or an instructor, allowed_lectures=None). OpenStax reference text is not course material and stays
        available."""
        if allowed_lectures is None:
            return None, None
        allowed_set = set(allowed_lectures)
        if self.note_lectures and allowed_set >= self.note_lectures:
            return None, None
        allowed = sorted(allowed_set)
        where = ({"$or": [{"source_type": "open_text"}, {"lecture": {"$in": allowed}}, {"lecture2": {"$in": allowed}},
                          {"guide": {"$in": allowed}}]} if allowed else {"source_type": "open_text"})
        mask = np.array([c["source_type"] == "open_text" or c["lecture"] in allowed_set or c.get("lecture2", "") in allowed_set
                         or (bool(c.get("guide")) and c["guide"] in allowed_set) for c in self.chunks])
        return where, mask

    def search(self, query, k=TOP_K, allowed_lectures=None, rerank=True):
        """allowed_lectures: None = everything. Otherwise a collection of lecture titles: course-note chunks from any
        other lecture are removed from BOTH rankings before fusion, so they can never reach the caller (or the model).
        OpenStax reference text is not course notes and stays available."""
        qvec = self.model.encode([QUERY_PREFIX + query], normalize_embeddings=True, convert_to_numpy=True)[0]
        where, allowed_mask = self.access_filter(allowed_lectures)
        dense = self.col.query(query_embeddings=[qvec.tolist()], n_results=POOL, where=where)
        dense_ids = dense["ids"][0]

        qtokens = tokenize(query)
        scores = self.bm25.get_scores(qtokens) if qtokens else np.zeros(len(self.chunks))
        if allowed_mask is not None:
            scores = np.where(allowed_mask, scores, 0.0)
        order = np.argsort(-scores)[:POOL]
        bm25_ids = [self.ids[i] for i in order if scores[i] > 0]

        rrf, d_rank, b_rank = {}, {}, {}
        for r, cid in enumerate(dense_ids, 1):
            rrf[cid] = rrf.get(cid, 0) + 1 / (RRF_K + r)
            d_rank[cid] = r
        for r, cid in enumerate(bm25_ids, 1):
            rrf[cid] = rrf.get(cid, 0) + 1 / (RRF_K + r)
            b_rank[cid] = r

        ranked = sorted(rrf, key=lambda cid: -rrf[cid] * BOOST.get(self.by_id[cid]["priority"], 1.0))[:k]
        champion = bm25_ids[0] if bm25_ids else None             # the best word-for-word match (grants already applied)
        extra = [champion] if champion and champion not in ranked else []
        got = ranked + extra
        cos = {cid: float(np.dot(qvec, e)) for cid, e in embeddings_by_id(self.col, got).items()}
        if extra and cos[champion] >= MIN_COSINE and len(ranked) >= 2:
            # Fusion rewards appearing in BOTH rankings, so a chunk that is BM25's top hit but missing from the dense list can fall
            # out of the top k although it states the answer. Keep it, in place of the weakest hit, if it is relevant on its own.
            ranked[-1] = champion
            rrf[champion] = min(rrf[champion], min(rrf[c] for c in ranked[:-1]) / BOOST.get(self.by_id[champion]["priority"], 1.0))
        bm25_by_id = {self.ids[i]: float(scores[i]) for i in range(len(self.ids))} if len(ranked) else {}
        hits = [Hit(chunk=self.by_id[cid], score=rrf[cid] * BOOST.get(self.by_id[cid]["priority"], 1.0),
                    rrf=rrf[cid], cosine=cos[cid], bm25=bm25_by_id.get(cid, 0.0),
                    dense_rank=d_rank.get(cid), bm25_rank=b_rank.get(cid)) for cid in ranked]

        best = max((h.cosine for h in hits), default=0.0)
        result = SearchResult(query=query, found=True, hits=hits, best_cosine=best)
        terms_ = set(qtokens)
        overlap = max((len(terms_ & set(tokenize(h.chunk["breadcrumb"] + " " + h.chunk["text"]))) for h in hits),
                      default=0)
        rescue = [h for h in hits if h.cosine >= TITLE_FLOOR and title_match(query, h.chunk)]
        cover = [h for h in hits if h.chunk["source_type"] == "dissection_guide" and h.cosine >= GUIDE_FLOOR and covers(query, h.chunk)]
        if hits and best < MIN_COSINE and rescue:
            result.best_cosine = max(h.cosine for h in rescue)         # found: the question names a section by its own heading
        elif hits and best < MIN_COSINE and cover:
            result.best_cosine = max(h.cosine for h in cover)          # found: a guide slide has the words of the how-to question
        elif not hits or best < MIN_COSINE:
            result.found, result.reason = False, f"best cosine {best:.2f} < {MIN_COSINE}"
        elif overlap < MIN_BM25_TERMS:
            result.found, result.reason = False, "no query term appears in any retrieved chunk"
        if result.found and rerank and rerank_on():
            self._rerank(result, query, k, ranked, rrf, d_rank, b_rank, scores, qvec, champion, allowed_mask)
        result.hits = drop_exercises(result.hits)
        return result

    def outside_titles(self, query, allowed_lectures, limit=3):
        """Titles (only) of course lectures/guides that match the query but are NOT in the grant. Purely local: embeddings and BM25 on
        this machine, no reranker, no model; the matching text is not returned, so nothing restricted can be passed on."""
        if allowed_lectures is None:
            return []
        res = self.search(query, rerank=False)
        if not res.found:
            return []
        allowed = set(allowed_lectures)
        out = []
        for h in res.hits[:limit]:
            c = h.chunk
            if c["source_type"] in ("notes", "dissection_guide") and c["lecture"] and c["lecture"] not in allowed \
                    and not (c.get("lecture2") and c["lecture2"] in allowed) and not (c.get("guide") and c["guide"] in allowed) \
                    and c["lecture"] not in out:
                out.append(c["lecture"])
        return out

    # ------------------------------------------------------------------
    # term lookup: where does this word appear, grouped by section
    # ------------------------------------------------------------------

    def _stem_sets(self):
        if getattr(self, "_stem_sets_cache", None) is None:
            self._stem_sets_cache = [terms.stem_set(c["breadcrumb"] + " " + c["text"]) for c in self.chunks]
        return self._stem_sets_cache

    @staticmethod
    def group_key(c):
        """One 'place' in the course: a section of a lecture, a station of a dissection guide, a section of the textbook."""
        if c["source_type"] == "open_text":
            return ("ref", c.get("section_number") or c["breadcrumb"])
        path = c.get("section_path") or []
        return (c["source_type"], c["lecture"], " > ".join(path[:2]) if c["source_type"] == "notes" else c["breadcrumb"])

    def keyword_groups(self, words, allowed_lectures=None, max_groups=6):
        """Word-for-word matches of ALL the given words (by stem) in text the user may access.
        -> {"hits": up to max_groups Hit (one per section, the best chunk of it), "n_groups": how many sections match,
        "all": every matching chunk}.
        Order: Dr. Inglis's material before OpenStax; within it the best match of each distinct lecture first, so the different
        meanings of a term come before repeats from the same lecture."""
        stems = terms.stems_of(words)
        if not stems:
            return {"hits": [], "n_groups": 0, "n_course": 0, "all": []}
        _, mask = self.access_filter(allowed_lectures)
        sets = self._stem_sets()
        scores = self.bm25.get_scores(tokenize(" ".join(words))) if tokenize(" ".join(words)) else np.zeros(len(self.chunks))
        phrase = " ".join(words)
        best, matching = {}, []
        for i, c in enumerate(self.chunks):
            if (mask is not None and not mask[i]) or not all(s in sets[i] for s in stems):
                continue
            matching.append(c)
            sc = float(scores[i]) * BOOST.get(c["priority"], 1.0) * (1.5 if len(words) > 1 and phrase in c["text"].lower() else 1.0)
            key = self.group_key(c)
            if key not in best or sc > best[key][0]:
                best[key] = (sc, i)
        course = sorted((v + (k,) for k, v in best.items() if k[0] != "ref"), reverse=True)
        refs = sorted((v + (k,) for k, v in best.items() if k[0] == "ref"), reverse=True)
        picked, lectures = [], set()
        for sc, i, key in course:                                  # first the best group of each distinct lecture ...
            lec = self.chunks[i]["lecture"]
            if lec not in lectures and len(picked) < max_groups:
                lectures.add(lec)
                picked.append((sc, i, key))
        for item in course:                                        # ... then the next best of the same lectures
            if item not in picked and len(picked) < max_groups:
                picked.append(item)
        chapters = set()
        for sc, i, key in refs:                                    # OpenStax only fills the places that are left
            ch = self.chunks[i]["lecture"]
            if len(picked) < max_groups and ch not in chapters:
                chapters.add(ch)
                picked.append((sc, i, key))
        hits = [Hit(chunk=self.chunks[i], score=sc, rrf=0.0, cosine=0.0, bm25=float(scores[i]), dense_rank=None, bm25_rank=r)
                for r, (sc, i, key) in enumerate(picked, 1)]
        return {"hits": hits, "n_groups": len(best), "n_course": len(course), "all": matching}

    def _children(self, parents, allowed_mask, limit=None):
        """Chunks one level or more below the given note chunks (same lecture, breadcrumb extends theirs), access-filtered."""
        out = []
        for p in parents:
            prefix = self.by_id[p]["breadcrumb"] + " > "
            for i, ch in enumerate(self.chunks):
                if ch["source_type"] == "notes" and ch["breadcrumb"].startswith(prefix) and ch["id"] not in out \
                        and (allowed_mask is None or allowed_mask[i]):
                    out.append(ch["id"])
        return out if limit is None else out[:limit]

    def _rerank(self, result, query, k, ranked, rrf, d_rank, b_rank, scores, qvec, champion, allowed_mask=None):
        """Reorder the already-found, already-access-filtered candidates by a cross-encoder. Never changes found/reason, and any
        failure leaves result.hits exactly as the fusion left them."""
        t0 = time.perf_counter()
        try:
            pool = sorted(rrf, key=lambda cid: -rrf[cid] * BOOST.get(self.by_id[cid]["priority"], 1.0))[:RERANK_POOL]
            if champion and champion not in pool:
                pool.append(champion)
            parents = [c for c in pool[:4] if self.by_id[c]["source_type"] == "notes"][:3]
            for c in self._children(parents, allowed_mask, RERANK_CHILDREN):
                if c not in pool and len(pool) < RERANK_POOL + RERANK_CHILDREN + 1:
                    pool.append(c)
            cos = {cid: float(np.dot(qvec, e)) for cid, e in embeddings_by_id(self.col, pool).items()}
            docs = [(self.by_id[c]["breadcrumb"] + "\n" + self.by_id[c]["text"])[:RERANK_CHARS] for c in pool]
            rr = self.rerank_fn(query, docs, timeout=RERANK_TIMEOUT)
            if not rr or len(rr) != len(pool):
                raise ValueError("empty or short rerank result")
            key = {c: s * RERANK_BOOST.get(self.by_id[c]["priority"], 1.0) for c, s in zip(pool, rr)}
            order = sorted(pool, key=lambda c: -key[c])[:k]
            if champion and champion not in order and cos.get(champion, 0) >= MIN_COSINE and len(order) >= 2:
                order[-1] = champion                       # the best word-for-word match stays, as before reranking
            top = order[0]
            if self.by_id[top]["source_type"] == "notes" and rr[pool.index(top)] >= 0.5:    # expand a short list of parts
                kids = self._children([top], allowed_mask)
                if 0 < len(kids) <= MAX_EXPAND:
                    for c in kids:
                        if c not in order:
                            order.append(c)
                            if c not in cos:
                                cos[c] = float(np.dot(qvec, embeddings_by_id(self.col, [c])[c]))
                            key.setdefault(c, 0.0)
            by_pos = {self.ids[i]: float(scores[i]) for i in range(len(self.ids))}
            result.hits = [Hit(chunk=self.by_id[c], score=key[c], rrf=rrf.get(c, 0.0), cosine=cos[c], bm25=by_pos.get(c, 0.0),
                               dense_rank=d_rank.get(c), bm25_rank=b_rank.get(c)) for c in order]
            result.reranked = True
        except Exception as exc:                          # silent fallback: the answer must never break because of this
            result.rerank_note = type(exc).__name__
        result.rerank_seconds = round(time.perf_counter() - t0, 2)


def rerank_on():
    return llm.rerank_enabled()


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: python -m src.retrieval.search "your question"')
    s = Searcher()
    res = s.search(" ".join(sys.argv[1:]))
    print(f"found={res.found} best_cosine={res.best_cosine:.3f} {res.reason}")
    for h in res.hits:
        print(f"{h.score:.4f} (rrf {h.rrf:.4f}, cos {h.cosine:.2f}, bm25 {h.bm25:.1f}, "
              f"d#{h.dense_rank} b#{h.bm25_rank}) [{h.chunk['source_type']}] {h.chunk['breadcrumb'][:100]}")


if __name__ == "__main__":
    main()
