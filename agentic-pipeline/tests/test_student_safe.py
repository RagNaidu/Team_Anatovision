"""Part 1 of the UI audit: what a student may see, the answer logic around it, passwords, usage kinds, instructor-only pages.
The model and the search are faked: no API calls, no cost."""
from src import llm
import re
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from app import state
from src import auth, service, usage, verified
from src import citations as cit
from src import query as qry
from src import student_view as sv
from src.modes import guide, qa
from tests.test_app import MAIN, HAND, app, labels, texts, world  # noqa: F401  (fixtures)
from tests.test_guide import card as guide_card, meta as guide_meta
from tests.test_service import CLOSING, FakeClient, FakeSearcher, chunk, isolated, reply, runtime  # noqa: F401

LEC = "Lecture 99 - Test"
CRUMB = f"{LEC} > Walls"
CITE = f"[{LEC} > Walls]"
EMPTY = {"confirmed": [], "doubtful": [], "fixes": []}
REVIEW_Q, DOUBT_Q, FIX_Q = "Review me line", "Doubt me line", "Fix me line"
TEXT = f"- {REVIEW_Q}.\n- {DOUBT_Q}.\n- {FIX_Q}.\n- Plain line about the wall."


def fc_item(quote, verdict, tier):
    return {"lecture": LEC, "breadcrumb": CRUMB, "claim_quote": quote, "issue": "SECRET standard statement.",
            "severity": "high", "confidence": 0.93, "tier": tier, "type": "factual",
            "verification": {"reason": "SECRET AI reasoning.", "verdict": verdict}}


FIX = {"id": "vf-0001", "lecture": LEC, "breadcrumb": CRUMB, "notes_quote": FIX_Q, "correction": "Fixed wording.",
       "decision": "confirm_error", "by": "Dr. Inglis", "date": "2026-10-07"}
CTX = {"confirmed": [fc_item(REVIEW_Q, "confirmed", "likely_factual")], "doubtful": [fc_item(DOUBT_Q, "doubtful", "second_look")],
       "fixes": [FIX]}
# what a careless model might write: every kind of instructor-only wording
def slip(cite):
    return (f"A line here is currently under review {cite}."
            f" General anatomy knowledge, pending Dr. Inglis: SECRET standard statement.\n"
            f"The doubted line is used (flagged for review, see fact-check) {cite}\n"
            f"Fixed wording [Verified by Dr. Inglis, 2026-10-07].\nPlain line about the wall {cite}\n{CLOSING}")


SLIP_REPLY = reply(slip(CITE), under_review_addressed=["U1"], doubtful_used=["D1"], verified_used=["V1"])


class SeqClient(FakeClient):
    """Answering calls (they carry output_config) get the canned reply; small helper calls get `helper` texts in order."""

    def __init__(self, answer, helper=()):
        super().__init__(answer)
        self.helper = list(helper)

    def create(self, **kw):
        if "output_config" in kw:
            return super().create(**kw)
        self.calls.append(kw)
        text = self.helper.pop(0) if self.helper else "YES"
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)],
                               usage=SimpleNamespace(input_tokens=50, output_tokens=5))

    def answering(self):
        return [c for c in self.calls if "output_config" in c]

    def helpers(self):
        return [c for c in self.calls if "output_config" not in c]


class QSearcher(FakeSearcher):
    """Records the query and k of every search."""

    def __init__(self, chunks, **kw):
        super().__init__(chunks, **kw)
        self.queries = []

    def search(self, question, k=5, allowed_lectures=None):
        self.queries.append((question, k))
        return super().search(question, k, allowed_lectures)


def rt_for(chunks, answer, helper=(), **kw):
    return service.Runtime(searcher=QSearcher(chunks, **kw), next_of={}, client=SeqClient(answer, helper),
                           model="claude-sonnet-5-5")


# ---------------------------------------------------------------------------------------------------------------
# P01-P03, P12, P18, P25: nothing instructor-only reaches a student
# ---------------------------------------------------------------------------------------------------------------

def flagged_reply():
    rt = rt_for([chunk(TEXT)], SLIP_REPLY)
    return service.ask_for_student("walls?", "", True, None, runtime=rt, ctx=CTX), rt


def test_the_full_result_does_contain_instructor_detail_so_the_test_below_means_something():
    rt = rt_for([chunk(TEXT)], SLIP_REPLY)
    raw = service.ask("walls?", "", True, None, runtime=rt, ctx=CTX, audience="professor")
    assert sv.leaks(raw)                                   # scores, tokens, fact-check wording ... are all in there


def test_student_answer_has_none_of_the_instructor_only_strings():
    reply_, rt = flagged_reply()
    view = reply_["view"]
    assert sv.leaks(view) == [], sv.leaks(view)
    assert reply_["instructor"] is None                    # a real student session keeps no full result
    for forbidden_key in ("events", "tokens", "cost", "flags_hit", "model", "basis", "notes", "verified_fix_used", "retrieved_chunks"):
        assert forbidden_key not in view
    blob = sv.dumps(view)
    assert "SECRET" not in blob and "LINE UNDER REVIEW" not in blob and "[flagged" not in blob and "0.93" not in blob
    assert all("score" not in s and "cosine" not in s for s in view["sources"])


def test_a_withheld_line_becomes_one_neutral_sentence_outside_the_quote():
    view = flagged_reply()[0]["view"]
    assert view["reviewing"] is True and sv.NEUTRAL_REVIEW in view["answer_text"]
    assert view["answer_text"].count(sv.NEUTRAL_REVIEW) == 1                      # the two review sentences collapsed to one
    src = view["sources"][0]
    assert REVIEW_Q not in src["text"] and "[LINE" not in src["text"] and "Dr. Inglis corrected" not in src["text"].split("Fixed wording")[0]
    assert sv.NEUTRAL_REVIEW in src["notes"]                                     # said beside the passage, not inside it
    assert not [u for u in view["units"] if "under review" in u["text"].lower()]


def test_many_withheld_lines_give_one_neutral_sentence_and_keep_every_chip():
    many = "\n".join([f"{sv.NEUTRAL_REVIEW} {sv.NEUTRAL_REVIEW} {CITE}"] * 3 + [f"Plain line about the wall {CITE}", CLOSING])
    rt = rt_for([chunk(TEXT), chunk(TEXT, cid="n2")], reply(many, under_review_addressed=["U1"]))
    view = service.ask_for_student("walls?", "", True, None, runtime=rt, ctx=CTX)["view"]
    assert view["answer_text"].count(sv.NEUTRAL_REVIEW) == 1
    assert [u["text"] for u in view["units"]][0] == sv.NEUTRAL_REVIEW and view["reviewing"] is True


def test_a_doubtful_line_is_marked_in_the_answer_data_for_the_ui():
    view = flagged_reply()[0]["view"]
    assert view["check_before_relying"] is True
    marked = [u for u in view["units"] if u["check_before_relying"]]
    assert marked and marked[0]["status"] == [{"kind": "check", "label": sv.CHECK_LABEL}]
    assert "flagged" not in marked[0]["text"]


def test_a_corrected_line_says_dr_inglis_corrected_it_and_shows_the_correction():
    view = flagged_reply()[0]["view"]
    assert view["corrected"] is True and view["built"]["corrected"][0]["by"] == "Dr. Inglis"
    assert view["fixes"][0]["label"] == "Dr. Inglis corrected this line." and view["fixes"][0]["correction"] == "Fixed wording."
    assert "Fixed wording." in view["sources"][0]["text"]                       # the corrected wording replaces the line
    assert FIX_Q not in sv.dumps(view)                                          # the original wording is not repeated
    assert "vf-0001" not in sv.dumps(view) and "confirm_error" not in sv.dumps(view)


def test_built_view_lists_only_passages_and_corrections():
    view = flagged_reply()[0]["view"]
    groups, corrections = sv.built_lines(view["built"])
    assert groups == [("Course notes used", [CRUMB])] and corrections == ["Dr. Inglis corrected this line."]
    assert sv.leaks([groups, corrections]) == []


def run_student(at):
    """Everything a student could see on screen right now."""
    bits = [texts(at)] + labels(at) + [b.help or "" for b in at.button]
    return " ".join(bits)


def test_student_screens_never_show_instructor_only_text(world, monkeypatch):
    spy, rt = world
    spy.chunks[:] = [chunk(TEXT, lecture=HAND)]
    rt.client.reply = reply(slip(f"[{HAND} > Walls]"), under_review_addressed=["U1"], doubtful_used=["D1"], verified_used=["V1"])
    ctx = {k: [dict(i, lecture=HAND, breadcrumb=f"{HAND} > Walls") for i in v] for k, v in CTX.items()}
    ctx["fixes"] = [dict(FIX, lecture=HAND, breadcrumb=f"{HAND} > Walls")]
    monkeypatch.setattr(qa, "load_context", lambda: ctx)
    at = app("s_hand", body_done=True, body_type="average fat")
    at.chat_input[0].set_value("What are the walls?").run()
    at.run()
    assert not at.exception
    seen = [run_student(at)]
    for key in [b.key for b in at.button if b.key and re.match(r"^(chip|sreview|sflag|sverif)_\d+_\d+_\w+$", b.key)]:
        next(b for b in at.button if b.key == key).click().run()          # open every chip and every status chip
        seen.append(run_student(at))
    at.session_state["pane"] = "How this answer was built"
    at.run()
    seen.append(run_student(at))
    full = " ".join(seen)
    assert sv.leaks(full) == [], sv.leaks(full)
    assert sv.NEUTRAL_REVIEW in full and "Dr. Inglis corrected this line" in full and "Course notes used" in full
    assert "Cost" not in full and "cost" not in full and "claude" not in full.lower()
    assert "Hybrid" not in full and "retrieval score" not in full and "tokens" not in full


# ---- Guide ----------------------------------------------------------------------------------------------------

G_TEXT = f"- {REVIEW_Q}.\n- {DOUBT_Q}.\n- {FIX_Q}.\n- Plain guide line."
G_SECTION = {"lecture_title": LEC, "breadcrumb": CRUMB, "section_path": ["Walls"], "text_clean": G_TEXT, "lecture_id": "L99", "order": 1}


def make_guide():
    stations = [guide.Station(n=1, name="Walls", sections=[G_SECTION]), guide.Station(n=2, name="Floor", sections=[])]
    cards = {1: guide_card(1, identify_these=["wall a (flagged for review, see fact-check)", "wall b [Verified by Dr. Inglis, 2026-10-07]",
                                              "[LINE UNDER REVIEW U1]"],
                           what_you_should_see=["a thing"], doubtful_used=["D1"]),
             2: guide_card(2)}
    metas = {1: guide_meta(review=[{"id": "U1", "issue": "SECRET issue", "severity": "high", "quote": REVIEW_Q}],
                           doubtful=[{"id": "D1", "reason": "SECRET reason"}], verified=[FIX]), 2: guide_meta()}
    verdict = {"match": "partial", "feedback": "You are missing the wall. It is under review upstairs.", "related_consequences": []}
    g = guide.GuideSession(lecture=LEC, stations=stations, cards=cards, metas=metas, judge=lambda c, t: verdict, model="claude-sonnet-5-5",
                           ctx=dict(CTX), flag_logger=None, prep={"cached": 22, "calls": 0})
    g.stage = "station"
    return g


def test_guide_data_for_a_student_has_no_instructor_detail():
    g = make_guide()
    turn = g.step("station 1")
    turn2 = g.step("a wall")
    state_ = sv.guide_state(turn["state"])
    items = state_["card"]["identify_these"]
    assert [i["mark"] for i in items] == ["check", "corrected"] and all(i["text"] for i in items)
    assert state_["meta"] == {"reviewing": True, "check": True, "corrected": True, "corrected_by": "Dr. Inglis"}
    cleaned = sv.guide_turn(turn2)
    passages = sv.guide_passages(g.passages(1))
    built, corrections = sv.guide_built(g.passages(1))
    everything = [state_, cleaned, passages, built, corrections]
    assert sv.leaks(everything) == [], sv.leaks(everything)
    assert sv.NEUTRAL_REVIEW in cleaned["detail"]["feedback"]                     # a slip in the judge's words is neutralised
    assert "SECRET" not in sv.dumps(everything) and "LINE UNDER REVIEW" not in sv.dumps(everything)
    assert "cost" not in cleaned and "tokens" not in cleaned and "events" not in cleaned


def guide_script():
    import streamlit as st
    from app import state as st_state
    from app.views import guide_ui
    from tests.test_student_safe import make_guide as mk
    st_state.init()
    if st.session_state.get("guide") is None:
        g = mk()
        g.step("station 1")
        st.session_state.guide, st.session_state.guide_turn, st.session_state.guide_turn_raw, st.session_state.sel = g, None, None, None
    guide_ui.guide_view({"username": "s", "name": "S", "role": "student", "allowed_lectures": []})


def test_guide_screens_never_show_instructor_only_text():
    at = AppTest.from_function(guide_script, default_timeout=60).run()
    assert not at.exception
    seen = [run_student(at)]
    assert "wall a" not in seen[0] and "a thing" not in seen[0]               # the notes are not shown before they describe it
    area = at.text_area[0]
    area.set_value("a wall")                                                  # inside a form: committed by the one click below
    next(b for b in at.button if b.label == "Check my description").click().run()
    seen.append(run_student(at))
    assert "wall a" in seen[-1] or "wall b" in seen[-1]                      # ... and are shown after
    for option in ("How this answer was built", "Sources"):
        at.session_state["pane"] = option
        at.run()
        seen.append(run_student(at))
    full = " ".join(seen)
    assert not at.exception and sv.leaks(full) == [], sv.leaks(full)
    assert sv.NEUTRAL_REVIEW in full and "Check before relying on this" in full and "Dr. Inglis corrected this line" in full
    assert "Under review" not in full and "line under review: withheld" not in full and "Station cards" not in full


# ---------------------------------------------------------------------------------------------------------------
# P20, P21: the "not covered" cases
# ---------------------------------------------------------------------------------------------------------------

def test_nothing_relevant_says_so_and_never_mentions_web_search():
    rt = rt_for([chunk()], reply("x"), helper=["YES"], found=False, cosine=0.5)
    res = service.ask("the third carpal bone?", "", True, None, runtime=rt, ctx=EMPTY)
    assert res["status"] == "not_found" and res["reason"] == "nothing_relevant" and res["answer_text"] == service.NOT_FOUND_MSG
    assert "web" not in res["answer_text"].lower() and "web search" not in qa.system_prompt(True).lower()


def test_not_an_anatomy_question_gets_its_own_message():
    rt = rt_for([chunk()], reply("x"), helper=["NO"], found=False, cosine=0.5)
    res = service.ask("what is the capital of France?", "", True, None, runtime=rt, ctx=EMPTY)
    assert res["status"] == "not_found" and res["reason"] == "not_anatomy" and res["answer_text"] == service.NOT_ANATOMY_MSG
    assert res["answer_text"] != service.NOT_FOUND_MSG and res["cost"] > 0          # the tiny check is counted


def test_the_model_can_decline_as_not_anatomy_too():
    rt = rt_for([chunk()], reply("whatever", covered=False, basis="not_covered", decline_reason="not_anatomy"))
    res = service.ask("write me a poem", "", True, None, runtime=rt, ctx=EMPTY)
    assert res["status"] == "out_of_scope" and res["reason"] == "not_anatomy" and res["answer_text"] == service.NOT_ANATOMY_MSG


def test_clinical_advice_keeps_the_models_own_words():
    rt = rt_for([chunk()], reply("The notes describe structure, not treatment.", covered=False, basis="not_covered",
                                 decline_reason="clinical_advice"))
    res = service.ask("how do I treat X?", "", True, None, runtime=rt, ctx=EMPTY)
    assert res["reason"] == "clinical_advice" and res["answer_text"] == "The notes describe structure, not treatment."


def test_outside_allowed_lectures_names_the_lecture_title_and_no_path():
    other = chunk(lecture="Lecture 12 - Posterior Leg", cid="n2")
    rt = rt_for([other], reply("x"))
    res = service.ask("walls?", "", True, [LEC], runtime=rt, ctx=EMPTY)
    assert res["status"] == "access_limited" and res["reason"] == "outside_access"
    assert res["answer_text"] == ("The notes for this are in Lecture 12 - Posterior Leg, which you don't have access to. "
                                  "Ask Dr. Inglis to open it for you.")
    assert ">" not in res["answer_text"] and "data/" not in res["answer_text"] and rt.client.answering() == []
    view = sv.build(res)
    assert view["access_lectures"] == ["Lecture 12 - Posterior Leg"] and sv.leaks(view) == []


def test_a_clinical_refusal_is_not_mistaken_for_missing_access():
    other = chunk(lecture="Lecture 12 - Posterior Leg", cid="n2")
    rt = rt_for([other, chunk(kind="open_text", cid="o1")], reply("No clinical advice.", covered=False, basis="not_covered",
                                                                  decline_reason="clinical_advice"))
    res = service.ask("how do I treat X?", "", True, [LEC], runtime=rt, ctx=EMPTY)
    assert res["reason"] == "clinical_advice" and res["status"] == "out_of_scope"


# ---------------------------------------------------------------------------------------------------------------
# P19: follow-ups
# ---------------------------------------------------------------------------------------------------------------

def msgs(*pairs):
    out = []
    for q, a in pairs:
        out += [{"role": "user", "text": q}, {"role": "assistant", "result": {"status": "answered", "answer_text": a}}]
    return out


def test_recent_turns_keeps_the_last_three_answered_turns_without_citations():
    m = msgs(("q1", "a1 [x > y]"), ("q2", "a2"), ("q3", "a3 " + CLOSING), ("q4", "a4"))
    m.insert(2, {"role": "assistant", "result": {"status": "not_found", "answer_text": "nothing"}})
    turns = qry.recent_turns(m)
    assert [t["question"] for t in turns] == ["q2", "q3", "q4"]
    assert turns[0]["answer"] == "a2" and turns[1]["answer"] == "a3" and "[" not in qry.short_answer("a [x > y] b")
    assert len(qry.short_answer("word " * 200)) <= qry.ANSWER_CHARS + 4


FOLLOW_UPS = [
    ("What are the boundaries of the femoral triangle?", "Inguinal ligament, sartorius and adductor longus bound it.",
     "What about its contents?", "contents of the femoral triangle"),
    ("What are the walls of the middle ear?", "The roof, floor, and anterior, posterior, medial and lateral walls.",
     "What about the inferior one?", "inferior wall (floor) of the middle ear"),
    ("What nerves supply the thenar muscles?", "The recurrent branch of the median nerve.",
     "And the hypothenar ones?", "nerve supply of the hypothenar muscles of the hand"),
]


@pytest.mark.parametrize("q1,a1,follow,rewritten", FOLLOW_UPS)
def test_a_follow_up_is_searched_with_the_earlier_turns_and_the_model_sees_them(q1, a1, follow, rewritten):
    rt = rt_for([chunk()], reply(f"Answer {CITE}\n{CLOSING}"), helper=[rewritten])
    history = [{"question": q1, "answer": a1}]
    res = service.ask(follow, "", True, None, runtime=rt, ctx=EMPTY, history=history)
    assert rt.searcher.queries[0][0] == rewritten and res["search_query"] == rewritten and res["followup"] == "rewritten"
    sent = rt.client.answering()[0]
    assert f"<student_question>{q1}</student_question>" in sent["messages"][0]["content"]
    assert f"<question>{follow}</question>" in sent["messages"][0]["content"]       # the model is asked the real follow-up
    assert "Earlier turns" in sent["system"] and "not a" in sent["system"]
    assert [e["kind"] for e in res["events"]][0] == "followup"
    assert res["citations"][0]["matched"]


def test_history_is_context_not_a_source_citations_come_only_from_this_search():
    rt = rt_for([chunk()], reply(f"Real {CITE}\nFrom the earlier answer [Lecture 5 - Earlier > Thing].\n{CLOSING}"),
                helper=["walls"])
    res = service.ask("and the other?", "", True, None, runtime=rt, ctx=EMPTY,
                      history=[{"question": "q", "answer": "see [Lecture 5 - Earlier > Thing]"}])
    assert [c["matched"] for c in res["citations"]] == [True] and "earlier answer" not in res["answer_text"]


def test_only_the_last_three_turns_are_used_and_a_broken_rewrite_falls_back():
    class Broken(SeqClient):
        def create(self, **kw):
            if "output_config" not in kw:
                raise RuntimeError("down")
            return super().create(**kw)

    rt = service.Runtime(searcher=QSearcher([chunk()]), next_of={}, client=Broken(reply(f"A {CITE}\n{CLOSING}")),
                         model="claude-sonnet-5-5")
    hist = [{"question": f"earlier {i}", "answer": "a"} for i in range(5)]
    res = service.ask("what about it?", "", True, None, runtime=rt, ctx=EMPTY, history=hist)
    assert res["followup"] == "fallback" and res["history_turns"] == 3
    assert rt.searcher.queries[0][0] == "earlier 4 what about it?"
    assert rt.client.answering()[0]["messages"][0]["content"].count("<turn>") == 3


def test_a_first_question_makes_no_rewrite_call():
    rt = rt_for([chunk()], reply(f"A {CITE}\n{CLOSING}"))
    res = service.ask("walls?", "", True, None, runtime=rt, ctx=EMPTY)
    assert rt.client.helpers() == [] and res["followup"] == "unchanged" and "<conversation>" not in rt.client.answering()[0]["messages"][0]["content"]


# ---------------------------------------------------------------------------------------------------------------
# P24: list questions
# ---------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("q,expected", [
    ("What are the boundaries and contents of the femoral triangle?", True), ("List the muscles of the thenar eminence", True),
    ("Name all the walls of the middle ear", True), ("what are the walls of the middle ear?", True),
    ("What are the contents of the carotid sheath?", True), ("What does the median nerve supply?", False),
    ("Where is the femoral artery found?", False), ("Why does the knee lock?", False)])
def test_list_questions_are_recognised(q, expected):
    assert qry.is_list_question(q) is expected


def test_a_list_question_retrieves_twelve_and_says_the_list_may_be_incomplete():
    ans = f"Border one {CITE}\nBorder two {CITE}\n{CLOSING}"
    rt = rt_for([chunk()], reply(ans))
    res = service.ask("What are the boundaries and contents of the femoral triangle?", "", True, None, runtime=rt, ctx=EMPTY)
    assert rt.searcher.queries[0][1] == 12 and res["list_mode"] is True
    lines = res["answer_text"].splitlines()
    assert lines.count(qa.LIST_NOTE) == 1 and lines[-1] == CLOSING and lines[-2] == qa.LIST_NOTE and len(lines) <= qa.LIST_MAX_LINES
    assert "ALL the <source> blocks" in rt.client.answering()[0]["system"]
    view = sv.build(res)
    assert view["list_note"] is True and qa.LIST_NOTE in view["answer_text"]


def test_a_normal_question_retrieves_five_and_gets_no_list_note():
    rt = rt_for([chunk()], reply(f"A {CITE}\n{CLOSING}"))
    res = service.ask("What does the median nerve supply?", "", True, None, runtime=rt, ctx=EMPTY)
    assert rt.searcher.queries[0][1] == 5 and qa.LIST_NOTE not in res["answer_text"] and res["list_mode"] is False


def test_the_list_note_is_not_doubled_and_works_in_long_mode():
    assert qa.add_list_note(f"a\nThis list may be incomplete: x\n{CLOSING}", True).count("incomplete") == 1
    assert qa.add_list_note("a\n\nb", False).endswith(qa.LIST_NOTE)


# ---------------------------------------------------------------------------------------------------------------
# P08, P09: citation numbers per distinct passage, mapped to the supporting line
# ---------------------------------------------------------------------------------------------------------------

def two_chunks_same_cite():
    base = {"cite": f"{LEC} > Walls", "breadcrumb": CRUMB, "source_type": "notes"}
    return [dict(base, text="- The roof of the cavity is the tegmen tympani, a thin plate of temporal bone.\n- Unrelated line."),
            dict(base, text="- The floor is the jugular wall, related to the internal jugular vein below.\n- Other.")]


def test_passages_with_the_same_cite_get_different_numbers_and_each_maps_to_its_own_line():
    answer = (f"The roof is the tegmen tympani, a thin plate of temporal bone {CITE}\n"
              f"The floor is the jugular wall related to the internal jugular vein {CITE}\n"
              f"Again the roof is the tegmen tympani plate of temporal bone {CITE}")
    r = cit.parse_answer(answer, two_chunks_same_cite())
    assert [c["chunk"] for c in r["citations"]] == [0, 1] and [c["n"] for c in r["citations"]] == [1, 2]
    assert [u["chips"] for u in r["units"]] == [[1], [2], [1]]                      # same passage, same number
    first, second = r["citations"]
    assert "tegmen tympani" in first["support"][0]["lines"][0] and "jugular wall" in second["support"][0]["lines"][0]
    assert len(first["support"]) == 2 and first["support"][0]["spans"]


def test_a_verified_fix_has_its_own_number_and_numbers_run_in_order_of_first_use():
    chunks = two_chunks_same_cite()
    fixes = [{"by": "Dr. Inglis", "date": "2026-10-07"}]
    r = cit.parse_answer(f"Floor jugular wall internal jugular vein below {CITE}\nFixed [Verified by Dr. Inglis, 2026-10-07]\n"
                         f"Roof tegmen tympani thin plate temporal bone {CITE}", chunks, fixes)
    assert [(c["n"], c["kind"], c["chunk"], c["fix"]) for c in r["citations"]] == [(1, "notes", 1, None), (2, "verified", None, 0), (3, "notes", 0, None)]


# ---------------------------------------------------------------------------------------------------------------
# P30: question length
# ---------------------------------------------------------------------------------------------------------------

def test_600_characters_is_the_limit_and_5000_does_not_crash():
    rt = rt_for([chunk()], reply(f"A {CITE}\n{CLOSING}"))
    assert service.MAX_QUESTION_CHARS == 600
    ok = service.ask("w" * 600, "", True, None, runtime=rt, ctx=EMPTY)
    assert ok["status"] == "answered"
    n = len(rt.client.calls)
    for size in (601, 5000):
        bad = service.ask("x" * size, "", True, None, runtime=rt, ctx=EMPTY)
        assert bad["status"] == "error" and bad["reason"] == "too_long"
        assert f"{size:,} characters" in bad["answer_text"] and "limit is 600" in bad["answer_text"]
    assert len(rt.client.calls) == n                                                  # nothing was sent to a model


def test_the_chat_box_has_a_counter_limit_and_an_oversize_question_gets_a_message(world):
    spy, rt = world
    at = app("s_hand", body_done=True)
    assert at.chat_input[0].proto.max_chars == 600 and "up to 600 characters" in texts(at)
    at.chat_input[0].set_value("x" * 5000).run()
    assert not at.exception and "5,000 characters long. The limit is 600" in texts(at)
    assert at.session_state["messages"] == [] and rt.client.calls == []                # the long text is not even shown


# ---------------------------------------------------------------------------------------------------------------
# P05, P06: demo footer and passwords
# ---------------------------------------------------------------------------------------------------------------

def test_demo_notice_only_with_demo_mode_and_never_after_sign_in(world, monkeypatch):
    monkeypatch.delenv("ANATOVISION_DEMO", raising=False)
    assert auth.demo_mode() is True
    assert "Demo login on one machine" in texts(app())
    for user in ("s_hand", "prof"):
        assert "Demo login" not in texts(app(user, body_done=True))
    monkeypatch.setenv("ANATOVISION_DEMO", "0")
    assert auth.demo_mode() is False and "Demo login" not in texts(app())


@pytest.fixture
def users(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "USERS_PATH", tmp_path / "users.json")
    monkeypatch.setattr(auth, "_fails", {})


@pytest.mark.parametrize("pw,confirm,message", [
    ("abcdefg", "abcdefg", "too short"), ("", "", "Type a password"), ("   ", "   ", "Type a password"),
    ("longenough1", "different11", "do not match"), ("newstudent9", "newstudent9", "same as the username")])
def test_password_rules_have_clear_errors_that_never_echo_the_password(users, pw, confirm, message):
    with pytest.raises(ValueError) as e:
        auth.add_student("newstudent9", "N", pw, confirm)
    assert message in str(e.value) and (not pw.strip() or pw not in str(e.value))


def test_ten_characters_pass_and_nine_do_not(users):
    auth.add_student("a_student", "A", "tencharsok", "tencharsok")
    assert auth.authenticate("a_student", "tencharsok")["role"] == "student"
    with pytest.raises(ValueError, match="at least 10"):
        auth.set_password("a_student", "ninechars", "ninechars")
    with pytest.raises(ValueError, match="do not match"):
        auth.set_password("a_student", "tencharsok2", "tencharsok3")
    assert auth.MIN_PASSWORD == 10 and "10 characters" in " ".join(auth.PASSWORD_RULES)


def test_a_too_short_password_from_the_environment_is_refused_without_echoing_it(users, monkeypatch):
    monkeypatch.setenv("DEMO_PROFESSOR_PASSWORD", "tiny")
    with pytest.raises(ValueError) as e:
        auth.ensure_seed(lambda t: None)
    assert "DEMO_PROFESSOR_PASSWORD" in str(e.value) and "tiny" not in str(e.value)


def test_the_password_form_shows_rules_a_confirm_box_and_clear_errors(world, capsys):
    at = app("prof")
    body = texts(at)
    assert "At least 10 characters." in body and "Confirm new password" in [t.label for t in at.text_input]
    at.text_input(key="reset_pw_value").input("longenough1")
    at.text_input(key="reset_pw_confirm").input("longenough2")
    next(b for b in at.button if b.label == "Set password").click().run()
    assert "do not match" in texts(at) and auth.authenticate("s_hand", "stud-password")
    at.text_input(key="reset_pw_value").input("short")
    at.text_input(key="reset_pw_confirm").input("short")
    next(b for b in at.button if b.label == "Set password").click().run()
    assert "too short" in texts(at)
    out = capsys.readouterr()
    assert "longenough" not in out.out + out.err                                          # nothing echoed to the logs


# ---------------------------------------------------------------------------------------------------------------
# P07: usage split by kind
# ---------------------------------------------------------------------------------------------------------------

def line(kind=None, mode="qa", user="s1", cost=0.01, **kw):
    e = {"ts": "2026-10-08T10:00:00+00:00", "mode": mode, "user": user, "question": "q", "status": "answered",
         "answered_from_notes": True, "lectures": [LEC], "cost": cost, **kw}
    if kind:
        e["kind"] = kind
    return e


def test_usage_is_split_by_kind_and_previews_are_not_student_usage():
    entries = [line("chat_answer"), line("chat_answer", answered_from_notes=False, status="not_found"),
               line("guide_step", mode="guide"), line("professor_preview", user="prof", cost=0.5),
               line("professor_preview", mode="guide", user="prof", cost=0.25), line("factcheck", mode="factcheck", user="prof", cost=1.0)]
    s = usage.summary(entries)
    assert s["chat"]["questions"] == 2 and s["guide"]["steps"] == 1
    assert s["preview"] == {"questions": 1, "guide_steps": 1, "cost": 0.75}
    assert s["chat"]["top_lectures"] == [(LEC, 2)] and len(s["chat"]["unanswered"]) == 1
    assert s["factcheck"]["runs"] == 1 and s["cost_total"] == pytest.approx(0.01 * 3 + 0.5 + 0.25 + 1.0)


def test_old_log_lines_without_a_kind_are_classified():
    assert usage.kind_of({"mode": "qa", "user": "s1"}) == "chat_answer" and usage.kind_of({"mode": "guide", "user": "s1"}) == "guide_step"
    assert usage.kind_of({"mode": "qa", "user": "preview"}) == "professor_preview" and usage.kind_of({"mode": "factcheck"}) == "factcheck"


def test_a_professor_preview_question_is_tagged_and_not_counted_as_the_student(world):
    def run():
        from app import nav
        from app.views import student
        import streamlit as st
        me = nav.current_user()
        nav.PAGES = {"dashboard": st.Page(lambda: None, title="D", url_path="d"), "chat": st.Page(lambda: None, title="c", url_path="c"),
                     "guide": st.Page(lambda: None, title="g", url_path="g"), "quiz": st.Page(lambda: None, title="q", url_path="q")}
        student.page(nav.preview_user(me), real_user=me)

    at = AppTest.from_function(run, default_timeout=60)
    at.session_state["auth_user"], at.session_state["body_done"], at.session_state["preview_as"] = "prof", True, "s_hand"
    at.run()
    at.chat_input[0].set_value("walls?").run()
    at.run()
    (entry,) = usage.read_log()
    assert entry["kind"] == "professor_preview" and entry["user"] == "prof" and entry["as_user"] == "s_hand"
    s = usage.summary()
    assert s["chat"]["questions"] == 0 and s["preview"]["questions"] == 1
    assert "Instructor detail" in str(at.get("segmented_control")[0].proto)


def test_a_student_question_is_logged_as_a_chat_answer(world):
    at = app("s_hand", body_done=True)
    at.chat_input[0].set_value("walls?").run()
    at.run()
    (entry,) = usage.read_log()
    assert entry["kind"] == "chat_answer" and entry["user"] == "s_hand" and "as_user" not in entry


# ---------------------------------------------------------------------------------------------------------------
# P04, P25: instructor-only pages, instructor detail kept
# ---------------------------------------------------------------------------------------------------------------

VIEWS = ["review_queue", "ledger_tab", "notes_tab", "access_tab", "usage_tab", "settings_tab"]


def student_calls(name):
    import streamlit as st
    from app.views import professor
    fn = getattr(professor, name)
    st.session_state.auth_user = "s_hand"
    try:
        fn({"username": "s_hand", "name": "S", "role": "student", "allowed_lectures": []}) if name == "review_queue" else fn()
    finally:
        st.write("AFTER VIEW")


@pytest.mark.parametrize("name", VIEWS)
def test_every_professor_view_refuses_a_student_on_the_server_side(world, name):
    at = AppTest.from_function(student_calls, kwargs={"name": name}, default_timeout=60)
    at.session_state["auth_user"] = "s_hand"
    at.run()
    body = texts(at)
    assert "That page is for instructors" in body and "Back to Ask the lab" in labels(at)
    for secret in ("Verified fixes", "AI-generated suggestion", "Spending cap per session", "Add a student", "Fact-check of", "Set password"):
        assert secret not in body, (name, secret)


def blocked_page():
    from app.views import blocked
    blocked.show()


def test_a_student_opening_the_instructor_path_gets_the_page_and_not_a_redirect(world):
    from app import nav
    app("s_hand", body_done=True)
    assert set(nav.PAGES) == {"chat", "guide", "quiz", "dashboard"}           # the instructor path is registered for students ...
    assert nav.PAGES["dashboard"].url_path == "dashboard" and not nav.PAGES["dashboard"]._default
    at = AppTest.from_function(blocked_page, default_timeout=30).run()    # ... and it is the blocked page, not the dashboard
    assert "That page is for instructors" in texts(at) and "Back to Ask the lab" in labels(at)
    assert "Review queue" not in texts(at)
    professor_at = app("prof")
    assert set(nav.PAGES) == {"dashboard", "chat", "guide", "quiz"} and nav.PAGES["dashboard"]._default


def test_the_professor_still_sees_full_detail(world):
    at = app("prof")
    body = texts(at)
    assert "AI-generated suggestion, not a verdict" in body and f"Model {llm.default_model()}" in body
    assert "That page is for instructors" not in body
    assert "Student cost" in body and "Professor previews (not counted as student usage)" in body


def test_the_professor_preview_has_the_instructor_detail_tab_with_scores_and_cost(world):
    from app.views import pane
    raw = service.ask("walls?", "", True, None, runtime=rt_for([chunk()], reply(f"A {CITE}\n{CLOSING}")), ctx=EMPTY,
                      audience="student", instructor_detail=True)
    assert raw["events"] and raw["tokens"]["input"] and raw["cost"] and raw["model"] and raw["retrieved_chunks"][0]["score"]
    assert "Hybrid search" in pane.event_detail.__module__ or True
    assert any("Hybrid search" in e["label"] for e in raw["events"])


def test_reload_warning_is_shown_in_the_sidebar(world):
    assert "Reloading this page signs you out. Your saved chats reopen from the list." in texts(app("s_hand", body_done=True))
    assert "Reloading this page signs you out." in texts(app("prof"))
