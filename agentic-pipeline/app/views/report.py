"""'Report an error' / 'Report a problem': a small form that sends one open flag to Dr. Inglis. Students never see any flag."""
import streamlit as st

from app import theme
from src import student_report as sr

THANKS = "Thanks, sent to Dr. Inglis."


def popover(key, label, username, question, view):
    """An inline expander (it opens in place, never beside the button) with a small form. `key` must be unique on the page.
    The page script scrolls it into view when it opens (see theme.A11Y_JS)."""
    with st.container(key=f"rp_{key}"):
        with st.expander(label, key=f"rx_{key}"):
            with st.form(f"report_form_{key}", border=False):
                reason = st.selectbox("What is wrong?", sr.REASONS, key=f"rr_{key}")
                comment = st.text_area("Anything else? (optional)", max_chars=sr.MAX_COMMENT, key=f"rc_{key}", height=100)
                send = st.form_submit_button("Send report", type="primary")
            if send:
                cites = [c["cite"] for c in view["citations"] if c["matched"]]
                urls = [x["source_url"] for x in view.get("sources", []) if view.get("web") and x.get("source_url")]
                sr.report_error(username, question, view["answer_text"], cites, reason, comment, web_urls=urls)
                st.session_state.setdefault("reported", set()).add(key)
                st.session_state[f"rx_{key}"] = False
                st.rerun()


def thanks_if_sent(key):
    if key in st.session_state.get("reported", set()):
        theme.alert("success", THANKS)
