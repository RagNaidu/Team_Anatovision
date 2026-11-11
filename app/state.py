"""Session state shared by the views: who is signed in, body type, scope, running cost and the spending cap."""
import streamlit as st

from src import usage

FAT = ["more", "average", "less"]
MUSCLE = ["more", "average", "less"]
BUILD = ["large", "average", "small"]


def init():
    d = st.session_state
    d.setdefault("mode", "qa")                  # qa | guide
    d.setdefault("body_done", False)            # the body type has been asked (answered or skipped)
    d.setdefault("body_type", "")
    d.setdefault("messages", [])
    d.setdefault("chat_id", None)               # the saved chat that is open (None = a new chat that has no saved turn yet)
    d.setdefault("sel", None)                   # what the Sources pane shows
    d.setdefault("pane", "Sources")
    d.setdefault("cost", 0.0)
    d.setdefault("tokens", {"input": 0, "output": 0})
    d.setdefault("busy", None)                  # question waiting for its answer
    d.setdefault("pending_q", None)
    d.setdefault("brief", usage.load_settings()["default_brief"])


def body_string(fat, muscle, build):
    return f"{fat} fat, {muscle} muscle, {build} build"


def add_cost(cost, tokens=None):
    st.session_state.cost += cost or 0.0
    if tokens:
        st.session_state.tokens["input"] += tokens.get("input", 0)
        st.session_state.tokens["output"] += tokens.get("output", 0)


def cap():
    return usage.load_settings()["spending_cap_usd"]


def cap_reached():
    return st.session_state.cost >= cap()


def new_chat():
    """A fresh, empty chat. Follow-up context comes only from the open chat, so nothing carries over."""
    d = st.session_state
    d.messages, d.chat_id, d.sel, d.busy, d.pending_q = [], None, None, None, None
