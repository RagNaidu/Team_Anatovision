"""The page a student gets when they open an instructor-only path (instead of a silent redirect)."""
import streamlit as st

from app import nav, theme

BACK_LABEL = "Back to Ask the lab"


def show():
    theme.set_title("Instructors only")
    st.markdown('<div class="landing"><h1>That page is for instructors</h1>'
                "<p class=\"lead\">Your account does not have access to it. You can keep asking questions about the lab.</p></div>",
                unsafe_allow_html=True)
    if st.button(BACK_LABEL, key="blocked_back"):
        target = nav.PAGES.get("chat")
        if target is not None:
            st.switch_page(target)
