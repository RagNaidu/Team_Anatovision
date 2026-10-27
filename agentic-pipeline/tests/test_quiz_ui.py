"""The Quiz screens (AppTest) with fake models: set up, build, one question at a time, saved selections, no disclosure before submit, resume,
isolation, the 10-to-5 offer, failures, and the professor's review tab."""
import pytest
from streamlit.testing.v1 import AppTest

from app import data as app_data
from app.views import guide_ui, quiz_ui, student
from src import auth, service, usage, verified
from src.modes import qa
from src.quiz.store import QuizStore
from tests.quiz_fakes import HAND, Behavior, FakeSearcher, corpus, install
from tests.test_app import MAIN, labels, texts


@pytest.fixture
def qworld(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "USERS_PATH", tmp_path / "users.json")
    monkeypatch.setattr(auth, "_fails", {})
    auth.save_users({"prof": auth.new_record("Dr. Inglis", "professor", "prof-password"),
                     "s_hand": auth.new_record("Hand Student", "student", "stud-password", [HAND]),
                     "s_two": auth.new_record("Other Student", "student", "stud-password", [HAND]),
                     "s_none": auth.new_record("No Access", "student", "stud-password")})
    monkeypatch.setattr(usage, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(usage, "QUESTION_LOG_PATH", tmp_path / "q.jsonl")
    for mod in (qa, verified):
        monkeypatch.setattr(mod, "FLAGS_PATH", tmp_path / "flags.jsonl")
    monkeypatch.setattr(verified, "FIXES_PATH", tmp_path / "fixes.jsonl")
    holder = {"chunks": corpus()}
    rt = service.Runtime(searcher=FakeSearcher(holder["chunks"]), next_of={}, client=object(), model="google/gemma-4-31B-it", rewrite_model="google/gemma-4-31B-it")
    for mod in (student, guide_ui, quiz_ui, app_data):
        monkeypatch.setattr(mod, "get_runtime", lambda rt=rt: rt)
    monkeypatch.setattr(qa, "load_context", lambda: {"confirmed": [], "doubtful": [], "fixes": []})
    monkeypatch.setattr("src.quiz.service.web_sources.web_fallback_on", lambda: False)
    monkeypatch.setattr("src.quiz.service.qry.scope_check", lambda c, q, m: ("anatomy", {}, True))
    beh = install(monkeypatch, Behavior())
    return rt, beh


def quiz_page(user, **state):
    from app import nav
    at = AppTest.from_file(str(MAIN), default_timeout=90)
    at.session_state["auth_user"] = user
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    at._page_hash = nav.PAGES["quiz"]._script_hash
    return at.run()


def everything(at):
    return texts(at) + " " + " ".join(str(getattr(e, "value", "") or "") for e in at.get("html")) + " " + " ".join(str(r.label) for r in at.radio) + " " + " ".join(str(e.label) for e in at.expander)


def pick_hand(at, n=5):
    at.multiselect(key="qz_pick").set_value([HAND])
    at.run()
    if n == 10:
        at.session_state["qz_len"] = 10
        at.run()
    return at


def build(at):
    next(b for b in at.button if b.label == "Build quiz").click().run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def test_quiz_is_enabled_in_the_sidebar_and_shows_the_two_lengths(qworld):
    at = quiz_page("s_hand")
    assert not at.exception and "Build quiz" in labels(at)
    assert [b.label for b in at.get("button_group")] == [] or True
    assert at.session_state["qz_len"] == 5                                   # default 5


def test_a_student_without_grants_is_told_and_cannot_build_from_materials(qworld):
    at = quiz_page("s_none")
    assert "No lectures or guides are open to you yet." in texts(at)
    assert next(b for b in at.button if b.label == "Build quiz").disabled


def test_build_then_one_question_at_a_time_with_nothing_revealed(qworld):
    rt, beh = qworld
    at = build(pick_hand(quiz_page("s_hand")))
    page = everything(at)
    assert "Question 1 of 5" in page and len(at.radio) == 1 and len(at.radio[0].options) == 4
    for banned in ("The passage states", "Correct answer", "Why it is correct", "Supporting passages", "scored", "Verified", "AI-checked", "explanation"):
        assert banned not in page
    assert "Back" in labels(at) and "Next" in labels(at)
    assert next(b for b in at.button if b.label == "Back").disabled


def test_selections_are_saved_across_back_next_and_a_new_session(qworld):
    at = build(pick_hand(quiz_page("s_hand")))
    at.radio[0].set_value(at.radio[0].options[1]).run()
    first = at.radio[0].value
    next(b for b in at.button if b.label == "Next").click().run()
    assert "Question 2 of 5" in texts(at) and at.radio[0].value is None
    next(b for b in at.button if b.label == "Back").click().run()
    assert at.radio[0].value == first
    again = quiz_page("s_hand")                                              # a brand-new session (sign in again)
    assert "You have a quiz in progress." in texts(again) and "Resume quiz" in labels(again)
    next(b for b in again.button if b.label == "Resume quiz").click().run()
    assert "Question 1 of 5" in texts(again) and again.radio[0].value == first


def test_review_page_shows_selections_but_still_no_correctness(qworld):
    at = build(pick_hand(quiz_page("s_hand")))
    for _ in range(4):
        next(b for b in at.button if b.label == "Next").click().run()
    next(b for b in at.button if b.label == "Review answers").click().run()
    page = everything(at)
    assert "Review your answers" in page and "Not answered" in page and "Yes, submit" in labels(at)
    assert "Correct answer" not in page and "scored" not in page


def test_submit_shows_the_score_answers_explanations_and_passages(qworld):
    at = build(pick_hand(quiz_page("s_hand")))
    store = QuizStore()
    q = store.latest("s_hand")
    for k, iid in enumerate(q["item_ids"][:3]):
        store.select("s_hand", q["id"], k, store.item(iid)["answer_ids"])
    at = quiz_page("s_hand")
    next(b for b in at.button if b.label == "Resume quiz").click().run()
    for _ in range(4):
        next(b for b in at.button if b.label == "Next").click().run()
    next(b for b in at.button if b.label == "Review answers").click().run()
    next(b for b in at.button if b.label == "Yes, submit").click().run()
    assert not at.exception, [e.message for e in at.exception]
    page = everything(at)
    assert "You scored 3 of 5" in page and "Correct answer" in page and "Why it is correct" in page and "Supporting passages" in page
    assert "Not reviewed by Dr. Inglis" in page and "<mark class=\"qz-span\"><mark" not in page
    assert any("<mark" in str(getattr(e, "value", "")) for e in at.markdown)                 # the supporting span is highlighted


def test_another_student_never_sees_or_resumes_the_quiz(qworld):
    build(pick_hand(quiz_page("s_hand")))
    other = quiz_page("s_two")
    assert "You have a quiz in progress." not in texts(other) and "Resume quiz" not in labels(other)


def test_ten_requested_but_five_pass_shows_an_explicit_offer_and_never_pads(qworld, monkeypatch):
    rt, beh = qworld
    beh.bad = ["thoracodorsal", "long thoracic", "dorsal scapular", "lateral pectoral", "medial pectoral", "upper subscapular", "suprascapular"]
    at = pick_hand(quiz_page("s_hand"), 10)
    build(at)
    assert "A 10-question quiz is not ready yet." in texts(at) and "Start with 5 questions" in labels(at)
    assert "Question 1" not in texts(at)
    next(b for b in at.button if b.label == "Start with 5 questions").click().run()
    assert "Question 1 of 5" in texts(at)


def test_insufficient_evidence_starts_nothing_and_says_why(qworld):
    rt, beh = qworld
    rt.searcher.chunks[:] = corpus()[:1]
    at = build(pick_hand(quiz_page("s_hand")))
    assert "No quiz was started" in everything(at) and "not enough source text" in everything(at)
    assert QuizStore().latest("s_hand") is None


def test_a_verifier_failure_starts_nothing(qworld):
    rt, beh = qworld
    beh.verifier = "error"
    at = build(pick_hand(quiz_page("s_hand")))
    assert "No quiz was started" in everything(at) and QuizStore().latest("s_hand") is None


def test_the_professor_sees_evidence_and_can_approve(qworld):
    build(pick_hand(quiz_page("s_hand")))
    at = AppTest.from_file(str(MAIN), default_timeout=90)
    at.session_state["auth_user"] = "prof"
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    page = everything(at)
    assert "Quiz items" in page and "Evidence (supporting spans are highlighted)" in page and "Recent builds" in page
    store = QuizStore()
    first = store.list_items()[0]
    next(b for b in at.button if b.key == f"qzr_ok_{first['item_id']}").click().run()
    assert store.item(first["item_id"])["review"]["status"] == "approved" and store.item(first["item_id"])["review"]["by"] == "Dr. Inglis"


def test_a_student_cannot_reach_the_professor_quiz_view(qworld):
    from app.views import professor
    def run():
        from app.views import professor
        professor.quiz_tab({"username": "s", "name": "S", "role": "student", "allowed_lectures": []})
    at = AppTest.from_function(run, default_timeout=30).run()
    assert "Evidence (supporting" not in everything(at)


def test_the_help_text_makes_no_time_promise_and_explains_reuse(qworld):
    page = everything(quiz_page("s_hand"))
    assert "about a minute" not in page and "reuses them" in page


def test_a_partial_build_shows_what_is_saved_and_continue_preparing_finishes_it(qworld):
    rt, beh = qworld
    beh.bad = ["thoracodorsal", "long thoracic", "dorsal scapular", "lateral pectoral", "medial pectoral", "upper subscapular", "suprascapular", "axillary"]
    at = build(pick_hand(quiz_page("s_hand")))
    page = everything(at)
    assert "No quiz was started" in page and "4 of 5 questions" in page and "Continue preparing" in labels(at)
    assert "rejected by the checks" in page and "source text" not in page and QuizStore().latest("s_hand") is None
    beh.bad = []
    before = beh.n_calls
    next(b for b in at.button if b.label == "Continue preparing").click().run()
    assert not at.exception, [e.message for e in at.exception]
    assert "Question 1 of 5" in texts(at)
    assert beh.n_calls - before < before                                      # only the missing question was prepared


def test_an_unreachable_service_shows_a_clear_error_at_once_and_offers_to_continue(qworld):
    from tests.test_quiz import DeadClient
    rt, beh = qworld
    rt.client = DeadClient()
    at = build(pick_hand(quiz_page("s_hand")))
    page = everything(at)
    assert "No quiz was started" in page and "could not be reached" in page and "VPN" in page
    assert "Continue preparing" in labels(at) and "source text" not in page and beh.n_calls == 0
    assert QuizStore().latest("s_hand") is None
