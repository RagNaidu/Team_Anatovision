"""The Guide screen as a conversation (AppTest). The model is a scripted client: no network, no cost; saved sessions go to a temp file."""
import json
from types import SimpleNamespace

import pytest

from src import auth, guide_store, llm
from tests.test_app import app, labels, texts, world  # noqa: F401  (fixture)


class RoleClient:
    """Answers the interpreter and the writer by looking at the system prompt. `fail` makes every call fail."""
    def __init__(self):
        self.intent = {"intent": "other", "step_ids": [], "slide": None, "claims_done": False, "missing_ids": []}
        self.fail, self.calls = False, []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise ConnectionError("down")
        if kw["system"].startswith("You read ONE message"):
            out = self.intent
        else:
            out = {"text": "Here is the step from the guide.", "cites": [], "match": "na", "expects": "ready"}
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(out))],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))


@pytest.fixture
def client(world):
    spy, rt = world
    rt.client = RoleClient()
    return rt.client


def guide_page(user, **state):
    from app import nav
    at = app(user, body_done=True, **state)
    at._page_hash = nav.PAGES["guide"]._script_hash
    return at.run()


def md(at):
    return texts(at)


def everything(at):
    """Markdown plus the html elements (alerts are html)."""
    return texts(at) + " " + " ".join(getattr(e, "value", "") or str(getattr(e, "proto", "")) for e in at.get("html"))


def open_first(at, option=None):
    if option:
        at.selectbox(key="guide_pick").set_value(option)
    next(b for b in at.button if b.label == "Open guide").click().run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def test_a_student_with_no_grants_sees_a_compact_access_explanation_and_nothing_to_open(world, client):
    at = guide_page("s_none")
    assert not at.exception
    assert "No dissection guides are open to you yet." in md(at) and "Open guide" not in labels(at)
    assert not at.chat_input


def test_a_student_with_only_a_guide_grant_can_open_and_start_that_guide(world, client):
    auth.set_allowed_lectures("s_none", ["Dissection Guide, Class 26"])            # no lecture at all
    at = guide_page("s_none")
    assert at.selectbox(key="guide_pick").options == ["Class 26: The Mediastinum and Heart"]
    open_first(at)
    assert "Are you starting from the beginning, or where are you now?" in md(at)
    assert "Start from the beginning" in labels(at) and at.chat_input
    next(b for b in at.button if b.label == "Start from the beginning").click().run()
    assert not at.exception, [e.message for e in at.exception]
    assert "Here is the step from the guide." in md(at) and "Slide " in md(at) and "step 1 of" in md(at)


def test_an_unmatched_guide_can_be_opened_when_granted(world, client):
    auth.set_allowed_lectures("s_none", ["Dissection Guide, Class 25"])
    at = open_first(guide_page("s_none"))
    assert "Class 25" in md(at)


def test_typing_a_slide_number_moves_the_position_and_it_is_saved_for_this_user_only(world, client, tmp_path):
    auth.set_allowed_lectures("s_none", ["Dissection Guide, Class 26"])
    at = open_first(guide_page("s_none"))
    at.chat_input[0].set_value("I'm at slide 5").run()
    assert not at.exception, [e.message for e in at.exception]
    assert "Slide 5" in md(at)
    store = guide_store.GuideStore()
    saved = [store.load("s_none", f) for f in store.guides_of("s_none")]
    assert len(saved) == 1 and saved[0]["pos"].startswith("s5") and saved[0]["messages"][0]["text"] == "I'm at slide 5"
    assert store.guides_of("s_hand") == []


def test_changing_guide_restores_each_guides_own_session(world, client):
    auth.set_allowed_lectures("s_none", ["Dissection Guide, Class 26", "Dissection Guide, Class 25"])
    at = guide_page("s_none")
    opts = at.selectbox(key="guide_pick").options
    open_first(at, opts[0])
    at.chat_input[0].set_value("slide 5").run()
    first_name = at.session_state["gsess"].entry["display_name"]
    next(b for b in at.button if b.label == "Change guide").click().run()
    at.selectbox(key="guide_pick").set_value(next(o for o in at.selectbox(key="guide_pick").options if first_name not in o))
    next(b for b in at.button if b.label == "Open guide").click().run()
    assert "Are you starting from the beginning" in md(at) and at.session_state["gsess"].state["pos"] is None
    assert at.session_state["gsess"].state["messages"] == []
    next(b for b in at.button if b.label == "Change guide").click().run()
    assert any("in progress" in o for o in at.selectbox(key="guide_pick").options)
    at.selectbox(key="guide_pick").set_value(next(o for o in at.selectbox(key="guide_pick").options if first_name in o))
    next(b for b in at.button if b.label == "Open guide").click().run()
    assert at.session_state["gsess"].state["pos"].startswith("s5")


def test_a_failed_turn_shows_a_retry_and_keeps_the_position(world, client):
    auth.set_allowed_lectures("s_none", ["Dissection Guide, Class 26"])
    at = open_first(guide_page("s_none"))
    at.chat_input[0].set_value("slide 5").run()
    pos = at.session_state["gsess"].state["pos"]
    client.fail = True
    at.chat_input[0].set_value("what is this structure?").run()
    assert not at.exception
    assert "That didn" in everything(at) and "Try again" in labels(at)
    assert at.session_state["gsess"].state["pos"] == pos
    client.fail = False
    next(b for b in at.button if b.label == "Try again").click().run()
    assert "Try again" not in labels(at)


def test_start_over_clears_only_this_guide_after_a_confirmation(world, client):
    auth.set_allowed_lectures("s_none", ["Dissection Guide, Class 26"])
    at = open_first(guide_page("s_none"))
    at.chat_input[0].set_value("slide 5").run()
    assert "Yes, start over" in labels(at)                                       # inside the popover: an explicit second step
    next(b for b in at.button if b.label == "Yes, start over").click().run()
    assert at.session_state["gsess"].state["pos"] is None and guide_store.GuideStore().guides_of("s_none") == []


def test_a_second_message_cannot_be_queued_while_one_is_waiting():
    from app.views import guide_ui
    import streamlit as st
    st.session_state.clear()
    st.session_state.gjob = {"text": "first", "action": None}
    guide_ui.queue(text="second")
    assert st.session_state.gjob["text"] == "first"


def test_a_professor_preview_saves_nothing(world, client):
    at = app("prof", body_done=True)
    from app import nav
    at._page_hash = nav.PAGES["guide"]._script_hash
    at.run()
    assert not at.exception
    open_first(at)
    at.chat_input[0].set_value("slide 5").run()
    assert "Previews are not saved." in md(at)
    assert guide_store.GuideStore().guides_of("preview") == [] and guide_store.GuideStore().guides_of("prof") == []


def test_no_horizontal_overflow_rules_exist_for_phone_width():
    from app import theme
    assert "overflow-wrap: anywhere" in theme.GUIDE_CSS and "max-width: 640px" in theme.GUIDE_CSS
