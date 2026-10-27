"""AnatoVision web app. Run:  .venv/bin/streamlit run app/main.py

Every run: seed accounts (first time only), require a signed-in user, then register ONLY the pages that user may open.
A student's navigation has no dashboard page at all, and the dashboard page checks the role again.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app import nav, theme  # noqa: E402
from app.data import get_runtime  # noqa: E402
from app.views import blocked, login, professor, student  # noqa: E402
from src import auth, chat_store, guide_store  # noqa: E402
from src.quiz import store as quiz_store  # noqa: E402

st.set_page_config(page_title="AnatoVision", page_icon=theme.FAVICON, layout="wide", initial_sidebar_state="auto")
theme.inject()


@st.cache_resource
def seed_accounts():
    return auth.ensure_seed()          # prints the generated passwords once, in the terminal that started the app


@st.cache_resource
def purge_old_chats():
    try:
        guide_store.GuideStore().purge()            # saved Guide sessions follow the same retention
        quiz_store.QuizStore().purge()
        return chat_store.ChatStore().purge()       # once per server start; also at every login (app/nav.py)
    except Exception:
        return 0


seed_accounts()
purge_old_chats()
user = nav.current_user()
if user is None:
    st.session_state.setdefault("asked_path", nav.requested_path())      # the login screen resets the address bar; remember it
    login.page()
    get_runtime()                      # warm the index and the embedding model while the login screen is already showing
    st.stop()


def student_page(mode):
    me = nav.current_user()
    if me is None:
        st.stop()
    st.session_state.mode = mode                    # the page decides the mode: /chat is Q&A, /guide is the Guide
    student.page(me if me["role"] == "student" else nav.preview_user(me), real_user=me)


def ask_page():
    student_page("qa")


def guide_page():
    student_page("guide")


def quiz_page():
    student_page("quiz")


def professor_page():
    professor.page(nav.current_user())


# Each page has its own title (shown in the browser tab as "<title> · AnatoVision") and a stable URL path.
if user["role"] == "professor":
    nav.PAGES = {"dashboard": st.Page(professor_page, title="Dashboard", url_path="dashboard", default=True),
                 "chat": st.Page(ask_page, title="Ask the lab (student view)", url_path="chat"),
                 "guide": st.Page(guide_page, title="Guide (student view)", url_path="guide"),
                 "quiz": st.Page(quiz_page, title="Quiz (student view)", url_path="quiz")}
else:
    # The instructor path exists for students too, so opening it shows "That page is for instructors" instead of
    # silently landing on the chat. It renders nothing from the dashboard.
    nav.PAGES = {"chat": st.Page(ask_page, title="Ask the lab", url_path="chat", default=True),
                 "guide": st.Page(guide_page, title="Guide", url_path="guide"),
                 "quiz": st.Page(quiz_page, title="Quiz", url_path="quiz"),
                 "dashboard": st.Page(blocked.show, title="Instructors only", url_path="dashboard")}
asked = st.session_state.pop("asked_path", "")
if asked and asked in nav.PAGES and not nav.PAGES[asked]._default:        # only registered pages; a student asking for /dashboard gets the "instructors" page
    st.switch_page(nav.PAGES[asked])
st.navigation(list(nav.PAGES.values()), position="hidden").run()
get_runtime()                          # cached: loaded once per server process, so the first question is not slow
