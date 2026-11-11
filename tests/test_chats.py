"""Stage 2: chat history. The store (SQLite), its limits and retention, isolation between users, what is stored (student-safe only),
and the Q&A page flows (new chat, list, reopen without a model call, preview saves nothing). Model and search are faked."""
import json
import time

import pytest

from app import state
from src import chat_store as cs
from src import service
from src import student_view as sv
from tests.test_app import HAND, app, labels, texts, world  # noqa: F401  (fixtures)
from tests.test_student_safe import CTX, flagged_reply

DAY = 86400


@pytest.fixture
def store(tmp_path):
    return cs.ChatStore(tmp_path / "chats.db")


@pytest.fixture(autouse=True)
def chats_db(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "DB_PATH", tmp_path / "ui_chats.db")        # the page's own store, never data/chats.db


@pytest.fixture
def VIEW():
    """A real student view (built under the conftest isolation, so nothing is written to the real logs)."""
    shown, _ = flagged_reply()
    return shown["view"]


# ---------------------------------------------------------------------------------------------------------------
# the store
# ---------------------------------------------------------------------------------------------------------------

def test_create_list_rename_delete(store, VIEW):
    a = store.create_chat("student1", "What are the walls of the middle ear?")
    b = store.create_chat("student1", "Boundaries of the femoral triangle")
    store.add_turn("student1", a, "What are the walls of the middle ear?", VIEW)
    assert {c["title"] for c in store.list_chats("student1")} == {"What are the walls of the middle ear?", "Boundaries of the femoral triangle"}
    assert store.list_chats("student1")[0]["id"] == a and store.list_chats("student1")[0]["n_messages"] == 2   # newest activity first
    assert store.rename_chat("student1", a, "  Ear   walls ") and store.get_chat("student1", a)["title"] == "Ear walls"
    with pytest.raises(ValueError):
        store.rename_chat("student1", a, "   ")
    assert store.delete_chat("student1", b) and store.get_chat("student1", b) is None
    assert store.delete_chat("student1", b) is False and len(store.list_chats("student1")) == 1


def test_delete_is_permanent_and_takes_the_messages_with_it(store, VIEW):
    a = store.create_chat("u", "q")
    store.add_turn("u", a, "q", VIEW)
    store.delete_chat("u", a)
    import sqlite3
    db = sqlite3.connect(store.path)
    assert db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0 and db.execute("SELECT COUNT(*) FROM chats").fetchone()[0] == 0


def test_the_title_is_the_first_question_cut_at_a_word_with_no_model_call(store):
    long_q = "What are the boundaries and the contents of the femoral triangle and how does it relate to the adductor canal?"
    title = cs.make_title(long_q)
    assert title.endswith("…") and len(title) <= cs.TITLE_CHARS + 1 and long_q.startswith(title[:-1])
    assert cs.make_title("  Short   question? ") == "Short question?" and cs.make_title("") == "New chat"
    assert store.get_chat("u", store.create_chat("u", long_q))["title"] == title


def test_groups_today_yesterday_previous_7_days_older():
    now = time.time()
    chats = [{"id": str(i), "title": str(i), "updated": now - d * DAY} for i, d in enumerate([0, 1, 3, 7, 8, 40])]
    names = [g for g, _ in cs.grouped(chats, now)]
    assert names == ["Today", "Yesterday", "Previous 7 days", "Older"]
    assert [len(items) for _, items in cs.grouped(chats, now)] == [1, 1, 2, 2]


def test_retention_deletes_chats_with_no_activity_for_90_days(store, VIEW):
    now = time.time()
    old = store.create_chat("u", "old one", now=now - 91 * DAY)
    edge = store.create_chat("u", "edge", now=now - 89 * DAY)
    live = store.create_chat("u", "live", now=now - 91 * DAY)
    store.add_turn("u", live, "live", VIEW, now=now - 2 * DAY)                # activity keeps a chat alive
    assert store.purge(now=now) == 1
    assert {c["id"] for c in store.list_chats("u")} == {edge, live} and store.get_chat("u", old) is None


def test_retention_days_is_configurable(store, monkeypatch):
    assert cs.retention_days() == 90
    monkeypatch.setenv("CHAT_RETENTION_DAYS", "30")
    now = time.time()
    c = store.create_chat("u", "x", now=now - 31 * DAY)
    assert cs.retention_days() == 30 and store.purge(now=now) == 1 and store.get_chat("u", c) is None
    monkeypatch.setenv("CHAT_RETENTION_DAYS", "nonsense")
    assert cs.retention_days() == 90


def test_each_user_sees_only_their_own_chats(store, VIEW):
    c1 = store.create_chat("student1", "my private question")
    store.add_turn("student1", c1, "my private question", VIEW)
    store.create_chat("student2", "another")
    assert [c["title"] for c in store.list_chats("student2")] == ["another"]
    assert store.get_chat("student2", c1) is None                                  # a guessed id is not enough
    assert store.rename_chat("student2", c1, "stolen") is False and store.delete_chat("student2", c1) is False
    with pytest.raises(KeyError):
        store.add_turn("student2", c1, "q", VIEW)
    assert store.get_chat("student1", c1)["title"] == "my private question" and len(store.get_chat("student1", c1)["messages"]) == 2


def test_limits_50_chats_and_200_messages_with_friendly_messages(store, VIEW):
    for i in range(cs.MAX_CHATS):
        store.create_chat("u", f"q{i}")
    with pytest.raises(cs.ChatLimit) as e:
        store.create_chat("u", "one too many")
    assert "50" in str(e.value) and "Delete" in str(e.value)
    store.create_chat("other", "other users are not affected")
    cid = store.list_chats("u")[0]["id"]
    for i in range(cs.MAX_MESSAGES // 2):
        assert store.can_add_turn("u", cid)
        store.add_turn("u", cid, f"q{i}", VIEW)
    assert not store.can_add_turn("u", cid)
    with pytest.raises(cs.ChatLimit) as e:
        store.add_turn("u", cid, "q", VIEW)
    assert "200" in str(e.value) and "new chat" in str(e.value).lower()
    assert len(store.get_chat("u", cid)["messages"]) == cs.MAX_MESSAGES


def test_reopening_restores_every_message_exactly(store):
    shown, _ = flagged_reply()
    view = shown["view"]
    cid = store.create_chat("student1", "walls?")
    store.add_turn("student1", cid, "walls?", view, brief=False)
    chat = store.get_chat("student1", cid)
    assert [m["role"] for m in chat["messages"]] == ["user", "assistant"] and chat["messages"][0]["text"] == "walls?"
    got = chat["messages"][1]
    assert got["result"] == json.loads(json.dumps(view, default=str)) and got["brief"] is False and got["instructor"] is None
    assert got["result"]["sources"] and got["result"]["built"] and got["result"]["citations"]      # sources + "how it was built" are there


def test_what_is_stored_is_student_safe_and_never_contains_the_raw_answer(store, tmp_path):
    shown, _ = flagged_reply()
    cid = store.create_chat("student1", "walls?")
    store.add_turn("student1", cid, "walls?", shown["view"])
    chat = store.get_chat("student1", cid)
    assert sv.leaks(chat) == [], sv.leaks(chat)
    import sqlite3
    raw = " ".join(r[0] for r in sqlite3.connect(store.path).execute("SELECT payload FROM messages"))
    assert sv.leaks(json.loads(f'"{raw[:0]}"') or raw) == [] and "SECRET" not in raw
    for key in ("events", "cost", "tokens", "flags_hit", "retrieved_chunks"):
        assert f'"{key}"' not in raw


# ---------------------------------------------------------------------------------------------------------------
# the Q&A page
# ---------------------------------------------------------------------------------------------------------------

def ask(at, text):
    at.chat_input[0].set_value(text).run()
    at.run()
    return at


def test_a_students_question_is_saved_as_a_chat_and_listed_under_today(world):
    at = app("s_hand", body_done=True)
    assert "Your chats will be listed here." in texts(at) and "New chat" in labels(at)
    assert f"Chats are kept for {cs.retention_days()} days." in texts(at)
    ask(at, "What are the walls?")
    assert not at.exception
    chats = cs.ChatStore().list_chats("s_hand")
    assert [c["title"] for c in chats] == ["What are the walls?"] and chats[0]["n_messages"] == 2
    assert "Today" in texts(at) and "What are the walls?" in labels(at)
    assert at.session_state["chat_id"] == chats[0]["id"]


def test_follow_ups_stay_in_the_same_chat_and_new_chat_starts_fresh_with_no_old_context(world):
    spy, rt = world
    at = app("s_hand", body_done=True)
    ask(at, "What are the walls?")
    ask(at, "and the floor?")
    assert len(cs.ChatStore().list_chats("s_hand")) == 1 and cs.ChatStore().list_chats("s_hand")[0]["n_messages"] == 4
    helper_calls_before = len(rt.client.calls)
    next(b for b in at.button if b.label == "New chat").click().run()
    assert at.session_state["chat_id"] is None and at.session_state["messages"] == []
    ask(at, "What are the walls of the ear?")
    assert len(cs.ChatStore().list_chats("s_hand")) == 2
    # the first question of a new chat has no earlier turns, so no follow-up rewrite call is made for it
    assert all("<follow_up>" not in json.dumps(c) for c in rt.client.calls[helper_calls_before:])


def test_reopening_a_chat_restores_it_and_does_not_call_the_model(world):
    spy, rt = world
    at = app("s_hand", body_done=True)
    ask(at, "What are the walls?")
    next(b for b in at.button if b.label == "New chat").click().run()
    assert "The walls are six." not in texts(at)
    calls = len(rt.client.calls)
    searches = len(spy.allowed_seen)
    next(b for b in at.button if b.key and b.key.startswith("chatopen_")).click().run()
    assert "The walls are six." in texts(at) and not at.exception
    assert any(b.key and b.key.startswith("chip_") for b in at.button)             # the citation chips are back
    assert len(rt.client.calls) == calls and len(spy.allowed_seen) == searches      # no model call, no search
    assert at.session_state["chat_id"] == cs.ChatStore().list_chats("s_hand")[0]["id"]


def test_the_open_chat_is_marked_in_the_list(world):
    at = app("s_hand", body_done=True)
    ask(at, "What are the walls?")
    assert any(b.key and b.key.startswith("chatcur_") for b in at.button) and not any(b.key and b.key.startswith("chatopen_") for b in at.button)


def test_a_new_session_after_sign_in_still_lists_the_old_chats(world):
    at = app("s_hand", body_done=True)
    ask(at, "What are the walls?")
    again = app("s_hand", body_done=True)
    assert "What are the walls?" in labels(again) and "Your chats will be listed here." not in texts(again)


def test_students_never_see_each_others_chats_in_the_page(world):
    at = app("s_hand", body_done=True)
    ask(at, "My own private question")
    other = app("s_none", body_done=True)
    assert "My own private question" not in labels(other) and "Your chats will be listed here." in texts(other)


def test_a_professor_previewing_as_a_student_saves_nothing(world):
    def run():
        from app.views import student
        from tests.test_app import HAND
        student.page({"username": "preview", "name": "Preview", "role": "student", "allowed_lectures": [HAND]},
                     real_user={"username": "prof", "name": "Dr. Inglis", "role": "professor", "allowed_lectures": []})
    from streamlit.testing.v1 import AppTest
    t = AppTest.from_function(run, default_timeout=60)
    t.session_state["body_done"] = True
    t.run()
    assert not t.exception and "Previews are not saved as chats." in " ".join(m.value for m in t.markdown) and "New chat" not in labels(t)
    t.chat_input[0].set_value("What are the walls?").run()
    t.run()
    assert not t.exception and "The walls are six." in texts(t)
    assert cs.ChatStore().list_chats("preview") == [] and cs.ChatStore().list_chats("prof") == []


def test_asking_in_a_full_chat_list_says_so_and_does_not_call_the_model(world):
    spy, rt = world
    s = cs.ChatStore()
    for i in range(cs.MAX_CHATS):
        s.create_chat("s_hand", f"old {i}")
    at = app("s_hand", body_done=True)
    at.chat_input[0].set_value("What are the walls?").run()
    assert cs.CHATS_FULL in texts(at) and len(rt.client.calls) == 0 and len(s.list_chats("s_hand")) == cs.MAX_CHATS


def test_asking_in_a_full_chat_says_so(world, VIEW):
    spy, rt = world
    s = cs.ChatStore()
    cid = s.create_chat("s_hand", "full")
    for i in range(cs.MAX_MESSAGES // 2):
        s.add_turn("s_hand", cid, f"q{i}", VIEW)
    at = app("s_hand", body_done=True)
    next(b for b in at.button if b.key and b.key.startswith("chatopen_")).click().run()
    at.chat_input[0].set_value("one more").run()
    assert cs.CHAT_FULL in texts(at) and len(rt.client.calls) == 0


def test_login_and_app_start_purge_old_chats(world, monkeypatch):
    s = cs.ChatStore()
    old = s.create_chat("s_hand", "ancient", now=time.time() - 120 * DAY)
    fresh = s.create_chat("s_hand", "recent")
    from app import nav
    class SS(dict):
        __getattr__ = dict.get
        __setattr__ = dict.__setitem__
    monkeypatch.setattr(nav.st, "session_state", SS())
    nav.sign_in({"username": "s_hand"})
    assert s.get_chat("s_hand", old) is None and s.get_chat("s_hand", fresh) is not None


def test_new_chat_resets_state():
    def run():
        import streamlit as st
        from app import state
        st.session_state.update(messages=[1], chat_id="x", sel={"a": 1}, busy="q", pending_q="p")
        state.new_chat()
        st.write(str((st.session_state.messages, st.session_state.chat_id, st.session_state.sel, st.session_state.busy)))
    from streamlit.testing.v1 import AppTest
    assert "([], None, None, None)" in AppTest.from_function(run).run().markdown[0].value
