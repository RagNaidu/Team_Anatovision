"""Student chat: sidebar controls, body-type intake, Q&A with live citation chips, and the Sources pane."""
import html
import re

import streamlit as st

from app import nav, state, theme
from app.data import get_runtime, lectures
from app.views import guide_ui, pane, quiz_ui, report
from src import chat_store
from src.ingest import guides
from src import query as qry
from src import service
from src import student_view as sv

EXAMPLES = [
    ("ex_ear", "What are the walls of the middle ear?", "qa"),
    ("ex_fem", "What are the boundaries and contents of the femoral triangle?", "qa"),
    ("ex_guide", "Start a Guide walkthrough: Lecture 09, The Hand", "guide"),
]


# ----------------------------------------------------------------------------
# who may see what
# ----------------------------------------------------------------------------

def accessible_lectures(user):
    """Lecture titles this user may use: only what the professor granted (read fresh from data/users.json)."""
    granted = set(user.get("allowed_lectures", []))
    return [t for t in [l["title"] for l in lectures()] + [g for g, _ in guides.guide_labels()] if t in granted]


def lecture_options(user):
    """Only the lectures (not the 'Dissection Guide, Class N' grants) among a user's grants."""
    return [t for t in accessible_lectures(user) if not t.startswith("Dissection Guide,")]


def effective_scope(user):
    """The lectures the search is allowed to use now: the user's access, narrowed by the sidebar choice."""
    allowed = accessible_lectures(user)
    chosen = [t for t in st.session_state.get("scope", []) if t in allowed]
    return chosen or allowed         # [] for a student with no grants: the search then returns OpenStax only


# ----------------------------------------------------------------------------
# sidebar
# ----------------------------------------------------------------------------

def mode_nav():
    """The Guide / Q&A / Quiz switcher: real links to real pages (so the selected one is exposed to screen readers),
    with the selected item filled and barred, and Quiz disabled with a "Coming soon" badge."""
    theme.label("Mode")
    st.page_link(nav.PAGES["guide"], label="Guide", icon=":material/menu_book:")
    st.page_link(nav.PAGES["chat"], label="Q&A", icon=":material/chat:")
    st.page_link(nav.PAGES["quiz"], label="Quiz", icon=":material/quiz:")


# ----------------------------------------------------------------------------
# chat history (Q&A). Saved per user in data/chats.db; a professor previewing a student saves nothing.
# ----------------------------------------------------------------------------

def store():
    return chat_store.ChatStore()


def saves_chats(real_user):
    """A real student session saves chats; a professor previewing as a student never does."""
    return not (real_user and real_user["role"] == "professor")


def open_chat(username, chat_id):
    chat = store().get_chat(username, chat_id)
    if chat is None:                                  # deleted meanwhile, or not this user's: nothing changes
        return
    d = st.session_state
    d.messages, d.chat_id, d.sel, d.busy, d.pending_q = chat["messages"], chat_id, None, None, None
    d.body_done = True


def ask_dialog(kind, chat_id, title):
    st.session_state.dlg = (kind, chat_id, title)


def chat_row(username, c, current):
    with st.container(horizontal=True, gap="small", key=f"chatrow_{c['id'][:8]}"):
        st.button(c["title"], key=f"{'chatcur' if current else 'chatopen'}_{c['id'][:8]}", on_click=open_chat,
                  args=(username, c["id"]), help=c["title"])
        with st.popover("⋯", key=f"chatmenu_{c['id'][:8]}", help="Rename or delete this chat"):
            st.button("Rename", key=f"chatren_{c['id'][:8]}", on_click=ask_dialog, args=("rename", c["id"], c["title"]),
                      icon=":material/edit:")
            st.button("Delete", key=f"chatdel_{c['id'][:8]}", on_click=ask_dialog, args=("delete", c["id"], c["title"]),
                      icon=":material/delete:")


def chat_sidebar(user, real_user):
    """'New chat', then this user's saved chats grouped Today / Yesterday / Previous 7 days / Older."""
    if not saves_chats(real_user):
        theme.meta("Previews are not saved as chats.")
        return
    username = user["username"]
    st.button("New chat", key="chatnew", on_click=state.new_chat, icon=":material/add:", type="primary")
    try:
        chats = store().list_chats(username)
    except Exception:
        chats = []
        theme.meta("Saved chats are unavailable right now.")
    if not chats:
        theme.meta("Your chats will be listed here.")
    for group, items in chat_store.grouped(chats):
        theme.label(group)
        for c in items:
            chat_row(username, c, current=(c["id"] == st.session_state.get("chat_id")))
    theme.meta(f"Chats are kept for {chat_store.retention_days()} days.")


def chat_dialogs(user, real_user):
    """Rename / delete open as a modal; the delete asks first and says it is permanent."""
    dlg = st.session_state.pop("dlg", None)
    if not dlg or not saves_chats(real_user):
        return
    kind, chat_id, title = dlg
    username = user["username"]
    if kind == "rename":
        @st.dialog("Rename chat")
        def rename():
            name = st.text_input("Name", value=title, max_chars=120, key="rename_input")
            with theme.button_row("rename_buttons"):
                if st.button("Save", key="rename_save", type="primary"):
                    try:
                        store().rename_chat(username, chat_id, name)
                        st.rerun()
                    except ValueError as exc:
                        theme.meta(str(exc), tone="error")
                if st.button("Cancel", key="rename_cancel"):
                    st.rerun()
        rename()
    else:
        @st.dialog("Delete this chat?")
        def delete():
            st.markdown(f"“{theme.esc(title)}” and all its answers will be deleted for good. This cannot be undone.")
            with theme.button_row("delete_buttons"):
                if st.button("Delete chat", key="danger_delete_chat"):
                    store().delete_chat(username, chat_id)
                    if st.session_state.get("chat_id") == chat_id:
                        state.new_chat()
                    st.rerun()
                if st.button("Cancel", key="delete_cancel"):
                    st.rerun()
        delete()


def save_turn(user, real_user, question, view, brief):
    """Store the question and its student-safe answer. Never raises: a storage problem must not lose the answer on screen."""
    if not saves_chats(real_user):
        return
    try:
        s = store()
        if st.session_state.chat_id is None:
            st.session_state.chat_id = s.create_chat(user["username"], question)
        s.add_turn(user["username"], st.session_state.chat_id, question, view, brief)
    except Exception:
        st.session_state.chat_notice = "This answer could not be saved to your chat history."


def limit_message(user, real_user):
    """A friendly sentence if the question cannot be saved (50 chats, 200 messages); '' if it can."""
    if not saves_chats(real_user):
        return ""
    try:
        s = store()
        cid = st.session_state.chat_id
        if cid is None:
            return chat_store.CHATS_FULL if len(s.list_chats(user["username"])) >= chat_store.MAX_CHATS else ""
        return "" if s.can_add_turn(user["username"], cid) else chat_store.CHAT_FULL
    except Exception:
        return ""


def sidebar(user, real_user=None, extra=None):
    mode = st.session_state.mode
    for key in ("length", "scope"):                      # keep these two alive while the Guide (which hides them) is open
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]
    with st.sidebar:
        theme.wordmark()
        if real_user and real_user["role"] == "professor":
            theme.label("Preview")
            theme.meta(f'You are seeing exactly what {user["name"]} sees. An extra "Instructor detail" tab next to each '
                       'answer is for you only.')
            nav.preview_picker()
            st.page_link(nav.PAGES["dashboard"], label="Back to dashboard", icon=":material/arrow_back:")
        mode_nav()
        if mode == "qa":
            chat_sidebar(user, real_user)

        if mode != "quiz":
            theme.label("Cadaver body type (optional)")
            if st.session_state.body_done or mode == "guide":         # in the Guide it is never asked first and never blocks anything
                with st.expander(st.session_state.body_type or "Not given", expanded=False):
                    body_editor("side")
            else:
                theme.meta("Asked before your first question.")

        if mode == "qa":                                  # these two only apply to Q&A, so the Guide does not show them
            theme.label("Answer length")
            st.segmented_control("Answer length", ["Brief", "Detailed"], key="length", label_visibility="collapsed",
                                 default="Brief" if st.session_state.brief else "Detailed")
            if not st.session_state.messages:               # a one-line hint, only until the first question
                theme.meta("Brief: about five lines. Detailed: a full walk-through.")
            st.session_state.brief = st.session_state.get("length", "Brief") != "Detailed"

            theme.label("Lecture scope")
            options = lecture_options(user)
            if not options:
                theme.meta(("No lectures or dissection guides have been shared with you yet. Ask your instructor. "
                            if not accessible_lectures(user) else "No lectures have been shared with you yet. Ask your instructor. ")
                           + "You can still ask about the OpenStax reference text.")
            else:
                st.multiselect("Lecture scope", options, key="scope", label_visibility="collapsed",
                               placeholder="All lectures you can use")
        if extra:
            extra()
        theme.label("Session")
        theme.meta(f'Signed in as {(real_user or user)["name"]}')
        st.button("Sign out", key="signout_chat", on_click=nav.sign_out)
        theme.meta("Reloading this page signs you out." + ((" Your saved chats reopen from the list." if mode == "qa" and saves_chats(real_user) else
                                                                           " Your Guide progress is saved; sign in again to continue." if mode == "guide" and saves_chats(real_user) else
                                                                           " An unfinished quiz is saved; sign in again to resume it." if mode == "quiz" else " The chat is cleared.")))
        if state.cap_reached():
            theme.alert("warning", "Session limit reached", "No more answers can be written. Ask your instructor.")


def body_editor(where):
    """Three small pickers; the saved value is a plain sentence the model sees ('more fat, average muscle, small build')."""
    fat = st.selectbox("Fat", state.FAT, index=1, key=f"fat_{where}")
    muscle = st.selectbox("Muscle", state.MUSCLE, index=1, key=f"muscle_{where}")
    build = st.selectbox("Build", state.BUILD, index=1, key=f"build_{where}")
    if st.button("Save", key=f"bodysave_{where}", type="primary"):
        st.session_state.body_type = state.body_string(fat, muscle, build)
        st.session_state.body_done = True
        st.rerun()


def intake_card():
    """Asked once, at the start, but it never blocks anything: Continue and Skip for now are equally prominent, a question
    asked without answering counts as skipped, and the choice can be changed any time from the sidebar."""
    with st.container(key="intake_card"):
        st.markdown('<div class="section-title">Which cadaver are you working on?</div>', unsafe_allow_html=True)
        theme.meta("Body fat, muscle and build change what you see. Tell me so the guidance can mention it where the notes do.")
        c1, c2, c3 = st.columns(3)
        fat = c1.selectbox("Fat", state.FAT, index=1, key="fat_intake")
        muscle = c2.selectbox("Muscle", state.MUSCLE, index=1, key="muscle_intake")
        build = c3.selectbox("Build", state.BUILD, index=1, key="build_intake")
        with theme.button_row("intake_buttons"):
            go = st.button("Continue", key="intake_go", type="primary")
            skip = st.button("Skip for now", key="intake_skip", type="primary")
    if go:
        st.session_state.body_type = state.body_string(fat, muscle, build)
        st.session_state.body_done = True
        st.rerun()
    if skip:
        st.session_state.body_type, st.session_state.body_done = "", True
        st.rerun()


# ----------------------------------------------------------------------------
# Q&A
# ----------------------------------------------------------------------------

def landing():
    st.markdown(theme.empty_state_html("book-open", "Ask about the lab.",
                "Answers come from Dr. Inglis's lecture notes, step by step, with the source of every line. "
                "Try one of these.").replace('class="empty"', 'class="empty empty-center"'), unsafe_allow_html=True)
    with st.container(key="examples"):
        for key, text, mode in EXAMPLES:
            if st.button(text, key=key):
                st.session_state.body_done = True
                if mode == "guide":
                    st.session_state.guide_lecture_pref = "Lecture 09"
                    st.switch_page(nav.PAGES["guide"])
                else:
                    st.session_state.pending_q = text
                st.rerun()


def unit_markdown(text):
    return text.replace("$", "\\$")


def render_user(msg):
    st.markdown(f'<div class="msg-label">You</div><div class="msg-user">{theme.esc(msg["text"])}</div>', unsafe_allow_html=True)


CARD_TITLES = {
    "nothing_relevant": "Not covered in the notes or the textbook",
    "not_anatomy": "Not an anatomy question",
    "clinical_advice": "Outside what this tool covers",
    "declined": "Not covered in the course notes",
    "outside_access": "Not in your lectures yet",
    "too_long": "Question too long",
}
STATUS_KEY = {"reviewing": "review", "check": "flag", "corrected": "verif"}


def card(kind, title, text):
    theme.alert(kind, title, text)


BULLET_RE = re.compile(r"^\s*[-*\u2022]\s+")
NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+")


def marker_html(i, view, n):
    """A small numbered source marker, e.g. [2]. It is a real link-like control: clicking it (or Enter) asks the page script to press
    the hidden button of that source, which opens it in the Sources panel (Streamlit cannot call Python from plain HTML)."""
    u = view["cite_unit"].get(n, 0)
    return f'<a class="cite" href="#" role="button" data-cite="{i}_{u}_{n}" aria-label="Open source {n} in the side panel">[{n}]</a>'


def block_text(block, i, view):
    text = html.escape(block["text"], quote=False).replace("$", "&#36;")
    marks = "".join(marker_html(i, view, n) for n in block["markers"])
    if block.get("note"):
        return f'<span class="muted-note">{text}</span>'
    return f"{text} {marks}".rstrip()


def segments(blocks):
    """Consecutive bullets (or consecutive numbered steps) become ONE markdown list so they render as a list; everything else is a paragraph."""
    out = []
    for k, b in enumerate(blocks):
        kind = "bullet" if BULLET_RE.match(b["text"]) else "num" if NUMBERED_RE.match(b["text"]) else "para"
        if out and kind != "para" and out[-1]["kind"] == kind:
            out[-1]["blocks"].append((k, b))
        else:
            out.append({"kind": kind, "blocks": [(k, b)]})
    return out


def sources_html(i, view):
    items = []
    for e in view["sources_list"]:
        u = view["cite_unit"].get(e["n"], 0)
        label = html.escape(e["label"], quote=False)
        if e["url"]:
            a = f'<a href="{html.escape(e["url"])}" target="_blank" rel="noopener noreferrer">{label}</a>'
        else:
            a = f'<a class="cite-open" href="#" role="button" data-cite="{i}_{u}_{e["n"]}">{label}</a>'
        items.append(f'<li value="{e["n"]}">{a}</li>')
    return f'<div class="src-block"><div class="src-title">Sources</div><ol class="src-list">{"".join(items)}</ol></div>' if items else ""


def render_answer(i, msg, user=None, question="", first=False):
    """Renders the student-safe answer (msg["result"], built by src/student_view.py): the answer first, then a Sources list."""
    res = msg["result"]
    mode_note = "brief" if msg["brief"] else "detailed"
    st.markdown(f'<div class="msg-label">AnatoVision · Q&A · {mode_note}</div>', unsafe_allow_html=True)
    status = res["status"]
    answered = False
    if status in ("not_found", "out_of_scope"):
        card("info", CARD_TITLES.get(res["reason"], "Not covered"), res["answer_text"])      # calm: nothing went wrong
    elif status == "capped":
        card("warning", "Session limit reached", res["answer_text"])
    elif status == "error":
        card("warning" if res["reason"] == "too_long" else "error", CARD_TITLES.get(res["reason"], "Could not answer"), res["answer_text"])
    elif status == "access_limited" and not res["sources"]:
        card("info", CARD_TITLES["outside_access"], res["answer_text"])
    else:
        answered = True
        ans = st.container(key=f"ans_{i}")
        for g, seg in enumerate(segments(res["blocks"])):
            body = "\n".join(block_text(b, i, res) for _, b in seg["blocks"])
            ans.markdown(body if seg["kind"] != "para" else body, unsafe_allow_html=True)
            for k, b in seg["blocks"]:
                if b["status"]:                                 # a withheld, doubtful or corrected line: a small button under it
                    with ans.container(horizontal=True, gap="small", key=f"mark_{i}_{k}"):
                        for item in b["status"]:
                            what = item["kind"]
                            st.button(item["label"], key=f"s{STATUS_KEY[what]}_{i}_{k}_{what}", on_click=pane.select,
                                      args=(i, "status"), kwargs={"what": what})
        with st.container(key=f"cites_{i}"):                   # hidden: the markers and the Sources list press these (see theme.A11Y_JS)
            for e in res["sources_list"]:
                u = res["cite_unit"].get(e["n"], 0)
                st.button(f'Source {e["n"]}', key=f"chip_{i}_{u}_{e['n']}", on_click=pane.select, args=(i, "cite"),
                          kwargs={"n": e["n"], "unit": u})
        st.markdown(sources_html(i, res), unsafe_allow_html=True)
        for line in (res.get("footer"), res.get("notice")):
            if line:
                st.markdown(f'<div class="src-foot">{html.escape(line, quote=False)}</div>', unsafe_allow_html=True)
    if res["n_unmatched"]:
        theme.meta(f'{res["n_unmatched"]} citation(s) not found')
    if answered:
        with theme.button_row(f"foot_{i}"):
            report.popover(f"a{i}", "Report an error", user["username"] if user else "", question, res)
            if first:
                report.popover(f"p{i}", "Report a problem", user["username"] if user else "", question, res)
        report.thanks_if_sent(f"a{i}")
        report.thanks_if_sent(f"p{i}")
    st.markdown('<div class="turn-rule"></div>', unsafe_allow_html=True)


def ask_now(user, question, scope, real_user=None):
    """Always as a student: the lectures come from the grants (never from the UI). Returns {"view", "cost", "tokens",
    "instructor"}; only "view" goes to the student screens. A professor previewing keeps the full result for the extra tab."""
    preview = bool(real_user and real_user["role"] == "professor")
    return service.ask_for_student(
        question, st.session_state.body_type, st.session_state.brief, scope, runtime=get_runtime(), keep_instructor=preview,
        session_cost=st.session_state.cost, cap=state.cap(), history=qry.recent_turns(st.session_state.messages),
        user=real_user["username"] if preview else user["username"], as_user=user["username"] if preview else "",
        kind="professor_preview" if preview else "chat_answer")


def too_long(text):
    n = len(text.strip())
    return service.too_long_message(n) if n > service.MAX_QUESTION_CHARS else ""


def qa_view(user, real_user=None):
    msgs = st.session_state.messages
    preview = bool(real_user and real_user["role"] == "professor")
    if st.session_state.pending_q:
        q, st.session_state.pending_q = st.session_state.pending_q, None
        msgs.append({"role": "user", "text": q})
        st.session_state.busy = q
        st.rerun()

    chat, side = st.columns([3, 2], gap="large")
    with chat:
        if note := st.session_state.pop("q_notice", None):
            theme.alert("warning", "Question too long", note)
        if note := st.session_state.pop("limit_notice", None):
            theme.alert("warning", "Chat history is full", note)
        if note := st.session_state.pop("chat_notice", None):
            theme.meta(note)
        if not st.session_state.body_done and not msgs:
            intake_card()
        if not msgs:
            landing()
        first_answer = next((i for i, m in enumerate(msgs) if m["role"] == "assistant" and m["result"]["status"] == "answered"), None)
        for i, m in enumerate(msgs):
            if m["role"] == "user":
                render_user(m)
            else:
                render_answer(i, m, user, msgs[i - 1]["text"] if i else "", first=(i == first_answer))
        if st.session_state.busy:
            q, st.session_state.busy = st.session_state.busy, None
            loading = st.empty()                      # a skeleton row that keeps its height, so nothing shifts when the answer lands
            loading.markdown(theme.loading_html("Searching the notes…"), unsafe_allow_html=True)
            reply = ask_now(user, q, effective_scope(user), real_user)
            loading.empty()
            state.add_cost(reply["cost"], reply["tokens"])
            msgs.append({"role": "assistant", "result": reply["view"], "instructor": reply["instructor"],
                         "brief": st.session_state.brief})
            save_turn(user, real_user, q, reply["view"], st.session_state.brief)
            st.session_state.sel = None
            st.rerun()
        st.markdown('<div class="chat-end"></div>', unsafe_allow_html=True)        # room so the last line clears the input bar
    last = next((i for i in range(len(msgs) - 1, -1, -1) if msgs[i]["role"] == "assistant"), None)
    shown = st.session_state.sel["msg"] if st.session_state.sel else last
    with side:
        if shown is not None:                              # no empty tab bar floating beside a blank page
            q_shown = msgs[shown - 1]["text"] if shown else ""
            pane.render_pane(shown, msgs[shown], instructor=preview, latest=(shown == last), question=q_shown,
                             report=lambda: report.popover(f"s{shown}", "Report a problem", user["username"], q_shown, msgs[shown]["result"]))

    prompt = st.chat_input("Ask about the lab or the notes", max_chars=service.MAX_QUESTION_CHARS)
    theme.meta(f"Questions can be up to {service.MAX_QUESTION_CHARS} characters.")
    if prompt:
        if msg := too_long(prompt):
            st.session_state.q_notice = msg
        elif full := limit_message(user, real_user):
            st.session_state.limit_notice = full
        else:
            st.session_state.body_done = True                 # asking without answering the body-type card counts as "skip for now"
            msgs.append({"role": "user", "text": prompt})
            st.session_state.busy = prompt
        st.rerun()


def preview_bar(user):
    """Shown ONLY to a professor previewing (never in a student's own session): who they are previewing as, and a way out."""
    n = len(accessible_lectures(user))
    with st.container(key="preview_bar"):
        who = "a student with full access" if user["username"] == "preview" else user["name"]
        st.markdown(f'<div class="preview-text"><b>Previewing as {theme.esc(who)}</b> (access to {n} lecture{"s" if n != 1 else ""}). '
                    "You are seeing exactly what they see.</div>", unsafe_allow_html=True)
        st.page_link(nav.PAGES["dashboard"], label="Exit preview", icon=":material/close:")


def page(user, real_user=None):
    """The student view for `user` (role student). A professor previewing passes the student's record and real_user=themself:
    everything (grants, audience, what the answer shows) is then exactly the student's."""
    assert user["role"] == "student"
    state.init()
    theme.set_title({"guide": "Guide", "quiz": "Quiz"}.get(st.session_state.mode, "Ask the lab"))
    sidebar(user, real_user)
    if st.session_state.mode == "qa":
        chat_dialogs(user, real_user)
    if real_user and real_user["role"] == "professor":
        preview_bar(user)
    if st.session_state.mode == "guide":
        guide_ui.guide_view(user, real_user)
    elif st.session_state.mode == "quiz":
        quiz_ui.quiz_view(user, real_user)
    else:
        qa_view(user, real_user)
