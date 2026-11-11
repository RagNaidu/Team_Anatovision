"""Who is signed in, who the student view is showing, and the page objects (set by app/main.py on every run)."""
import streamlit as st

from app.data import lectures
from src import auth, chat_store, guide_store

PAGES = {}
FULL_ACCESS = "Full access (all lectures)"


def current_user():
    """The signed-in account, re-read from data/users.json on every run (a removed or changed account takes effect at once)."""
    name = st.session_state.get("auth_user")
    user = auth.get_user(name) if name else None
    if user is None and name:
        st.session_state.clear()
    return user


def requested_path():
    """The page path in the address bar ('dashboard', 'guide', '' for the home page)."""
    try:
        from urllib.parse import urlparse
        return urlparse(st.context.url).path.strip("/")
    except Exception:
        return ""


def sign_in(user):
    try:
        guide_store.GuideStore().purge()
        chat_store.ChatStore().purge()               # chats unused for CHAT_RETENTION_DAYS (90) are deleted at login
    except Exception:
        pass
    asked = st.session_state.get("asked_path", "")
    st.session_state.clear()
    st.session_state.auth_user = user["username"]
    st.session_state.asked_path = asked                 # after sign-in, go where they were heading (see app/main.py)


def sign_out():
    st.session_state.clear()


def preview_user(professor):
    """The student the professor is previewing: a real student's grants, or all lectures. Always role 'student'."""
    choice = st.session_state.get("preview_as", FULL_ACCESS)
    if choice != FULL_ACCESS:
        u = auth.get_user(choice)
        if u and u["role"] == "student":
            return u
    return {"username": "preview", "name": "Preview", "role": "student", "allowed_lectures": [l["title"] for l in lectures()]}


def preview_picker():
    """Sidebar control for the professor: which student to preview."""
    options = [FULL_ACCESS] + [u for u, _ in auth.students()]
    st.selectbox("Preview as", options, key="preview_as")
