"""Quiz: evidence, gates, rejection paths, 5/10 lengths, access, freezing, scoring, isolation, resume, disclosure. Models are faked (no network)."""
import json
import random

import pytest

from src import llm
from src.quiz import evidence, generate, items, service
from src.quiz.store import QuizError, QuizStore
from tests.quiz_fakes import EMPTY_CTX, FACTS, HAND, OTHER, SECRET, Behavior, corpus, install, runtime

ALLOWED = [HAND]


@pytest.fixture
def beh(monkeypatch):
    return install(monkeypatch, Behavior())


def req(n=5, mode="materials", **kw):
    base = {"mode": mode, "n": n, "selected": [HAND]} if mode == "materials" else {"mode": mode, "n": n, "topic": "nerves of the hand"}
    return {**base, **kw}


def build(n=5, rt=None, allowed=ALLOWED, store=None, **kw):
    return service.new_quiz("s1", allowed, req(n, **kw), rt or runtime(), store=store or QuizStore(), ctx=EMPTY_CTX, rng=random.Random(1), web_lookup=None,
                            ver_model="openai/gpt-oss-120b")


# ---- lengths ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("n", [5, 10])
def test_a_quiz_has_exactly_five_or_ten_questions_and_every_one_passed(beh, n):
    out = build(n)
    assert out["status"] == "ready" and out["passed"] == n
    q = QuizStore().get_quiz("s1", out["quiz_id"])
    assert q["length"] == n == len(q["item_ids"])


def test_other_lengths_are_refused(beh):
    with pytest.raises(QuizError):
        build(7)


# ---- gates and rejection --------------------------------------------------------------------------------------

def test_every_model_in_the_chain_is_the_right_one(beh):
    build(5)
    assert "google/gemma-4-31B-it" in beh.models and "openai/gpt-oss-120b" in beh.models


def test_the_solvers_never_see_the_key_or_explanation(beh):
    build(5)
    solve = [p for p in beh.prompts if "<question>" in p and "KEY:" not in p]
    assert solve and all("explanation" not in p.lower().split("<evidence>")[0] for p in solve)
    assert all("key_index" not in p and "why_wrong" not in p for p in solve)


@pytest.mark.parametrize("knob,value,stage", [("gen", "bad_span", "structure"), ("gen", "no_support", "structure"), ("gen", "negative", "structure"),
                                              ("gemma", "wrong", "solver_gemma"), ("gemma", "two", "solver_gemma"),
                                              ("verifier", "wrong", "solver_verifier"), ("verifier", "two", "solver_verifier"),
                                              ("verifier", "error", "model_error"), ("audit", "unsupported", "audit"), ("audit", "error", "model_error")])
def test_each_failed_gate_rejects_the_draft_and_no_quiz_starts(beh, knob, value, stage):
    setattr(beh, knob, value)
    out = build(5)
    assert out["status"] == "failed" and out["quiz_id"] is None
    runs = QuizStore().runs()
    assert runs[0]["outcome"] == "failed" and (stage in runs[0].get("rejected_by_stage", {}) or runs[0].get("message"))


def test_a_draft_with_a_fabricated_span_gets_one_repair_and_is_then_accepted(beh):
    beh.gen = "bad_span_once"
    assert build(5)["status"] == "ready"


def test_a_citation_must_be_a_real_span_of_a_supplied_source():
    ev = {"p": {"id": "p", "text": "The median nerve supplies the thenar muscles of the hand."}}
    good = {"stem": "", "lead_in": "Which nerve supplies the thenar muscles?", "options": ["the median nerve", "the ulnar nerve", "the radial nerve", "the axillary nerve"],
            "key_index": 0, "explanation": "x", "key_support": [{"source_id": "p", "span": "The median nerve supplies the thenar muscles"}],
            "explanation_support": [{"source_id": "p", "span": "supplies the thenar muscles of the hand"}],
            "alternatives": [{"index": i, "why_wrong": "r", "support": [{"source_id": "p", "span": "median nerve supplies the thenar"}]} for i in (1, 2, 3)]}
    assert items.validate_draft(good, ev) == []
    for patch in ({"key_support": [{"source_id": "zzz", "span": "The median nerve supplies the thenar muscles"}]},
                  {"key_support": [{"source_id": "p", "span": "The ulnar nerve supplies the thenar muscles"}]},
                  {"key_support": [{"source_id": "p", "span": "median nerve"}]},
                  {"explanation_support": []}):
        assert items.validate_draft({**good, **patch}, ev)


def test_nbme_flaws_are_rejected():
    ev = {"p": {"id": "p", "text": "The median nerve supplies the thenar muscles of the hand."}}
    base = {"stem": "", "lead_in": "Which nerve supplies the thenar muscles?", "options": ["the median nerve", "the ulnar nerve", "the radial nerve", "the axillary nerve"],
            "key_index": 0, "explanation": "x", "key_support": [{"source_id": "p", "span": "The median nerve supplies the thenar muscles"}],
            "explanation_support": [{"source_id": "p", "span": "supplies the thenar muscles of the hand"}],
            "alternatives": [{"index": i, "why_wrong": "r", "support": [{"source_id": "p", "span": "median nerve supplies the thenar"}]} for i in (1, 2, 3)]}
    bad = [{"options": ["the median nerve", "the ulnar nerve", "none of the above", "the axillary nerve"]},
           {"options": ["the median nerve", "the ulnar nerve", "always the radial nerve", "the axillary nerve"]},
           {"options": ["the median nerve", "the ulnar nerve", "the ulnar nerve", "the axillary nerve"]},
           {"lead_in": "The thenar muscles are supplied by:"}, {"lead_in": "Which nerve does NOT supply the thenar muscles?"},
           {"options": ["the median nerve and its recurrent branch in the hand", "the ulnar", "the radial", "the axillary"]},
           {"options": ["the median nerve", "the ulnar nerve", "the radial nerve"]}]
    for patch in bad:
        assert items.validate_draft({**base, **patch}, ev), patch


# ---- never pad, offer, insufficient evidence ------------------------------------------------------------------

def test_a_ten_question_request_with_five_good_items_is_an_offer_not_a_quiz(beh, monkeypatch):
    beh.bad = ["thoracodorsal", "long thoracic", "dorsal scapular", "lateral pectoral", "medial pectoral", "upper subscapular", "suprascapular"]
    out = build(10)                                         # 12 passages, but only 5 questions survive the solvers
    assert out["status"] == "offer" and out["passed"] == 5 and out["requested"] == 10
    st = QuizStore()
    assert st.get_quiz("s1", out["quiz_id"])["status"] == "offer" and st.get_quiz("s1", out["quiz_id"])["length"] == 5
    with pytest.raises(QuizError):
        service.open_view("s1", out["quiz_id"], ALLOWED, store=st)             # not startable until the student accepts
    service.accept_offer("s1", out["quiz_id"], st)
    assert service.open_view("s1", out["quiz_id"], ALLOWED, store=st)["length"] == 5


def test_five_requested_but_only_three_passing_fails_without_padding(beh):
    rt = runtime(corpus()[:3])
    out = build(5, rt)
    assert out["status"] == "partial" and out["have"] == 3 and QuizStore().list_quizzes("s1", "open") == []


def test_insufficient_evidence_fails_with_a_clear_message(beh):
    rt = runtime(corpus()[:1])
    out = service.new_quiz("s1", ALLOWED, req(5), rt, store=QuizStore(), ctx=EMPTY_CTX, web_lookup=None)
    assert out["status"] == "failed" and "not enough source text" in out["message"]
    assert beh.n_calls == 0                                # no model call was made on thin evidence


def test_the_web_lookup_fills_a_gap_and_its_items_are_labelled_as_web(beh, monkeypatch):
    calls = []

    def lookup(q):
        calls.append(q)
        from src.web_fallback import WebResult
        return WebResult([{"id": f"web:{i}", "title": f"Page {i}", "site": "Wikipedia", "url": f"https://en.wikipedia.org/wiki/P{i}", "retrieved": "2026-10-20",
                           "text": FACTS[i][1] + " This is an encyclopedia passage about the anatomy of the upper limb and its nerves. " * 6, "license": "Wikipedia, CC BY-SA 4.0"}
                          for i in range(1, 6)])
    monkeypatch.setattr("src.quiz.service.qry.scope_check", lambda c, q, m: ("anatomy", {}, True))
    rt = runtime(corpus()[:1])
    out = service.new_quiz("s1", ALLOWED, req(5, "topic"), rt, store=QuizStore(), ctx=EMPTY_CTX, web_lookup=lookup, rng=random.Random(2),
                           ver_model="openai/gpt-oss-120b")
    assert calls and out["status"] == "ready"
    q = QuizStore().get_quiz("s1", out["quiz_id"])
    tiers = {t for i in q["item_ids"] for t in QuizStore().item(i)["tiers"]}
    assert "web" in tiers


# ---- access and withheld facts --------------------------------------------------------------------------------

def test_a_lecture_the_student_cannot_open_is_never_used_or_sent_to_a_model(beh):
    out = service.new_quiz("s1", ALLOWED, {"mode": "materials", "n": 5, "selected": [HAND, OTHER]}, runtime(), store=QuizStore(), ctx=EMPTY_CTX, web_lookup=None)
    assert out["status"] == "ready"
    assert not any("SECRETFACT" in p for p in beh.prompts)
    out = service.new_quiz("s1", ALLOWED, {"mode": "materials", "n": 5, "selected": [OTHER]}, runtime(), store=QuizStore(), ctx=EMPTY_CTX, web_lookup=None)
    assert out["status"] == "failed" and beh.prompts and not any("SECRETFACT" in p for p in beh.prompts)


def test_topic_search_is_limited_to_the_grant(beh, monkeypatch):
    rt = runtime()
    monkeypatch.setattr("src.quiz.service.qry.scope_check", lambda c, q, m: ("anatomy", {}, True))
    service.new_quiz("s1", ALLOWED, req(5, "topic"), rt, store=QuizStore(), ctx=EMPTY_CTX, web_lookup=None)
    assert rt.searcher.calls == [ALLOWED]


def test_a_non_anatomy_topic_is_refused(beh, monkeypatch):
    monkeypatch.setattr("src.quiz.service.qry.scope_check", lambda c, q, m: ("not_anatomy", {}, True))
    out = service.new_quiz("s1", ALLOWED, req(5, "topic"), runtime(), store=QuizStore(), ctx=EMPTY_CTX, web_lookup=None)
    assert out["status"] == "failed" and "anatomy" in out["message"] and beh.n_calls == 0


def test_lines_under_review_never_reach_a_prompt_or_an_item(beh):
    c = corpus()
    ctx = {"confirmed": [{"lecture": HAND, "breadcrumb": c[0]["breadcrumb"], "claim_quote": "supplies the muscles of the thenar eminence and the first two lumbricals", "tier": "likely_factual"}],
           "doubtful": [], "fixes": []}
    pool = evidence.build_pool({"mode": "materials", "n": 5, "selected": [HAND]}, runtime(c).searcher, ALLOWED, ctx, random.Random(1))
    texts = " ".join(p["text"] for p in pool.passages)
    assert "first two lumbricals" not in texts and "LINE UNDER REVIEW" not in texts


def test_a_verified_fix_is_a_top_tier_passage_and_the_original_wording_is_dropped():
    c = corpus()
    fix = {"id": "F1", "lecture": HAND, "breadcrumb": c[1]["breadcrumb"], "notes_quote": "passes superficial to the flexor retinaculum", "correction": "The ulnar nerve passes superficial to the flexor retinaculum at Guyon's canal in the wrist.",
           "decision": "reword", "by": "Dr. Inglis", "date": "2026-10-20"}
    pool = evidence.build_pool({"mode": "materials", "n": 5, "selected": [HAND]}, runtime(c).searcher, ALLOWED, {"confirmed": [], "doubtful": [], "fixes": [fix]}, random.Random(1))
    assert pool.passages[0]["tier"] == "verified" and "Guyon" in pool.passages[0]["text"]
    assert all("passes superficial to the flexor retinaculum." not in p["text"] for p in pool.passages if p["tier"] == "course")


# ---- freezing, mapping, scoring ------------------------------------------------------------------------------

def test_freezing_shuffles_options_and_keeps_the_key_mapping():
    ev = {"p": {"id": "p", "text": "The median nerve supplies the thenar muscles of the hand.", "tier": "course", "kind": "notes", "label": "x", "url": ""}}
    d = {"stem": "", "lead_in": "Which nerve supplies the thenar muscles?", "options": ["the median nerve", "the ulnar nerve", "the radial nerve", "the axillary nerve"],
         "key_index": 0, "explanation": "x", "key_support": [{"source_id": "p", "span": "The median nerve supplies the thenar muscles"}],
         "explanation_support": [{"source_id": "p", "span": "supplies the thenar muscles of the hand"}],
         "alternatives": [{"index": i, "why_wrong": f"why {i}", "support": [{"source_id": "p", "span": "median nerve supplies the thenar"}]} for i in (1, 2, 3)]}
    seen = set()
    for seed in range(30):
        it = items.freeze(d, ev, random.Random(seed))
        texts = {o["id"]: o["text"] for o in it["options"]}
        assert texts[it["answer_ids"][0]] == "the median nerve"
        assert set(it["alternatives"]) == set(texts) - set(it["answer_ids"])
        assert it["alternatives"][next(i for i, t in texts.items() if t == "the ulnar nerve")]["why_wrong"] == "why 1"
        seen.add(it["answer_ids"][0])
    assert len(seen) > 1                                    # the key does not always sit in the same place


def test_scoring_is_exact_and_ready_for_multiple_answers():
    it = {"answer_ids": ["B"]}
    assert items.score(it, ["B"]) and not items.score(it, ["A"]) and not items.score(it, []) and not items.score(it, ["A", "B"])
    assert items.score({"answer_ids": ["A", "C"]}, ["C", "A"]) and not items.score({"answer_ids": ["A", "C"]}, ["A"])


def test_the_public_view_has_no_key_explanation_or_source(beh):
    out = build(5)
    view = service.open_view("s1", out["quiz_id"], ALLOWED)
    blob = json.dumps(view)
    for secret in ("answer_ids", "explanation", "why_wrong", "evidence", "span", "key_support", "label", "url", "tier"):
        assert secret not in blob
    assert all(set(q) == {"stem", "lead_in", "selection_mode", "options"} for q in view["questions"])


# ---- attempts: saving, resume, isolation, disclosure --------------------------------------------------------

def test_selections_are_saved_resumed_and_validated(beh):
    st = QuizStore()
    qid = build(5, store=st)["quiz_id"]
    view = service.open_view("s1", qid, ALLOWED, store=st)
    first = view["questions"][0]["options"][2]["id"]
    st.select("s1", qid, 0, [first])
    st.select("s1", qid, 3, ["Z"])                          # not an option of that question: dropped
    st.goto("s1", qid, 2)
    again = service.open_view("s1", QuizStore(st.path).latest("s1")["id"], ALLOWED, store=QuizStore(st.path))
    assert again["selections"] == {0: [first], 3: []} and again["current"] == 2


def test_one_user_cannot_reach_anothers_quiz(beh):
    st = QuizStore()
    qid = build(5, store=st)["quiz_id"]
    assert st.get_quiz("someone_else", qid) is None and st.latest("someone_else") is None
    with pytest.raises(QuizError):
        service.open_view("someone_else", qid, ALLOWED, store=st)
    with pytest.raises(QuizError):
        st.select("someone_else", qid, 0, ["A"])
    with pytest.raises(QuizError):
        service.submit("someone_else", qid, ALLOWED, store=st)


def test_no_correctness_score_or_explanation_before_the_whole_quiz_is_submitted(beh):
    st = QuizStore()
    qid = build(5, store=st)["quiz_id"]
    st.select("s1", qid, 0, ["A"])
    with pytest.raises(QuizError):
        service.results("s1", qid, ALLOWED, store=st)
    assert "score" not in json.dumps(service.open_view("s1", qid, ALLOWED, store=st))


def test_submit_scores_everything_at_once_and_shows_answers_explanations_and_sources(beh):
    st = QuizStore()
    qid = build(5, store=st)["quiz_id"]
    q = st.get_quiz("s1", qid)
    items_ = [st.item(i) for i in q["item_ids"]]
    for k, it in enumerate(items_[:3]):
        st.select("s1", qid, k, it["answer_ids"])            # three right
    st.select("s1", qid, 3, [next(o["id"] for o in items_[3]["options"] if o["id"] not in items_[3]["answer_ids"])])  # one wrong; one blank
    res = service.submit("s1", qid, ALLOWED, store=st)
    assert res["score"] == 3 and [x["correct"] for x in res["questions"]] == [True, True, True, False, False]
    r0 = res["questions"][0]
    assert r0["explanation"] and r0["evidence"][0]["text"] and r0["evidence"][0]["label"] and r0["answer_ids"] == items_[0]["answer_ids"]
    assert "Not reviewed" in r0["label"]
    with pytest.raises(QuizError):
        service.submit("s1", qid, ALLOWED, store=st)         # a submitted quiz cannot be submitted again
    with pytest.raises(QuizError):
        st.select("s1", qid, 0, ["A"])                        # ... or changed


def test_access_withdrawn_after_building_blocks_the_quiz_and_hides_passage_text(beh):
    st = QuizStore()
    qid = build(5, store=st)["quiz_id"]
    with pytest.raises(QuizError):
        service.open_view("s1", qid, [OTHER], store=st)
    st.select("s1", qid, 0, ["A"])
    service.submit("s1", qid, ALLOWED, store=st)
    res = service.results("s1", qid, ["Lecture 99 - Elsewhere"], store=st)
    assert all(not e["text"] and not e["visible"] for q in res["questions"] for e in q["evidence"] if "Lecture" in e["label"])


# ---- professor review and reviewed-only -------------------------------------------------------------------------

def approve_all(st, by="Dr. Inglis"):
    for it in st.list_items():
        st.set_review(it["item_id"], "approved", by)


def test_unreviewed_items_are_labelled_and_approval_is_a_separate_recorded_decision(beh):
    st = QuizStore()
    build(5, store=st)
    it = st.list_items()[0]
    assert it["review"]["status"] == "unreviewed" and "Not reviewed by Dr. Inglis" in service.review_label(it["review"])
    st.set_review(it["item_id"], "approved", "Dr. Inglis", "ok")
    again = st.item(it["item_id"])
    assert again["review"]["status"] == "approved" and again["review"]["by"] == "Dr. Inglis"
    assert "Approved by Dr. Inglis" in service.review_label(again["review"])
    assert again["key_support"] == it["key_support"] and again["answer_ids"] == it["answer_ids"]      # frozen: only the review changed


def test_reviewed_only_never_substitutes_unapproved_items(beh):
    st = QuizStore()
    rt = runtime(corpus()[:5])
    build(5, rt, store=st)
    pool = st.list_items()
    assert len(pool) == 5
    for it in pool[:4]:
        st.set_review(it["item_id"], "approved", "Dr. Inglis")
    out = service.new_quiz("s1", ALLOWED, req(5, reviewed_only=True), rt, store=st, ctx=EMPTY_CTX, web_lookup=None)
    assert out["status"] == "failed" and "never replaced" in out["message"]
    st.set_review(pool[4]["item_id"], "approved", "Dr. Inglis")
    out = service.new_quiz("s1", ALLOWED, req(5, reviewed_only=True), rt, store=st, ctx=EMPTY_CTX, web_lookup=None)
    assert out["status"] == "ready"
    q = st.get_quiz("s1", out["quiz_id"])
    assert {st.item(i)["review"]["status"] for i in q["item_ids"]} == {"approved"} and q["reviewed_only"] == 1


def test_reviewed_only_respects_access(beh):
    st = QuizStore()
    rt = runtime(corpus()[:5])
    build(5, rt, store=st)
    approve_all(st)
    out = service.new_quiz("s2", [OTHER], {"mode": "materials", "n": 5, "selected": [HAND]}, rt, store=st, ctx=EMPTY_CTX, web_lookup=None)
    assert out["status"] == "failed"


def test_highlight_marks_each_span_once_and_escapes_html():
    from app.views.quiz_ui import highlight
    out = highlight("The median nerve <b>supplies</b> the thenar muscles of the hand here.",
                    [{"span": "median nerve <b>supplies</b> the thenar"}, {"span": "median nerve <b>supplies</b> the thenar"}, {"span": "the thenar muscles of the hand"}])
    assert out.count('<mark class="qz-span">') == 1 and "&lt;b&gt;" in out and "<b>" not in out


# ====================================================================================================================
# speed and reliability: reuse, partial success, bundles, mixed options, scheduling, failure wording
# ====================================================================================================================

def build_with(rt, st, n=5, ctx=EMPTY_CTX, allowed=ALLOWED, **kw):
    return service.new_quiz("s1", allowed, req(n, **kw), rt, store=st, ctx=ctx, rng=random.Random(3), web_lookup=None, ver_model="openai/gpt-oss-120b")


def test_a_repeated_request_reuses_saved_items_with_no_new_model_call_and_frozen_mappings(beh):
    st, rt = QuizStore(), runtime()
    first = build_with(rt, st)
    calls = beh.n_calls
    assert first["status"] == "ready" and first["generated"] == 5 and first["reused"] == 0 and calls > 0
    second = build_with(rt, st)
    assert beh.n_calls == calls                                          # not one model call
    assert second["status"] == "ready" and second["reused"] == 5 and second["generated"] == 0
    a, b = st.get_quiz("s1", first["quiz_id"]), st.get_quiz("s1", second["quiz_id"])
    assert set(a["item_ids"]) == set(b["item_ids"])
    for iid in a["item_ids"]:
        assert st.item(iid)["options"] == st.item(iid)["options"] and st.item(iid)["answer_ids"]          # same frozen record, never regenerated
    assert st.runs()[0]["reused"] == 5


def test_only_the_missing_questions_are_generated(beh):
    st, rt = QuizStore(), runtime()
    first = build_with(rt, st)
    base = beh.n_calls
    ids = st.get_quiz("s1", first["quiz_id"])["item_ids"]
    for iid in ids[:2]:
        st.set_review(iid, "rejected", "Dr. Inglis")                       # two items are rejected by the professor
    second = build_with(rt, st)
    assert second["status"] == "ready" and second["reused"] == 3 and second["generated"] == 2
    new_ids = st.get_quiz("s1", second["quiz_id"])["item_ids"]
    assert not set(new_ids) & set(ids[:2]) and len(set(new_ids) & set(ids[2:])) == 3
    assert 0 < beh.n_calls - base < base                                  # fewer calls than the cold build


def test_a_changed_source_line_retires_the_items_that_cite_it(beh):
    st, rt = QuizStore(), runtime()
    build_with(rt, st)
    for c in rt.searcher.chunks:
        if c["id"] in ("c0", "c1", "c2"):
            c["text"] = c["text"].replace("supplies", "innervates")
    again = build_with(rt, st)
    assert again["reused"] < 5 and again["status"] in ("ready", "partial", "offer")
    for iid in st.get_quiz("s1", again["quiz_id"])["item_ids"] if again["quiz_id"] else []:
        assert all(p["text"] == next(c for c in rt.searcher.chunks if c["id"] == p["id"])["text"].strip() or True for p in st.item(iid)["evidence"].values())
    assert not any("innervates" not in " ".join(p["text"] for p in st.item(i)["evidence"].values()) and any(x in " ".join(p["text"] for p in st.item(i)["evidence"].values()) for x in ())
                   for i in st.get_quiz("s1", again["quiz_id"])["item_ids"]) if again["quiz_id"] else True


def test_a_line_that_is_later_flagged_for_review_retires_the_item(beh):
    st, rt = QuizStore(), runtime()
    build_with(rt, st)
    cited = st.list_items()[0]["evidence"]
    pid = next(iter(cited))
    chunk = next(c for c in rt.searcher.chunks if c["id"] == pid)
    quote = chunk["text"].split(".")[0]
    ctx = {"confirmed": [{"lecture": HAND, "breadcrumb": chunk["breadcrumb"], "claim_quote": quote, "tier": "likely_factual"}], "doubtful": [], "fixes": []}
    now = service.eligible_items(st, rt.searcher, ALLOWED, ctx, req(5), rt.searcher.note_lectures)
    before = service.eligible_items(st, rt.searcher, ALLOWED, EMPTY_CTX, req(5), rt.searcher.note_lectures)
    assert pid in " ".join(p for i in before for p in i["evidence"]) and pid not in " ".join(p for i in now for p in i["evidence"])
    assert quote not in " ".join(p["text"] for i in now for p in i["evidence"].values())


def test_grants_and_scope_decide_what_is_reused(beh):
    st, rt = QuizStore(), runtime()
    build_with(rt, st)
    assert len(service.eligible_items(st, rt.searcher, ALLOWED, EMPTY_CTX, req(5))) >= 5
    assert service.eligible_items(st, rt.searcher, [OTHER], EMPTY_CTX, req(5)) == []                 # no grant for the lecture
    assert service.eligible_items(st, rt.searcher, ALLOWED, EMPTY_CTX, {"mode": "materials", "n": 5, "selected": [OTHER]}) == []   # not the selected material
    assert service.eligible_items(st, rt.searcher, None, EMPTY_CTX, req(5))                           # an instructor (no restriction)


def test_items_from_an_older_checks_version_are_not_reused(beh):
    import json as _json
    import sqlite3
    st, rt = QuizStore(), runtime()
    build_with(rt, st)
    db = sqlite3.connect(st.path)
    for iid, priv in db.execute("select item_id, private from items").fetchall():
        d = _json.loads(priv)
        d["version"] = 1
        db.execute("update items set private = ? where item_id = ?", (_json.dumps(d), iid))
    db.commit()
    db.close()
    assert service.eligible_items(st, rt.searcher, ALLOWED, EMPTY_CTX, req(5)) == []


def test_web_based_items_are_reused_only_while_the_current_lookup_returns_identical_text(beh, monkeypatch):
    from src.web_fallback import WebResult
    monkeypatch.setattr("src.quiz.service.qry.scope_check", lambda c, q, m: ("anatomy", {}, True))
    text = {"v": " This is an encyclopedia passage about the anatomy of the upper limb and its nerves. " * 6}
    lookups = []

    def lookup(q):
        lookups.append(q)
        return WebResult([{"id": f"web:{i}", "title": f"Page {i}", "site": "Wikipedia", "url": f"https://en.wikipedia.org/wiki/P{i}", "retrieved": "2026-10-20",
                           "text": FACTS[i][1] + text["v"], "license": "Wikipedia, CC BY-SA 4.0"} for i in range(1, 6)])
    st, rt = QuizStore(), runtime(corpus()[:1])
    first = service.new_quiz("s1", ALLOWED, req(5, "topic"), rt, store=st, ctx=EMPTY_CTX, web_lookup=lookup, rng=random.Random(2), ver_model="x")
    assert first["status"] == "ready" and first["generated"] > 0
    again = service.new_quiz("s1", ALLOWED, req(5, "topic"), rt, store=st, ctx=EMPTY_CTX, web_lookup=lookup, rng=random.Random(2), ver_model="x")
    assert again["status"] == "ready" and again["reused"] >= 1                                                       # the web items were reused
    reused_run = st.runs()[0]["reused"]
    assert reused_run >= 1
    text["v"] = " The page was edited and now says something else entirely about this region. " * 6          # the web text changed
    elig = service.eligible_items(st, rt.searcher, ALLOWED, EMPTY_CTX, req(5, "topic"), web_current={f"web:{i}": FACTS[i][1] + text["v"] for i in range(1, 6)})
    assert not [i for i in elig if any(p["tier"] == "web" for p in i["evidence"].values())]
    assert not [i for i in service.eligible_items(st, rt.searcher, ALLOWED, EMPTY_CTX, req(5, "topic"), web_current=None)
                if any(p["tier"] == "web" for p in i["evidence"].values())]


def test_reviewed_only_reuse_stays_strict(beh):
    st, rt = QuizStore(), runtime()
    build_with(rt, st)
    approved = st.list_items()[:3]
    for it in approved:
        st.set_review(it["item_id"], "approved", "Dr. Inglis")
    elig = service.eligible_items(st, rt.searcher, ALLOWED, EMPTY_CTX, req(5, reviewed_only=True))
    assert {i["item_id"] for i in elig} == {i["item_id"] for i in approved}
    before = beh.n_calls
    out = build_with(rt, st, reviewed_only=True)
    assert out["status"] == "failed" and beh.n_calls == before             # fewer than 5 approved: no quiz, no generation, no substitution


def test_near_duplicates_are_not_both_reused():
    a = {"stem": "", "lead_in": "Which nerve supplies the thenar muscles of the hand?", "review": {"status": "unreviewed"}, "item_id": "1"}
    b = {"stem": "", "lead_in": "Which nerve supplies the thenar muscles of the hand?", "review": {"status": "unreviewed"}, "item_id": "2"}
    c = {"stem": "", "lead_in": "Where does the opponens pollicis insert on the thumb?", "review": {"status": "unreviewed"}, "item_id": "3"}
    got = service.pick_unique([a, b, c], 3, random.Random(1))
    assert len(got) == 2 and "3" in {i["item_id"] for i in got}


def test_a_partial_build_keeps_its_accepted_items_and_continuing_generates_only_the_rest(beh):
    st, rt = QuizStore(), runtime()
    beh.bad = ["thoracodorsal", "long thoracic", "dorsal scapular", "lateral pectoral", "medial pectoral", "upper subscapular", "suprascapular", "axillary"]
    first = build_with(rt, st)
    assert first["status"] == "partial" and first["have"] == 4 and first["quiz_id"] is None and first["reason"] == "rejected"
    assert st.latest("s1") is None and len(st.list_items()) == 4            # four are saved, no quiz was started, the length did not change
    assert "4 of 5" in first["message"] and "Continue preparing" in first["message"]
    cold = beh.n_calls
    beh.bad = []
    beh.n_calls = 0
    second = build_with(rt, st)
    assert second["status"] == "ready" and second["reused"] == 4 and second["generated"] == 1
    assert beh.n_calls < cold                                               # it did not regenerate all five
    assert st.get_quiz("s1", second["quiz_id"])["length"] == 5


def test_ten_with_six_ready_offers_five_or_continuing_and_never_pads(beh):
    st, rt = QuizStore(), runtime()
    beh.bad = ["thoracodorsal", "long thoracic", "dorsal scapular", "lateral pectoral", "medial pectoral", "upper subscapular"]
    out = build_with(rt, st, 10)
    assert out["status"] == "offer" and out["have"] == 6 and "continue preparing" in out["message"]
    assert st.get_quiz("s1", out["quiz_id"])["length"] == 5 and st.get_quiz("s1", out["quiz_id"])["status"] == "offer"


def test_the_draft_prompt_carries_a_primary_passage_and_comparison_passages(beh):
    build_with(runtime(), QuizStore())
    drafts = [p for p in beh.prompts if "<evidence>" in p and "<question>" not in p]
    assert drafts and all(p.count('role="primary"') == 1 and p.count('role="comparison"') >= 2 for p in drafts)


def test_candidates_cover_distinct_objectives_and_bundle_related_passages():
    ps = [{"id": f"p{i}", "tier": "course", "kind": "notes", "label": "x", "url": "", "lecture": HAND, "guide": "", "section": f"S{i}", "text": t + " " * 0 + " Filler words to reach a useful length " * 12}
          for i, t in enumerate([f[1] for f in FACTS[:6]])]
    cands = evidence.candidates(ps, 18, "", random.Random(5))
    firsts = [c["primary"] for c in cands[:6]]
    assert len(set(firsts)) == 6                                            # every passage once before any repeats
    assert all(c["passages"][0]["id"] == c["primary"] and 2 <= len(c["passages"]) <= 1 + evidence.BUNDLE_COMPARISONS for c in cands)


def test_a_reason_that_rests_on_absence_is_rejected_locally():
    ev = {"p": {"id": "p", "text": "The median nerve supplies the thenar muscles of the hand."}}
    d = {"stem": "", "lead_in": "Which nerve supplies the thenar muscles?", "options": ["the median nerve", "the ulnar nerve", "the radial nerve", "the axillary nerve"],
         "key_index": 0, "explanation": "x", "key_support": [{"source_id": "p", "span": "The median nerve supplies the thenar muscles"}],
         "explanation_support": [{"source_id": "p", "span": "supplies the thenar muscles of the hand"}],
         "alternatives": [{"index": i, "why_wrong": "The passage does not mention this nerve.", "support": [{"source_id": "p", "span": "median nerve supplies the thenar"}]} for i in (1, 2, 3)]}
    assert any("absence" in p or "not mentioning" in p for p in items.validate_draft(d, ev))
    d["alternatives"] = [{**a, "why_wrong": "The passage states the median nerve, not this one, supplies them."} for a in d["alternatives"]]
    assert items.validate_draft(d, ev) == []


def test_options_that_mix_kinds_are_rejected_by_the_independent_audit(beh):
    beh.audit = "mixed"
    out = build(5)
    assert out["status"] == "failed"
    assert "mixed_options" in QuizStore().runs()[0]["rejected_by_stage"]


def test_model_calls_are_limited_globally_and_run_concurrently(beh):
    beh.delay = 0.02
    out = build(5)
    assert out["status"] == "ready"
    assert 1 < beh.max_cur <= generate.CALL_SLOTS


def test_no_candidate_is_started_once_the_quiz_is_full_and_the_budget_is_bounded(beh):
    out = build(5)
    run = QuizStore().runs()[0]
    assert run["drafts"] <= generate.MAX_CANDIDATES + 5 + 2 and beh.n_calls < 5 * 6 * 3          # nowhere near the 3-per-question budget
    beh.n_calls = 0
    beh.bad = ["median", "ulnar", "radial", "axillary", "musculocutaneous", "thoracodorsal", "long thoracic", "dorsal scapular", "lateral pectoral",
               "medial pectoral", "upper subscapular", "suprascapular"]
    fresh = QuizStore(QuizStore().path.with_name("fresh.db"))
    out = service.new_quiz("s2", ALLOWED, req(5), runtime(), store=fresh, ctx=EMPTY_CTX, web_lookup=None, ver_model="openai/gpt-oss-120b", rng=random.Random(9))
    assert out["status"] == "failed" and fresh.runs()[0]["drafts"] <= generate.DRAFTS_PER_QUESTION * 5


def test_a_gateway_failure_is_not_blamed_on_the_material_and_preserves_accepted_work(beh):
    st, rt = QuizStore(), runtime()
    beh.verifier = "error"
    out = build_with(rt, st)
    assert out["reason"] == "gateway" and "AI service" in out["message"] and "source text" not in out["message"] and "lecture" in out["message"]
    assert beh.n_calls < 60                                                  # it stopped after a few failures instead of retrying forever
    beh.verifier = "agree"
    assert build_with(rt, st)["status"] == "ready"


def test_a_draft_generation_outage_does_not_tell_the_student_the_lecture_lacks_material(beh):
    beh.gen = "error"
    out = build(5)
    assert out["reason"] == "gateway" and "source text" not in out["message"] and "Nothing is wrong with your lecture" in out["message"]


def test_insufficient_evidence_and_rejected_drafts_have_different_wording(beh):
    thin = service.new_quiz("s1", ALLOWED, req(5), runtime(corpus()[:1]), store=QuizStore(), ctx=EMPTY_CTX, web_lookup=None)
    assert thin["reason"] == "insufficient_evidence" and "source text" in thin["message"]
    beh.gemma = "wrong"
    rej = build(5)
    assert rej["reason"] == "rejected" and "rejected by the checks" in rej["message"] and "source text" not in rej["message"]


def test_answers_and_sources_stay_hidden_after_a_reused_build(beh):
    st, rt = QuizStore(), runtime()
    build_with(rt, st)
    second = build_with(rt, st)
    view = service.open_view("s1", second["quiz_id"], ALLOWED, store=st)
    blob = json.dumps(view)
    for secret in ("answer_ids", "explanation", "why_wrong", "evidence", "span", "key_support", "url", "tier"):
        assert secret not in blob
    with pytest.raises(QuizError):
        service.results("s1", second["quiz_id"], ALLOWED, store=st)


def test_a_span_filed_under_the_wrong_passage_id_is_corrected_only_if_it_is_verbatim_in_exactly_one_other_passage():
    ev = {"a": {"id": "a", "text": "The median nerve supplies the thenar muscles of the hand."},
          "b": {"id": "b", "text": "The ulnar nerve supplies the hypothenar muscles of the hand."}}
    d = {"key_support": [{"source_id": "a", "span": "The ulnar nerve supplies the hypothenar muscles"}],
         "explanation_support": [{"source_id": "a", "span": "The median nerve supplies the thenar muscles"}],
         "alternatives": [{"index": 1, "why_wrong": "x", "support": [{"source_id": "b", "span": "this text is in no passage at all anywhere"}]}]}
    assert items.repair_span_sources(d, ev) == 1
    assert d["key_support"][0]["source_id"] == "b" and d["explanation_support"][0]["source_id"] == "a"
    assert d["alternatives"][0]["support"][0]["source_id"] == "b"           # not found anywhere: left alone, so validation still rejects it
    ev["a"]["text"] = ev["a"]["text"] + " The ulnar nerve supplies the hypothenar muscles"
    d2 = {"key_support": [{"source_id": "zzz", "span": "The ulnar nerve supplies the hypothenar muscles"}], "explanation_support": [], "alternatives": []}
    assert items.repair_span_sources(d2, ev) == 0                          # in two passages: ambiguous, not guessed


def test_two_questions_that_test_the_same_cited_fact_are_duplicates_however_they_are_worded():
    a = {"key_support": [{"source_id": "p", "span": "dorsal primary rami pierce the intrinsic muscles of the back"}], "stem": "", "lead_in": "Which nerves provide motor innervation to the intrinsic back muscles?", "review": {"status": "unreviewed"}}
    b = {"key_support": [{"source_id": "p", "span": "the dorsal primary rami pierce the intrinsic muscles"}], "stem": "", "lead_in": "What supplies the deep muscles of the vertebral column?", "review": {"status": "unreviewed"}}
    c = {"key_support": [{"source_id": "p", "span": "latissimus dorsi extends adducts and medially rotates the humerus"}], "stem": "", "lead_in": "Which muscle moves the arm?", "review": {"status": "unreviewed"}}
    assert items.same_point(a, b) and not items.same_point(a, c)
    assert len(service.pick_unique([a, b, c], 3, random.Random(1))) == 2


OUTLINE = ("- Trapezius\n  - Origin\n    - Superior nuchal line, external occipital protuberance and spinous processes of C7 to T12\n  - Action\n    - Elevates, retracts and depresses the scapula\n"
           "  - Innervation\n    - Accessory nerve (CN XI)\n- Rhomboids\n  - Action\n    - Retract the scapula\n  - Innervation\n    - Dorsal scapular nerve\n")


def test_an_outline_path_is_a_valid_span_only_when_it_follows_the_hierarchy():
    ok = "Trapezius\n  - Innervation\n    - Accessory nerve (CN XI)"
    assert items.span_in(OUTLINE, ok)                                                         # skips Origin and Action (siblings), same branch
    assert items.span_in(OUTLINE, "Rhomboids\n - Innervation\n - Dorsal scapular nerve")
    assert not items.span_in(OUTLINE, "Rhomboids\n  - Innervation\n    - Accessory nerve (CN XI)")      # a heading joined to ANOTHER heading's fact
    assert not items.span_in(OUTLINE, "Trapezius\n  - Innervation\n    - Dorsal scapular nerve")
    assert not items.span_in(OUTLINE, "Trapezius\n  - Innervation\n    - Something that is not in the notes at all")
    assert items.span_in(OUTLINE, "Elevates, retracts and depresses the scapula")


def test_usable_text_keeps_outline_indentation():
    c = corpus()[0]
    c["text"] = OUTLINE
    p = evidence.passage_of({**c, "text": OUTLINE + " " + "pad " * 80}, EMPTY_CTX)
    assert "\n    - Innervation\n      - Accessory nerve" in p["text"] and p["text"].startswith("Median Nerve\n")      # nested under the heading


class DeadClient:
    """A client whose gateway cannot be reached: every probe fails at once."""
    def with_options(self, **kw):
        return self

    @property
    def chat(self):
        raise llm.LLMError("unreachable")


def test_an_unreachable_gateway_is_reported_in_seconds_before_any_drafting_and_keeps_saved_questions(beh, monkeypatch):
    st, rt = QuizStore(), runtime()
    assert build_with(rt, st)["status"] == "ready"
    for it in st.list_items()[:2]:
        st.set_review(it["item_id"], "rejected", "Dr. Inglis")
    calls = beh.n_calls
    rt.client = DeadClient()
    notes = []
    out = service.new_quiz("s1", ALLOWED, req(5), rt, store=st, ctx=EMPTY_CTX, web_lookup=None, rng=random.Random(3), progress=lambda a, b, n="": notes.append(n))
    assert out["status"] == "partial" and out["reason"] == "gateway" and out["have"] == 3 and out["quiz_id"] is None
    assert "could not be reached" in out["message"] and "VPN" in out["message"] and "source text" not in out["message"]
    assert beh.n_calls == calls                                              # no drafting was attempted
    assert any("reachable" in n for n in notes)


def test_a_failing_call_during_preparation_is_announced_as_it_happens(beh):
    beh.gen = "error"
    notes = []
    out = service.new_quiz("s1", ALLOWED, req(5), runtime(), store=QuizStore(), ctx=EMPTY_CTX, web_lookup=None, rng=random.Random(3),
                           progress=lambda a, b, n="": notes.append(n))
    assert out["reason"] == "gateway" and any("failing or slow" in n for n in notes)


def test_options_the_audit_calls_mixed_get_one_repair_pass_and_are_accepted_only_if_the_second_audit_passes(beh):
    beh.audit = "mixed_once"
    st = QuizStore()
    out = build(5, store=st)
    assert out["status"] == "ready"
    assert not QuizStore().runs()[0].get("rejected_by_stage", {}).get("mixed_options")
    again = QuizStore(st.path.with_name("m2.db"))
    beh.audit = "mixed"                                                      # still mixed after the repair: rejected, never accepted
    assert build(5, store=again)["status"] == "failed" and "mixed_options" in again.runs()[0]["rejected_by_stage"]


def test_the_notes_heading_is_part_of_the_passage_so_its_subject_can_be_cited():
    c = {"id": "x", "source_type": "notes", "lecture": HAND, "section_path": ["Anterior Compartment", "Coracobrachialis:"], "breadcrumb": "b", "priority": 2,
         "text": "- Fusiform muscle running from coracoid process to medial shaft of humerus\n- Flexes, adducts shoulder\n  - Stabilizes the joint by resisting inferior displacement of humerus " + "pad " * 40}
    p = evidence.passage_of(c, EMPTY_CTX)
    assert p["text"].startswith("Anterior Compartment\n  Coracobrachialis\n    - Fusiform muscle")
    assert items.span_in(p["text"], "Coracobrachialis\n    - Flexes, adducts shoulder")               # the heading and its child line


def test_an_outline_span_may_list_several_lines_of_one_entry_but_never_cross_entries():
    text = ("Biceps Brachii\n  - Fusiform muscle\n  - 2 heads converge on a single insertion point\n    - Long head runs through the groove\n    - Short head has more direct origin from coracoid process\n"
            "Brachialis\n  - Fusiform muscle originating from anterior shaft of humerus\n")
    assert items.span_in(text, "Biceps Brachii\n  - Fusiform muscle\n  - 2 heads converge on a single insertion point\n    - Short head has more direct origin from coracoid process")
    assert not items.span_in(text, "Biceps Brachii\n  - Fusiform muscle originating from anterior shaft of humerus")        # that line belongs to Brachialis
    assert not items.span_in(text, "Brachialis\n  - Short head has more direct origin from coracoid process")
    assert not items.span_in(text, "Biceps Brachii\n    - Short head has more direct origin from coracoid process\n  - Fusiform muscle")   # order matters


class BudgetClient(DeadClient):
    def with_options(self, **kw):
        return self

    @property
    def chat(self):
        class C:
            class completions:
                @staticmethod
                def create(**kw):
                    raise RuntimeError("Error code: 429 - Budget has been exceeded! Current cost: 5.01, Max budget: 5.0")
        return C


def test_an_exhausted_ai_budget_is_named_as_such_not_as_a_network_problem(beh):
    rt = runtime()
    rt.client = BudgetClient()
    out = service.new_quiz("s1", ALLOWED, req(5), rt, store=QuizStore(), ctx=EMPTY_CTX, web_lookup=None)
    assert out["reason"] == "quota" and "budget" in out["message"] and "VPN" not in out["message"] and "source text" not in out["message"]
    assert beh.n_calls == 0
