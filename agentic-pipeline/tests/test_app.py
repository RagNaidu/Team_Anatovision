"""Headless smoke tests of the Streamlit app (AppTest): login, roles, access enforcement, student chat, guide, dashboard.
The model and the search are faked: no API calls, no cost."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app import data as app_data
from app.views import guide_ui, student
from src import auth, service, usage, verified
from src.modes import qa
from tests.test_service import CLOSING, FakeClient, FakeSearcher, chunk, reply

MAIN = Path(__file__).resolve().parents[1] / "app" / "main.py"
HAND = "Lecture 09 - The Hand"
ANSWER = f"The walls are six. [{HAND} > Walls]\n{CLOSING}"


class Spy(FakeSearcher):
    """Records which lectures every search was allowed to use."""

    def __init__(self, chunks):
        super().__init__(chunks)
        self.allowed_seen = []

    def search(self, question, k=5, allowed_lectures=None):
        self.allowed_seen.append(None if allowed_lectures is None else sorted(allowed_lectures))
        return super().search(question, k, allowed_lectures)


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "USERS_PATH", tmp_path / "users.json")
    monkeypatch.setattr(auth, "_fails", {})
    auth.save_users({"prof": auth.new_record("Dr. Inglis", "professor", "prof-password"),
                     "s_hand": auth.new_record("Hand Student", "student", "stud-password", [HAND]),
                     "s_none": auth.new_record("No Access", "student", "stud-password")})
    monkeypatch.setattr(usage, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(usage, "QUESTION_LOG_PATH", tmp_path / "q.jsonl")
    for mod in (qa, verified):
        monkeypatch.setattr(mod, "FLAGS_PATH", tmp_path / "flags.jsonl")
    monkeypatch.setattr(verified, "FIXES_PATH", tmp_path / "fixes.jsonl")
    spy = Spy([chunk(lecture=HAND), chunk(lecture="Lecture 12 - Other", cid="n2")])
    rt = service.Runtime(searcher=spy, next_of={}, client=FakeClient(reply(ANSWER)), model="claude-sonnet-5-5")
    for mod in (student, guide_ui, app_data):
        monkeypatch.setattr(mod, "get_runtime", lambda rt=rt: rt)
    monkeypatch.setattr(qa, "load_context", lambda: {"confirmed": [], "doubtful": [], "fixes": []})
    return spy, rt


def app(user=None, **state):
    at = AppTest.from_file(str(MAIN), default_timeout=60)
    if user:
        at.session_state["auth_user"] = user
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def texts(at):
    """Everything markdown shows, without the page's own <style> and <script> blocks."""
    return " ".join(m.value for m in at.markdown if not m.value.lstrip().startswith(("<style", "<script")))


def labels(at):
    return [b.label for b in at.button]


def test_no_login_shows_only_the_sign_in_form(world):
    at = app()
    assert not at.exception and "Sign in" in labels(at)
    assert at.text_input(key="login_user") and "Review queue" not in texts(at) and "Ask about the lab" not in texts(at)


def test_wrong_password_is_refused_and_the_right_one_signs_in(world):
    at = app()
    at.text_input(key="login_user").input("s_hand")
    at.text_input(key="login_pass").input("nope-nope")
    next(b for b in at.button if b.label == "Sign in").click().run()
    import html
    from app.views import login
    assert html.escape(login.BAD_LOGIN) in texts(at) and "auth_user" not in at.session_state
    at.text_input(key="login_pass").input("stud-password")
    next(b for b in at.button if b.label == "Sign in").click().run()
    assert at.session_state["auth_user"] == "s_hand" and not at.exception


def test_student_sees_the_chat_and_never_the_dashboard(world):
    at = app("s_hand", body_done=True)
    assert not at.exception
    assert "Review queue" not in texts(at) and "Verified fixes" not in texts(at)
    assert [t.label for t in at.tabs] == []
    links = {l.proto.label: l.proto for l in at.get("page_link")}
    assert not links["Quiz"].disabled and not links["Guide"].disabled and not links["Q&A"].disabled     # Quiz is on


def test_the_dashboard_page_refuses_a_student_even_if_called_directly(world):
    from app.views import professor

    def run():
        import streamlit as st
        from app.views import professor
        professor.page({"username": "s", "name": "S", "role": "student", "allowed_lectures": []})
        st.write("REACHED THE DASHBOARD")

    at = AppTest.from_function(run, default_timeout=30).run()
    assert "That page is for instructors" in texts(at) and "Back to Ask the lab" in labels(at)
    assert "REACHED THE DASHBOARD" not in texts(at) and "Review queue" not in texts(at)


def test_student_question_is_limited_to_the_students_lectures(world):
    spy, rt = world
    at = app("s_hand", body_done=True, body_type="average fat")
    at.chat_input[0].set_value("What are the walls?").run()
    at.run()
    assert spy.allowed_seen[0] == [HAND]
    assert not at.exception and "The walls are six." in texts(at)
    assert any(b.key and b.key.startswith("chip_") for b in at.button)           # a numbered citation chip


def test_student_with_no_grants_searches_openstax_only(world):
    spy, rt = world
    at = app("s_none", body_done=True)
    at.chat_input[0].set_value("anything about the wall").run()
    at.run()
    assert spy.allowed_seen[0] == []
    assert "No lectures or dissection guides have been shared with you yet" in texts(at)


def test_grants_are_read_fresh_so_a_revoked_lecture_stops_working(world):
    spy, rt = world
    at = app("s_hand", body_done=True)
    auth.set_allowed_lectures("s_hand", [])
    at.chat_input[0].set_value("walls?").run()
    at.run()
    assert spy.allowed_seen[0] == []


def test_sidebar_scope_cannot_widen_access(world):
    spy, rt = world
    at = app("s_hand", body_done=True, scope=["Lecture 12 - Posterior Leg and Plantar Surface of Foot", HAND])
    at.chat_input[0].set_value("walls?").run()
    at.run()
    assert spy.allowed_seen[0] == [HAND]


def test_spending_cap_stops_the_model_and_says_so(world):
    spy, rt = world
    usage.save_settings(spending_cap_usd=0.0)
    at = app("s_hand", body_done=True)
    at.chat_input[0].set_value("walls?").run()
    at.run()
    assert rt.client.calls == [] and "spending cap" in texts(at).lower() and not at.exception


def test_the_cost_in_the_sidebar_grows_after_an_answer(world):
    at = app("s_hand", body_done=True)
    at.chat_input[0].set_value("walls?").run()
    at.run()
    assert at.session_state["cost"] == pytest.approx(0.003)            # still counted for the spending cap ...
    assert "$" not in texts(at) and "spending cap" not in texts(at).lower()      # ... but a student is never shown money


def test_the_professor_gets_the_dashboard_tabs(world):
    at = app("prof")
    assert not at.exception
    assert [t.label for t in at.tabs][:3] == ["Review queue", "Verified fixes", "Access"] or "Review queue" in [t.label for t in at.tabs]
    assert "AI-generated suggestion, not a verdict" in texts(at)


def test_the_professor_previewing_a_student_gets_that_students_lectures(world):
    spy, rt = world

    def run():
        from app import nav
        from app.views import student
        import streamlit as st
        me = nav.current_user()
        nav.PAGES = {"dashboard": st.Page(lambda: None, title="Dashboard", url_path="d"), "chat": st.Page(lambda: None, title="c", url_path="c"),
                     "guide": st.Page(lambda: None, title="g", url_path="g"), "quiz": st.Page(lambda: None, title="q", url_path="q")}
        student.page(nav.preview_user(me), real_user=me)

    at = AppTest.from_function(run, default_timeout=60)
    at.session_state["auth_user"], at.session_state["body_done"], at.session_state["preview_as"] = "prof", True, "s_hand"
    at.run()
    assert "You are seeing exactly what" in texts(at) and "Hand Student" in texts(at)
    at.chat_input[0].set_value("walls?").run()
    at.run()
    assert spy.allowed_seen[0] == [HAND]


def test_a_removed_account_is_signed_out(world):
    at = app("s_hand", body_done=True)
    users = auth.load_users()
    users.pop("s_hand")
    auth.save_users(users)
    at.run()
    assert "auth_user" not in at.session_state and at.text_input(key="login_user")


def test_body_type_is_asked_once_at_the_start_without_blocking_anything(world):
    at = app("s_hand")
    body = texts(at)
    assert "Which cadaver are you working on?" in body and "Ask about the lab." in body       # asked, but the chat is right there
    assert {"What are the walls of the middle ear?", "What are the boundaries and contents of the femoral triangle?"} <= set(labels(at))
    assert {"Continue", "Skip for now"} <= set(labels(at))
    kinds = {b.label: b.proto.type for b in at.button if b.label in ("Continue", "Skip for now")}
    assert kinds["Continue"] == kinds["Skip for now"] == "primary"                           # equally prominent
    next(b for b in at.button if b.label == "Skip for now").click().run()
    assert "Which cadaver are you working on?" not in texts(at) and at.session_state["body_done"] is True and at.session_state["body_type"] == ""


def test_asking_without_answering_the_body_type_counts_as_skipping_it(world):
    at = app("s_hand")
    at.chat_input[0].set_value("walls?").run()
    at.run()
    assert at.session_state["body_done"] is True and "Which cadaver are you working on?" not in texts(at)


def test_a_student_asking_outside_their_lectures_gets_the_access_message_and_no_model_call(world):
    spy, rt = world
    at = app("s_none", body_done=True)
    at.chat_input[0].set_value("What are the walls?").run()
    at.run()
    import html
    assert html.escape(service.access_message([HAND, "Lecture 12 - Other"])) in texts(at) and rt.client.calls == []
    assert "Lecture 09 - The Hand" in texts(at) and "Ask Dr. Inglis to open it for you." in texts(at)
    assert "The walls are six." not in texts(at)
    chunks_shown = [m for m in at.session_state["messages"] if m["role"] == "assistant"][0]["result"]["sources"]
    assert chunks_shown == []


def test_the_guide_picker_lists_only_granted_lectures(world, monkeypatch):
    from app import nav
    at = app("s_hand", body_done=True)
    at._page_hash = nav.PAGES["guide"]._script_hash          # open the /guide page
    at.run()
    at.radio(key="guide_source").set_value("Lecture notes (sample)").run()        # the lecture-notes walk-through is the second option
    sel = at.selectbox(key="guide_lecture")
    assert sel.options == [HAND] or sel.options == [] or HAND in sel.options
    assert all(o == HAND for o in sel.options)


# ---- professor dashboard tabs ------------------------------------------------------------------------------

def test_dashboard_tabs_are_all_there_and_render(world, monkeypatch, tmp_path):
    from src import notes_upload
    monkeypatch.setattr(notes_upload, "UPLOAD_DIR", tmp_path / "up")
    at = app("prof")
    assert not at.exception
    assert {"Review queue", "Verified fixes", "Notes library", "Access", "Usage", "Settings"} <= {t.label for t in at.tabs}
    body = texts(at)
    assert "26 lectures" in body and "never edited or overwritten" in body and "Last fact-check" in body


def test_settings_save_changes_the_spending_cap_the_students_get(world):
    at = app("prof")
    next(n for n in at.number_input if n.label.startswith("Spending cap")).set_value(0.5)
    next(b for b in at.button if b.label == "Save settings").click().run()
    assert usage.load_settings()["spending_cap_usd"] == 0.5
    student_at = app("s_hand", body_done=True)
    assert "$" not in texts(student_at)                                  # the student is not shown the cap
    assert student_at.session_state["cost"] == 0 and usage.load_settings()["spending_cap_usd"] == 0.5


def test_usage_tab_counts_questions_and_lists_the_unanswered_ones(world):
    usage.log_event({"mode": "qa", "user": "s_hand", "question": "Q answered", "status": "answered", "answered_from_notes": True,
                     "lectures": [HAND], "cost": 0.01})
    usage.log_event({"mode": "qa", "user": "s_hand", "question": "Q gap", "status": "not_found", "answered_from_notes": False,
                     "lectures": [], "cost": 0.0})
    at = app("prof")
    body = texts(at)
    assert ">2<" in body and "$0.0100" in body
    gap = [df.value for df in at.dataframe]
    assert any("Q gap" in str(d.to_dict()) for d in gap) and not any("Q answered" in str(d.to_dict()) for d in gap if "Question" in d)
