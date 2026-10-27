"""Login screen (demo-grade; see src/auth.py)."""
import time

import streamlit as st

from app import nav, theme
from src import auth

BAD_LOGIN = "That username or password didn't match. Try again."
LOCKED = "Too many tries. Wait a few minutes and try again."


def page():
    theme.set_title("Sign in")
    with st.container(key="login_card"):
        theme.wordmark()
        theme.meta("Sign in to ask about the lab, or to review the notes.")
        with st.form("login", border=False):
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            go = st.form_submit_button("Sign in", type="primary")
        with st.container(key="login_msg"):              # a fixed-height slot below the button: an error never moves the form
            slot = st.empty()
            slot.markdown('<div class="alert-slot"></div>', unsafe_allow_html=True)
        if go:
            if auth.locked(username.strip()):
                slot.markdown(theme.alert_html("warning", "Sign-in paused", LOCKED, focus="Username"), unsafe_allow_html=True)
            else:
                user = auth.authenticate(username, password)
                if user:
                    nav.sign_in(user)
                    st.rerun()
                time.sleep(1)                                   # slows guessing; demo-grade
                slot.markdown(theme.alert_html("error", "Could not sign in", BAD_LOGIN, focus="Password"), unsafe_allow_html=True)
        if auth.demo_mode():              # ANATOVISION_DEMO=0 turns this off; it is never shown after sign-in
            theme.meta("Demo login on one machine, not production security. A real deployment would use UB single sign-on.")
