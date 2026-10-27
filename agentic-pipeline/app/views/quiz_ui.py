"""Quiz screens: set up, build (every question must pass every check), take one question at a time, review, submit, results.

A thin layer over src/quiz/service.py. What this file never does: hold or show a key, an explanation or a source before the whole quiz is
submitted. The screen keeps only the quiz id; every render asks the service for the OPEN quiz's public view (no key), and `results` is
called only for a submitted quiz.
"""
import re
import time

import streamlit as st

from app import nav, state, theme
from app.data import get_runtime
from src.ingest import guides as guide_files
from src.quiz import service as qs
from src.quiz.store import LENGTHS, QuizError, QuizStore

TOPIC_MAX = 80
BUILD_HELP = ("Every question is checked before the quiz starts: its answer and explanations must be supported by real passages, and two "
              "different AI models must each reach the same answer on their own. Questions that pass are saved, so building the same quiz again "
              "reuses them and only prepares what is missing. A quiz starts only when every question has passed.")
REASON_TITLE = {"insufficient_evidence": "Not enough source text", "rejected": "Some drafts did not pass the checks", "gateway": "The AI service had a problem", "quota": "The AI budget is used up"}


def owner_of(user, real_user):
    """A professor previewing keeps preview quizzes under their own name, never under the student's."""
    if real_user and real_user["role"] == "professor":
        return f"preview:{real_user['username']}"
    return user["username"]


def access(user):
    from app.views.student import accessible_lectures
    return accessible_lectures(user)


def options_for(user):
    """[(label, key)]: the lectures and the guides this user may open. key is what the quiz uses (lecture title or 'Dissection Guide, Class N')."""
    granted = set(access(user))
    from app.data import lectures
    out = [(l["title"], l["title"]) for l in lectures() if l["title"] in granted]
    out += [(name, label) for label, name in guide_files.guide_labels() if label in granted]
    return out


def set_stage(stage, qid=None):
    st.session_state.qz_stage = stage
    if qid is not None:
        st.session_state.qz_id = qid


def leave():
    for k in ("qz_stage", "qz_id", "qz_offer", "qz_error", "qz_busy"):
        st.session_state.pop(k, None)


def esc(text):
    return theme.esc(text or "")


def md_safe(text):
    return (text or "").replace("$", "\\$")


def highlight(text, spans):
    """The passage as HTML with each supporting span marked (whitespace/case-insensitive). Overlapping or repeated spans become one mark; a
    span that cannot be placed is simply not marked."""
    ranges = []
    for sp in spans:
        raw = sp.get("span") or ""
        pieces = [raw] if "\n" not in raw.strip() else [re.sub(r"^\s*(?:[-*\u2022o]\s+)+", "", ln) for ln in raw.splitlines()]      # an outline path: mark each of its lines
        for piece in pieces:
            words = [re.escape(w) for w in piece.split()]
            if len(words) < (3 if len(pieces) == 1 else 1):
                continue
            m = re.search(r"\s+".join(words), text, flags=re.I)
            if m:
                ranges.append([m.start(), m.end()])
    ranges.sort()
    merged = []
    for a_, b_ in ranges:
        if merged and a_ <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b_)
        else:
            merged.append([a_, b_])
    out, pos = [], 0
    for a_, b_ in merged:
        out += [theme.esc(text[pos:a_]), '<mark class="qz-span">', theme.esc(text[a_:b_]), "</mark>"]
        pos = b_
    out.append(theme.esc(text[pos:]))
    return "".join(out)


# ----------------------------------------------------------------------------
# set up and build
# ----------------------------------------------------------------------------

def build_request(user):
    st.markdown('<div class="ghead"><span class="gname">Quiz</span><span class="gpos">Practice questions from your course material</span></div>', unsafe_allow_html=True)
    busy = bool(st.session_state.get("qz_busy"))
    kind = st.radio("What do you want to be quizzed on?", ["My lectures and guides", "A topic"], horizontal=True, key="qz_kind", disabled=busy)
    request = {"mode": "materials" if kind == "My lectures and guides" else "topic"}
    if request["mode"] == "materials":
        opts = options_for(user)
        if not opts:
            st.markdown('<div class="gwelcome"><p><b>No lectures or guides are open to you yet.</b></p><p class="small">Ask your instructor to open some. '
                        'You can still quiz yourself on a topic from the OpenStax reference text.</p></div>', unsafe_allow_html=True)
        names = dict(opts)
        picked = st.multiselect("Lectures and guides", list(names), key="qz_pick", placeholder="Choose one or more", disabled=busy or not opts)
        request["selected"] = [names[p] for p in picked]
    else:
        request["topic"] = st.text_input("Anatomy topic", max_chars=TOPIC_MAX, key="qz_topic", placeholder="For example: rotator cuff muscles", disabled=busy)
    length = st.segmented_control("Number of questions", list(LENGTHS), default=5, key="qz_len", disabled=busy)
    request["n"] = length or 5
    request["reviewed_only"] = st.checkbox("Only questions approved by the instructor", key="qz_reviewed", disabled=busy,
                                           help="Questions are approved one by one. If too few match, no quiz is built: unapproved questions are never added.")
    theme.meta(BUILD_HELP)
    return request


def start_build(request):
    st.session_state.qz_busy = request


def do_build(user, real_user, request):
    rt = get_runtime()
    status = st.status("Preparing your quiz…", expanded=True)
    status.write("Looking for saved questions that were already checked against your current sources")

    def progress(have, wanted, note=""):
        status.write((f"{note}. " if note else "") + f"{have} of {wanted} questions ready")
    try:
        out = qs.new_quiz(owner_of(user, real_user), access(user), request, rt, progress=progress)
    except QuizError as exc:
        out = {"status": "failed", "reason": "", "message": str(exc), "quiz_id": None, "have": 0, "requested": request["n"], "reused": 0, "generated": 0}
    except Exception:
        out = {"status": "failed", "reason": "gateway", "message": "Quiz preparation hit an unexpected problem. Nothing is wrong with your material. Try again.",
               "quiz_id": None, "have": 0, "requested": request["n"], "reused": 0, "generated": 0}
    done = out["status"] == "ready"
    note = f" ({out['reused']} reused, {out['generated']} new)" if out.get("reused") or out.get("generated") else ""
    status.update(label=("Quiz ready" if done else "Quiz not started") + note, state="complete" if done else "error", expanded=False)
    st.session_state.qz_busy = None
    st.session_state.qz_last = request
    if done:
        st.session_state.qz_error = None
        set_stage("take", out["quiz_id"])
        QuizStore().goto(owner_of(user, real_user), out["quiz_id"], 0)
    elif out["status"] == "offer":
        st.session_state.qz_error = None
        st.session_state.qz_offer = out
    else:
        st.session_state.qz_error = out
    st.rerun()


def resume_cards(owner):
    store = QuizStore()
    latest = store.latest(owner, ("open", "offer"))
    if latest is None:
        return False
    if latest["status"] == "offer":
        offer_card(owner, latest["id"], f"Only {latest['length']} questions passed every check.")
        return True
    answered = sum(1 for v in latest["selections"].values() if v)
    st.markdown(f'<div class="gwelcome"><p><b>You have a quiz in progress.</b></p><p class="small">{latest["length"]} questions, '
                f'{answered} answered, you were on question {latest["current"] + 1}.</p></div>', unsafe_allow_html=True)
    with theme.button_row("qz_resume_row"):
        st.button("Resume quiz", key="qz_resume", type="primary", on_click=set_stage, args=("take", latest["id"]))
        with st.popover("Discard"):
            st.markdown("This deletes the unfinished quiz and your saved answers.")
            st.button("Yes, discard", key="qz_discard", on_click=lambda: (store.delete_quiz(owner, latest["id"])))
    return True


def offer_card(owner, qid, why):
    st.markdown(f'<div class="gwelcome"><p><b>A 10-question quiz is not ready yet.</b></p><p class="small">{esc(why)} '
                'Questions are never added unless they pass every check. The ones that passed are saved.</p></div>', unsafe_allow_html=True)
    with theme.button_row("qz_offer_row"):
        st.button("Start with 5 questions", key="qz_accept", type="primary", on_click=accept, args=(owner, qid))
        st.button("Continue preparing 10", key="qz_continue_offer", on_click=continue_from_offer, args=(owner, qid))
        st.button("Discard", key="qz_decline", on_click=decline, args=(owner, qid))


def accept(owner, qid):
    qs.accept_offer(owner, qid)
    st.session_state.qz_offer = None
    set_stage("take", qid)


def decline(owner, qid):
    qs.decline_offer(owner, qid)
    st.session_state.qz_offer = None


def continue_from_offer(owner, qid):
    """Drop the 5-question offer and look only for the missing questions (the saved ones are reused)."""
    qs.decline_offer(owner, qid)
    st.session_state.qz_offer = None
    if st.session_state.get("qz_last"):
        start_build(st.session_state.qz_last)


def continue_preparing():
    if st.session_state.get("qz_last"):
        st.session_state.qz_error = None
        start_build(st.session_state.qz_last)


def past_results(owner):
    rows = QuizStore().list_quizzes(owner, "submitted", 5)
    if rows:
        theme.label("Earlier quizzes")
        for q in rows:
            when = time.strftime("%d %b %Y", time.localtime(q["submitted"] or q["updated"]))
            st.button(f"{when}: {q['score']} of {q['length']}", key=f"qz_past_{q['id']}", on_click=set_stage, args=("results", q["id"]))


def setup_view(user, real_user):
    owner = owner_of(user, real_user)
    if st.session_state.get("qz_busy"):
        request = st.session_state.qz_busy
        build_request(user)
        do_build(user, real_user, request)
        return
    has_open = resume_cards(owner)
    if offer := st.session_state.get("qz_offer"):
        if not has_open:
            offer_card(owner, offer["quiz_id"], offer["message"])
    request = build_request(user)
    ready = (request["mode"] == "materials" and request.get("selected")) or (request["mode"] == "topic" and len((request.get("topic") or "").strip()) >= 3)
    if err := st.session_state.get("qz_error"):
        err = err if isinstance(err, dict) else {"message": str(err), "reason": "", "have": 0}
        theme.alert("warning", "No quiz was started", err["message"])
        if err.get("have"):
            theme.meta(f'{err["have"]} of {err.get("requested", request["n"])} questions are saved for this request ({err.get("reused", 0)} reused, {err.get("generated", 0)} new).')
        if err.get("reason") in ("rejected", "gateway", "quota"):
            st.button("Continue preparing", key="qz_continue", on_click=continue_preparing, help="Looks only for the questions still missing; saved ones are reused")
    st.button("Build quiz", key="qz_build", type="primary", disabled=not ready, on_click=start_build, args=(request,))
    past_results(owner)


# ----------------------------------------------------------------------------
# taking the quiz
# ----------------------------------------------------------------------------

def save_choice(owner, qid, index, key):
    choice = st.session_state.get(key)
    try:
        QuizStore().select(owner, qid, index, [choice] if choice else [])
    except QuizError:
        pass


def go_to(owner, qid, index):
    try:
        QuizStore().goto(owner, qid, index)
    except QuizError:
        pass
    st.session_state.qz_stage = "take"


def take_view(user, real_user):
    owner, qid = owner_of(user, real_user), st.session_state.qz_id
    try:
        view = qs.open_view(owner, qid, access(user), get_runtime().searcher.note_lectures)
    except QuizError as exc:
        theme.alert("warning", "This quiz cannot be opened", str(exc))
        st.button("Back to Quiz", key="qz_back_setup", on_click=leave)
        return
    n, cur = view["length"], min(view["current"], view["length"] - 1)
    q = view["questions"][cur]
    st.markdown(f'<div class="ghead"><span class="gname">Quiz</span><span class="gpos">Question {cur + 1} of {n} · {view["answered"]} answered</span></div>',
                unsafe_allow_html=True)
    st.progress((cur + 1) / n)
    saved = (view["selections"].get(cur) or [None])[0]
    ids = [o["id"] for o in q["options"]]
    texts = {o["id"]: o["text"] for o in q["options"]}
    if q["stem"]:
        st.markdown(f'<div class="qz-stem">{esc(q["stem"])}</div>', unsafe_allow_html=True)
    key = f"qz_opt_{qid}_{cur}"
    start = None if key in st.session_state else (ids.index(saved) if saved in ids else None)      # the saved answer seeds the widget once
    st.radio(q["lead_in"], ids, index=start, format_func=lambda i: f"{i}.  {md_safe(texts[i])}", key=key,
             on_change=save_choice, args=(owner, qid, cur, key))
    with theme.button_row("qz_nav"):
        st.button("Back", key="qz_prev", on_click=go_to, args=(owner, qid, cur - 1), disabled=cur == 0, icon=":material/arrow_back:")
        if cur < n - 1:
            st.button("Next", key="qz_next", on_click=go_to, args=(owner, qid, cur + 1), type="primary", icon=":material/arrow_forward:", icon_position="right")
        else:
            st.button("Review answers", key="qz_review", on_click=set_stage, args=("review",), type="primary")
    with st.expander("Jump to a question"):
        with theme.button_row("qz_jump"):
            for i in range(n):
                done = bool(view["selections"].get(i))
                st.button(f"{i + 1}{' ✓' if done else ''}", key=f"qz_j_{i}", on_click=go_to, args=(owner, qid, i), help="answered" if done else "not answered yet")
    theme.meta("Your answers are saved as you go. Nothing is marked until you submit the whole quiz.")
    st.markdown('<div class="chat-end"></div>', unsafe_allow_html=True)


def review_view(user, real_user):
    owner, qid = owner_of(user, real_user), st.session_state.qz_id
    try:
        view = qs.open_view(owner, qid, access(user), get_runtime().searcher.note_lectures)
    except QuizError as exc:
        theme.alert("warning", "This quiz cannot be opened", str(exc))
        st.button("Back to Quiz", key="qz_back_setup2", on_click=leave)
        return
    n = view["length"]
    st.markdown('<div class="ghead"><span class="gname">Review your answers</span><span class="gpos">Nothing is marked yet</span></div>', unsafe_allow_html=True)
    blank = 0
    for i, q in enumerate(view["questions"]):
        sel = (view["selections"].get(i) or [None])[0]
        texts = {o["id"]: o["text"] for o in q["options"]}
        blank += sel is None
        mine = f"{sel}.  {esc(texts[sel])}" if sel else "<i>Not answered</i>"
        st.markdown(f'<div class="qz-row"><div class="qz-q"><b>{i + 1}.</b> {esc(q["lead_in"])}</div><div class="qz-a">Your answer: {mine}</div></div>', unsafe_allow_html=True)
        st.button("Change", key=f"qz_chg_{i}", on_click=go_to, args=(owner, qid, i))
    if blank:
        theme.alert("warning", f"{blank} question{'s are' if blank > 1 else ' is'} not answered", "Unanswered questions count as wrong.")
    with theme.button_row("qz_submit_row"):
        with st.popover("Submit quiz", help="Marks the whole quiz"):
            st.markdown("**Submit the quiz?** You cannot change your answers afterwards.")
            st.button("Yes, submit", key="qz_submit", type="primary", on_click=submit, args=(owner, qid, user))
        st.button("Back to questions", key="qz_back_q", on_click=set_stage, args=("take",))


def submit(owner, qid, user):
    try:
        qs.submit(owner, qid, access(user), get_runtime().searcher.note_lectures)
        set_stage("results", qid)
    except QuizError as exc:
        st.session_state.qz_error = str(exc)


# ----------------------------------------------------------------------------
# results (only for a submitted quiz)
# ----------------------------------------------------------------------------

def results_view(user, real_user):
    owner, qid = owner_of(user, real_user), st.session_state.qz_id
    try:
        res = qs.results(owner, qid, access(user), get_runtime().searcher.note_lectures)
    except QuizError as exc:
        theme.alert("warning", "Results are not available", str(exc))
        st.button("Back to Quiz", key="qz_back_setup3", on_click=leave)
        return
    st.markdown(f'<div class="ghead"><span class="gname">You scored {res["score"]} of {res["length"]}</span></div>', unsafe_allow_html=True)
    theme.meta("This is a practice quiz. Questions are checked by AI against the sources and are not approved by Dr. Inglis unless a question says so.")
    for q in res["questions"]:
        st.markdown(f'<div class="qz-res-h"><b>Question {q["n"]}</b> · <span class="qz-{"ok" if q["correct"] else "no"}">{"Correct" if q["correct"] else "Not correct"}</span></div>',
                    unsafe_allow_html=True)
        if q["stem"]:
            st.markdown(f'<div class="qz-stem">{esc(q["stem"])}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="qz-lead">{esc(q["lead_in"])}</div>', unsafe_allow_html=True)
        rows = []
        for o in q["options"]:
            tags = []
            if o["id"] in q["selected"]:
                tags.append("Your answer")
            if o["id"] in q["answer_ids"]:
                tags.append("Correct answer")
            tag = f' <span class="qz-tag">{" · ".join(tags)}</span>' if tags else ""
            cls = "qz-opt-right" if o["id"] in q["answer_ids"] else ""
            rows.append(f'<li class="{cls}"><b>{o["id"]}.</b> {esc(o["text"])}{tag}</li>')
        if not q["selected"]:
            rows.append('<li class="qz-blank"><i>You did not answer this question.</i></li>')
        st.markdown(f'<ul class="qz-opts">{"".join(rows)}</ul>', unsafe_allow_html=True)
        st.markdown(f'**Why it is correct.** {md_safe(q["explanation"])}')
        wrong = "".join(f'<li><b>{i}.</b> {esc(w)}</li>' for i, w in sorted(q["alternatives"].items()))
        st.markdown(f'<div class="label">Why the others are not</div><ul class="qz-why">{wrong}</ul>', unsafe_allow_html=True)
        spans = q["spans"]["key"] + q["spans"]["explanation"] + [x for sup in q["spans"]["alternatives"].values() for x in sup]
        with st.expander(f"Supporting passages ({len(q['evidence'])})"):
            for e in q["evidence"]:
                link = f' · <a href="{esc(e["url"])}" target="_blank" rel="noopener noreferrer">open source</a>' if e["url"] else ""
                lic = f' · {esc(e["license"])}' if e.get("license") else ""
                body = (f'<div class="qz-pass">{highlight(e["text"], [s for s in spans if s["source_id"] == e["id"]])}</div>' if e["visible"]
                        else '<div class="small">This source is no longer open to you.</div>')
                st.markdown(f'<div class="qz-src"><b>{esc(e["label"])}</b> <span class="small">({esc(e["tier"])}{lic}){link}</span>{body}</div>', unsafe_allow_html=True)
        theme.meta(q["label"])
    st.button("New quiz", key="qz_new", type="primary", on_click=leave)


# ----------------------------------------------------------------------------

def quiz_view(user, real_user=None):
    stage = st.session_state.get("qz_stage", "setup")
    if stage == "take" and st.session_state.get("qz_id"):
        take_view(user, real_user)
    elif stage == "review" and st.session_state.get("qz_id"):
        review_view(user, real_user)
    elif stage == "results" and st.session_state.get("qz_id"):
        results_view(user, real_user)
    else:
        setup_view(user, real_user)
