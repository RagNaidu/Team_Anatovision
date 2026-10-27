"""Professor dashboard: review queue, verified fixes, notes library, access, usage, settings. Professor role only."""
import functools
from pathlib import Path

import streamlit as st

import pandas as pd

from app import nav, state, theme
from app.data import get_runtime, lectures
from app.views import blocked, quiz_review
from src import auth, llm, notes_upload, reports, review, usage as usage_log
from src.ingest import guides

PER_PAGE = 10
TAB_LABELS = {"start_here": "Start here", "likely_factual": "Likely facts", "second_look": "Second look", "typo": "Typos"}
DECISION_WORDS = {"confirm_error": "Confirmed as an error", "notes_correct": "Notes are correct", "reword": "Reworded"}


def is_professor(user=None):
    """Checked against the account file on every call (not against what the caller passed in)."""
    me = nav.current_user()
    return bool(me and me.get("role") == "professor" and (user is None or user.get("role") == "professor"))


def instructors_only(fn):
    """Every professor view starts with this check, on the server side of the view itself: a student (or nobody) gets the
    'That page is for instructors' page and the view's own code never runs."""
    @functools.wraps(fn)
    def checked(*args, **kwargs):
        user = next((a for a in args if isinstance(a, dict) and "role" in a), None)
        if not is_professor(user):
            blocked.show()
            st.stop()
        return fn(*args, **kwargs)
    return checked


def require_professor(user):
    if not is_professor(user):
        blocked.show()
        st.stop()


# ----------------------------------------------------------------------------
# review queue
# ----------------------------------------------------------------------------

TAB_HELP = {
    "start_here": "The most likely real errors, best evidence first. Start here.",
    "likely_factual": "Lines the second check agreed are probably wrong. Until you decide, students see a neutral “being reviewed” note instead of the line.",
    "second_look": "Wording that could be clearer, or facts the second check doubted. Students still see the line, with a “check before relying” note.",
    "typo": "Spelling and typing slips. They do not change what a student reads.",
}
FILTER_SEVERITY = {"All": "Any", "high": "High", "medium": "Medium", "low": "Low"}
FILTER_KIND = {"All": "Any kind", "factual": "A fact", "wording": "Wording", "typo": "A typo"}
FILTER_STATUS = {"Open": "Still open", "Decided": "Already decided", "All": "Both"}
PAGE_SIZES = (10, 25, 50)


def item_card(item):
    """One clear card: the line, why it was flagged, a compact meta row. Details live behind 'Show details'."""
    d = item["decision"]
    parts = [f'<div class="crumb">{theme.esc(item["breadcrumb"])}</div>',
             f'<div class="quote">“{theme.esc(item["claim_quote"])}”</div>',
             f'<div class="why"><b>Why it was flagged.</b> {theme.esc(item["issue"])}</div>']
    if item.get("what_references_say"):
        parts.append(f'<div class="why"><b>What the reference says.</b> {theme.esc(item["what_references_say"])}</div>')
    chips = [theme.badge_html("uploaded", FILTER_KIND.get(item["type"], item["type"]).replace("Any kind", item["type"])),
             theme.badge_html("uploaded", f'{item["severity"].capitalize()} severity')]
    if d.get("seen_in_question"):
        chips.append(theme.chip_html("doubtful", "Shown in student answers"))          # emphasised: students may be reading it now
    if d["status"] == "resolved":
        chips.append(theme.badge_html("verified", f'{DECISION_WORDS.get(d["decision"], d["decision"])} · {d["by"]}, {d["date"]}'))
    parts.append(f'<div class="metarow">{" ".join(chips)}</div>')
    return "".join(parts)


def item_details(item):
    second = item.get("verification", {}).get("verdict")
    rows = [("Basis", item["basis_text"]), ("Confidence", f'{item["confidence"]:.2f}'), ("Kind", item["type"])]
    if second:
        rows.append(("Second check", second))
    html_ = "".join(f'<div class="kv"><b>{theme.esc(k)}.</b> {theme.esc(v)}</div>' for k, v in rows)
    reason = item.get("verification", {}).get("reason")
    if reason:
        html_ += f'<div class="kv"><b>Second check said.</b> {theme.esc(reason)}</div>'
    return html_ + '<div class="kv">An AI-generated suggestion, not a verdict.</div>'


def toast(text, error=False):
    st.toast(text, icon=":material/error:" if error else ":material/check_circle:", duration=6 if error else 5)


def decision_form(item, user, scope):
    i = f'{scope}_{item["idx"]}'
    with st.expander("Decide", key=f"dx_{i}", on_change="rerun"):          # stateful: it stays open where you left it
        with st.form(f"decide_{i}", border=False):
            # Ctrl/Cmd+Enter in the box submits the FIRST submit button of the form. That one is a hidden no-op, so the
            # shortcut can never record a decision; only a deliberate click on one of the three visible buttons does.
            st.form_submit_button("noop", key=f"noop_{i}")
            by = st.text_input("Your name (recorded as the person who verified it)", value=user["name"], key=f"by_{i}")
            correction = st.text_area("Corrected wording (required to confirm an error or to reword)", key=f"corr_{i}", height=96)
            places = review.same_quote_places(item)
            apply_all = st.checkbox(f"Also apply to the {len(places)} other place(s) with this exact line", key=f"all_{i}") if places else False
            choice = None
            with theme.button_row(f"decide_row_{i}"):        # the three look different by role: confirm = primary, the others secondary
                if st.form_submit_button("Confirm error", type="primary", key=f"ok_{i}"):
                    choice = "confirm_error"
                if st.form_submit_button("Notes are correct", key=f"fine_{i}"):
                    choice = "notes_correct"
                if st.form_submit_button("Reword", key=f"reword_{i}"):
                    choice = "reword"
            theme.meta("Confirm error: this will show the corrected line to students. Notes are correct: the line stays as written.")
        if choice:
            try:
                new = review.decide(item, choice, correction, by, apply_all)
            except ValueError as exc:
                toast(str(exc), error=True)
            else:
                st.session_state.rq_flash = f"Recorded: {DECISION_WORDS[choice]} ({len(new)} verified fix(es) written)."
                st.rerun()                                         # the decided item leaves the open list on its own


def set_page(name, value):
    st.session_state[f"rq_pg_{name}"] = value


def pager(name, total):
    """'Page 1 of N' with previous/next and a page-size selector. -> (start, end) of the rows to show."""
    size = st.session_state.get(f"rq_ps_{name}", PAGE_SIZES[0])
    pages = max(1, -(-total // size))
    page = min(max(1, st.session_state.get(f"rq_pg_{name}", 1)), pages)
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key=f"pager_{name}"):
        st.button("Previous", key=f"rq_prev_{name}", on_click=set_page, args=(name, page - 1), disabled=page <= 1, icon=":material/chevron_left:")
        st.markdown(f'<div class="pager-text">Page {page} of {pages}</div>', unsafe_allow_html=True)
        st.button("Next", key=f"rq_next_{name}", on_click=set_page, args=(name, page + 1), disabled=page >= pages,
                  icon=":material/chevron_right:", icon_position="right")
        st.selectbox("Items per page", PAGE_SIZES, key=f"rq_ps_{name}", on_change=set_page, args=(name, 1))
    return (page - 1) * size, page * size


def bulk_typos(items, lecture, user):
    """The one bulk action, for typos only: 'Mark all typos in this lecture as reviewed', behind a confirmation with the count."""
    todo = review.bulk_typo_items(items, lecture) if lecture != "All" else []
    if lecture == "All":
        theme.meta("Choose one lecture in the filter above to mark its typos as reviewed in one go.")
        return
    if not todo:
        theme.meta("No open typos in this lecture.")
        return
    key = f"bulk_{lecture}"
    if st.session_state.get(key):
        theme.alert("warning", f"Mark {len(todo)} typos as reviewed?",
                    f"This records “the notes are correct as written” for {len(todo)} typo item(s) in {lecture}. "
                    "It changes nothing students read. Facts and wording items are never touched.")
        with theme.button_row(f"bulk_row_{lecture}"):
            if st.button(f"Yes, mark {len(todo)} as reviewed", key=f"bulk_yes_{lecture}", type="primary"):
                n = review.mark_typos_reviewed(items, lecture, user["name"])
                st.session_state[key] = False
                st.session_state.rq_flash = f"Marked {n} typo item(s) in {lecture} as reviewed."
                st.rerun()
            if st.button("Cancel", key=f"bulk_no_{lecture}"):
                st.session_state[key] = False
                st.rerun()
    elif st.button(f"Mark all {len(todo)} typos in this lecture as reviewed", key=f"bulk_ask_{lecture}"):
        st.session_state[key] = True
        st.rerun()


@instructors_only
def review_queue(user):
    theme.section("Review queue")
    theme.meta("Every item is an AI-generated suggestion, not a verdict. Deciding records a verified fix that students see in place "
               "of the line. The notes files themselves are never edited.")
    if msg := st.session_state.pop("rq_flash", None):
        toast(msg)
    report = review.load_report()
    items = review.queue(report)
    if not items:
        theme.alert("info", "No fact-check report yet", "Ask the developer to run the fact-check over the notes.")
        return
    theme.meta(f'Fact-check of {report["sections_checked"]} sections, {report["date"]}.')
    lectures = sorted({i["lecture"] for i in items})
    f1, f2, f3, f4 = st.columns(4)
    lecture = f1.selectbox("Lecture", ["All"] + lectures, key="rq_lecture")
    severity = f2.selectbox("How serious", list(FILTER_SEVERITY), format_func=FILTER_SEVERITY.get, key="rq_sev")
    kind = f3.selectbox("Kind of issue", list(FILTER_KIND), format_func=FILTER_KIND.get, key="rq_type")
    status = f4.selectbox("Show", list(FILTER_STATUS), format_func=FILTER_STATUS.get, key="rq_status")

    def keep(i):
        return ((lecture == "All" or i["lecture"] == lecture) and (severity == "All" or i["severity"] == severity)
                and (kind == "All" or i["type"] == kind)
                and (status == "All" or (status == "Open") == (i["decision"]["status"] != "resolved")))

    tabs = review.TABS
    contents = {t: [i for i in review.tab_items(items, t) if keep(i)] for t in tabs}
    reports_n = len(review.open_student_reports()) + len(review.open_conflicts())
    names = [f'{TAB_LABELS[t]} ({len(contents[t])})' for t in tabs] + [f"Student reports ({reports_n})"]
    for tab, name in zip(st.tabs(names), tabs + ("flags",)):
        with tab:
            if name == "flags":
                student_reports()
                continue
            theme.meta(TAB_HELP[name])
            rows = contents[name]
            if name == "typo":
                bulk_typos(items, lecture, user)
            if not rows:
                theme.meta("Nothing here with these filters.")
                continue
            lo, hi = pager(name, len(rows))
            for item in rows[lo:hi]:
                with st.container(key=f"rqcard_{name}_{item['idx']}"):
                    st.markdown(item_card(item), unsafe_allow_html=True)
                    with st.expander("Show details", key=f"dt_{name}_{item['idx']}"):
                        st.markdown(item_details(item), unsafe_allow_html=True)
                    if item["decision"]["status"] != "resolved":
                        decision_form(item, user, name)


def student_reports():
    theme.meta("Errors students reported with “Report an error”, and places where the notes and the textbook disagree. "
               "A report does not change any answer by itself: use the Review queue or the notes to fix the cause.")
    reports_ = review.open_student_reports()
    conflicts = review.open_conflicts()
    if not reports_ and not conflicts:
        theme.meta("Nothing reported yet.")
        return
    for n, f in reports_:
        with st.container(key=f"report_{n}"):
            st.markdown(f'<div class="crumb">{theme.esc(f.get("ts", "")[:16].replace("T", " "))} · {theme.esc(f.get("student", ""))}</div>'
                        f'<div class="why"><b>{theme.esc(f.get("reason", ""))}</b></div>'
                        + (f'<div class="quote">“{theme.esc(f["comment"])}”</div>' if f.get("comment") else "")
                        + f'<div class="why"><b>Question.</b> {theme.esc(f.get("question", ""))}</div>', unsafe_allow_html=True)
            with st.expander("The answer the student saw", key=f"rpa_{n}"):
                st.markdown(f'<div class="kv">{theme.esc(f.get("answer", ""))}</div>'
                            f'<div class="kv"><b>Cited.</b> {theme.esc("; ".join(f.get("cites", [])) or "nothing")}</div>', unsafe_allow_html=True)
            if st.button("Mark as handled", key=f"rp_done_{n}"):
                review.close_report(n)
                st.session_state.rq_flash = "Report marked as handled."
                st.rerun()
    for n, f in conflicts:
        st.markdown(f'<div class="label">Notes versus textbook · {theme.esc(f.get("topic", ""))}</div>'
                    f'<div class="kv"><b>Notes say.</b> {theme.esc(f.get("notes_say", ""))} ({theme.esc(f.get("notes_cite", ""))})</div>'
                    f'<div class="kv"><b>OpenStax says.</b> {theme.esc(f.get("openstax_say", ""))} ({theme.esc(f.get("openstax_cite", ""))})</div>',
                    unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# verified fixes ledger
# ----------------------------------------------------------------------------

def ask_undo(fix_id):
    if is_professor():
        st.session_state.undo_pending = fix_id


def cancel_undo():
    st.session_state.undo_pending = None


def undo_fix(fix_id):
    if not is_professor():                    # runs as a button callback: refuse quietly, do nothing
        return
    n = review.undo(fix_id)
    st.session_state.undo_pending = None
    st.session_state.rq_flash = f"Removed {fix_id}; reopened {n} flag(s)."


@instructors_only
def ledger_tab():
    fixes = review.ledger()
    theme.section("Verified fixes")
    theme.meta("Dr. Inglis’s decisions. A fix is what students see in place of the original line. Undo removes it and reopens the flag.")
    if msg := st.session_state.pop("rq_flash", None):
        toast(msg)
    if not fixes:
        theme.meta("No verified fixes yet.")
    for f in fixes:
        with st.container(key=f"fixcard_{f['id']}"):
            after = f["correction"] or "(the line was confirmed as written)"
            st.markdown(f'<div class="label">{theme.esc(f["id"])} · {theme.esc(DECISION_WORDS.get(f["decision"], f["decision"]))}</div>'
                        f'<div class="crumb">{theme.esc(f["breadcrumb"])}</div>'
                        f'<div class="beforeafter"><div><div class="stat-label">Before (the notes)</div><div class="quote">“{theme.esc(f["notes_quote"])}”</div></div>'
                        f'<div><div class="stat-label">After (what students see)</div><div class="quote">“{theme.esc(after)}”</div></div></div>'
                        f'<div class="kv">Decided by {theme.esc(f["by"])} on {theme.esc(f["date"])}</div>', unsafe_allow_html=True)
            if st.session_state.get("undo_pending") == f["id"]:
                theme.alert("warning", f"Undo {f['id']}?", "The fix is removed, students see the original line again, and the flag reopens.")
                with theme.button_row(f"undo_row_{f['id']}"):
                    st.button("Yes, undo it", key=f"undo_yes_{f['id']}", on_click=undo_fix, args=(f["id"],), type="primary")
                    st.button("Keep it", key=f"undo_no_{f['id']}", on_click=cancel_undo)
            else:
                st.button("Undo", key=f"undo_{f['id']}", on_click=ask_undo, args=(f["id"],))


# ----------------------------------------------------------------------------
# access control
# ----------------------------------------------------------------------------

def access_label(l, files):
    """The lecture title; if two files share a title (or the file name adds information) a short unique suffix is added."""
    same = [x for x in files if x["title"] == l["title"]]
    base = l.get("display", l["title"])
    if len(same) > 1:
        base += f' · {l["lecture_id"][-6:]}'
    return base


def ask_access(username, what):
    if is_professor():
        st.session_state[f"acc_confirm_{username}"] = what


@instructors_only
def access_tab():
    theme.section("Access")
    theme.meta("Tick the lectures each student may use. A new student starts with none. This is enforced in the search itself: "
               "notes from other lectures never reach the model. A dissection guide opens for a student who may use the lecture it is matched to, "
               "or who is given the guide itself here (\"Dissection Guide, Class N\"); a guide matched to no lecture opens only that way, or for a student who may use every lecture. "
               "\"Grant all\" gives a student every lecture and every guide. The OpenStax textbook stays open to everyone, labelled as not course notes.")
    if msg := st.session_state.pop("acc_flash", None):
        toast(msg)
    files = lectures() + [{"title": t, "lecture_id": "guide-" + "".join(ch if ch.isalnum() else "-" for ch in t.lower()), "file": "",
                           "display": f"{t}: {name.split(': ', 1)[-1]}"}
                          for t, name in guides.guide_labels()]          # every dissection guide can be granted on its own
    noun = "lectures and dissection guides" if len(files) > len(lectures()) else "lectures"
    for username, rec in auth.students():
        granted = set(rec["allowed_lectures"])
        with st.expander(f'{rec["name"]} ({username}): {len(granted & {l["title"] for l in files})} of {len(files)} {noun}'):
            with st.form(f"access_{username}", border=False):
                cols = st.columns(2)
                picks = {l["title"]: cols[i % 2].checkbox(access_label(l, files), value=l["title"] in granted,
                                                          key=f"acc_{username}_{l['lecture_id']}")
                         for i, l in enumerate(files)}
                with theme.button_row(f"accrow_{username}"):
                    save = st.form_submit_button("Save access", type="primary")
                    all_ = st.form_submit_button("Grant all")
                    none = st.form_submit_button("Revoke all", key=f"danger_revoke_{username}")
            if save:
                chosen = [t for t, v in picks.items() if v]
                auth.set_allowed_lectures(username, chosen)
                st.session_state.acc_flash = f"{rec['name']}: access saved ({len(chosen)} lectures)."
                for l in files:                              # let the checkboxes show the saved state
                    st.session_state.pop(f"acc_{username}_{l['lecture_id']}", None)
                st.rerun()
            if all_ or none:
                ask_access(username, "all" if all_ else "none")
                st.rerun()
            what = st.session_state.get(f"acc_confirm_{username}")
            if what:
                n = len(files) if what == "all" else len(granted)
                changed = len(files) - len(granted) if what == "all" else len(granted)
                theme.alert("warning", ("Grant access to every lecture?" if what == "all" else "Remove access to every lecture?"),
                            f"{rec['name']} {'gets' if what == 'all' else 'loses'} {changed} lecture(s) "
                            f"({len(files)} lectures in total, {len(granted)} allowed now).")
                with theme.button_row(f"acc_confirm_row_{username}"):
                    if st.button("Yes, " + ("grant all" if what == "all" else "revoke all"), key=f"acc_yes_{username}", type="primary"):
                        auth.set_allowed_lectures(username, [l["title"] for l in files] if what == "all" else [])
                        st.session_state[f"acc_confirm_{username}"] = None
                        for l in files:
                            st.session_state.pop(f"acc_{username}_{l['lecture_id']}", None)
                        st.session_state.acc_flash = f"{rec['name']}: access {'granted to all' if what == 'all' else 'revoked for all'} lectures."
                        st.rerun()
                    if st.button("Cancel", key=f"acc_no_{username}"):
                        st.session_state[f"acc_confirm_{username}"] = None
                        st.rerun()
    rules = " ".join(auth.PASSWORD_RULES)
    st.markdown('<div class="label">Add a student</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="small">Password rules: {theme.esc(rules)}</div>', unsafe_allow_html=True)
    with st.form("add_student", border=False, clear_on_submit=False):
        c1, c2 = st.columns(2)
        username, name = c1.text_input("Username"), c2.text_input("Name")
        c3, c4 = st.columns(2)
        pw, pw2 = c3.text_input("Password", type="password"), c4.text_input("Confirm password", type="password")
        if st.form_submit_button("Add student", type="primary"):
            try:
                auth.add_student(username, name, pw, pw2)
            except ValueError as exc:
                theme.alert("error", "Student not added", str(exc))
            else:
                st.session_state.acc_flash = f"Added {username} with access to no lectures."
                st.rerun()
    st.markdown('<div class="label">Set a new password</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="small">Password rules: {theme.esc(rules)}</div>', unsafe_allow_html=True)
    with st.form("reset_pw", border=False):
        who = st.selectbox("Account", [u for u, _ in auth.students()] or [""])
        c1, c2 = st.columns(2)
        pw, pw2 = c1.text_input("New password", type="password", key="reset_pw_value"), \
            c2.text_input("Confirm new password", type="password", key="reset_pw_confirm")
        if st.form_submit_button("Set password", type="primary"):
            try:
                auth.set_password(who, pw, pw2)
            except ValueError as exc:
                theme.alert("error", "Password not changed", str(exc))
            else:
                theme.alert("success", "Password updated", f"Password for {who} updated.")


# ----------------------------------------------------------------------------
# notes library and upload
# ----------------------------------------------------------------------------

def library_html(rows, dates):
    base_date, since_upload = dates
    body = []
    for r in rows:
        badge = (f' <span class="badge badge-uploaded">uploaded {theme.esc(r["uploaded"])}</span>' if r["uploaded"] else "")
        if r["uploaded"]:
            checked = since_upload.get(r["title"]) or "not since upload"
        else:
            checked = base_date or "never"
        body.append(f'<tr><td>{theme.esc(Path(str(r["file"])).name)}{badge}</td><td>{theme.esc(r["title"])}</td><td class="num">{r["sections"]}</td>'
                    f'<td>{theme.esc(checked)}</td></tr>')
    return ('<table class="lib"><thead><tr><th>File</th><th>Lecture</th><th class="num">Sections</th><th>Last fact-check</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table>')


def guides_library_html(entries):
    """The dissection guides: which lecture each one is matched to, how sure the match is, and that none is fact-checked yet."""
    body = []
    for e in entries:
        lecture = e["matched_lecture"] or "unmatched"
        if e.get("also_lecture"):
            lecture += f' + {e["also_lecture"]}'
        conf = e["confidence"]
        who = "instructors, students with full access, or a student granted this guide" if not e["matched_lecture"] else "follows the lecture's access, or the guide can be granted itself"
        body.append(f'<tr><td>{theme.esc(e["display_name"])}</td><td>{theme.esc(lecture)}</td>'
                    f'<td><span class="badge {"badge-uploaded" if conf in ("low", "unmatched") else "badge-notes"}">{theme.esc(conf)}</span></td>'
                    f'<td class="num">{e["n_slides"]}</td><td>{theme.esc(who)}</td>'
                    '<td><span class="badge badge-uploaded">not fact-checked yet</span></td></tr>')
    return ('<table class="lib"><thead><tr><th>Guide</th><th>Matched lecture</th><th>Match</th><th class="num">Slides</th><th>Visible to</th>'
            f'<th>Fact-check</th></tr></thead><tbody>{"".join(body)}</tbody></table>')


@instructors_only
def notes_tab():
    rows = notes_upload.library()
    uploaded = {r["title"]: r["uploaded"] for r in rows if r["uploaded"]}
    theme.section("Notes library")
    theme.meta(f"{len(rows)} lectures. Dr. Inglis’s original files are never edited or overwritten; "
               "an uploaded file is kept as a separate version.")
    st.markdown(library_html(rows, reports.fact_check_dates(uploaded)), unsafe_allow_html=True)

    guide_entries = list(guides.map_by_file().values())
    if guide_entries:
        theme.section("Dissection guides")
        n_weak = sum(e["confidence"] in ("low", "unmatched") for e in guide_entries)
        theme.meta(f"{len(guide_entries)} guides, matched to lectures by title and content (not by number: Class 17 is Lecture 13). "
                   f"{n_weak} need a look (low or unmatched, see the dissection-guides inventory report). The guides have not been fact-checked. "
                   "Students may use a guide when they may use its lecture.")
        st.markdown(guides_library_html(guide_entries), unsafe_allow_html=True)

    st.markdown('<div class="section-title">Add or replace notes</div>', unsafe_allow_html=True)
    st.markdown('<div class="small">Name the file like “Lecture 09 - The Hand - Notes.docx”. A file for a lecture that exists replaces it in the '
                'search (the old version is kept); a new lecture number adds one. New lectures start with no student access.</div>',
                unsafe_allow_html=True)
    if msg := st.session_state.pop("upload_flash", None):
        theme.alert("success", "Notes saved", msg)
    file = st.file_uploader("Word file", type=["docx", "doc"], key="notes_file", label_visibility="collapsed")
    if file is not None:
        try:
            _, title, lecture_id = notes_upload.identify(file.name)
            exists = any(r["lecture_id"] == lecture_id for r in rows)
            st.markdown(f'<div class="small">Detected: <b>{theme.esc(title)}</b>. This will '
                        f'{"replace that lecture in the search (version kept)" if exists else "add a new lecture"}.</div>', unsafe_allow_html=True)
        except notes_upload.UploadError as exc:
            theme.alert("error", "That file can't be used", str(exc))
            file = None
    if file is not None and st.button("Save and index", key="upload_go", type="primary"):
        bar = st.progress(0.0, text="Starting")
        try:
            out = notes_upload.add_or_replace(file.name, file.getvalue(), model=get_runtime().searcher.model,
                                              progress=lambda f, m: bar.progress(min(1.0, f), text=m))
        except notes_upload.UploadError as exc:
            bar.empty()
            theme.alert("error", "Upload failed", str(exc))
        else:
            get_runtime.clear()                       # the search reloads the new index on the next use
            ix = out["index"] or {}
            st.session_state.last_upload = {"title": out["lecture"], "sections": out["sections"]}
            st.session_state.upload_flash = (f'{out["lecture"]}: version {out["version"]} saved, {out["sections"]} sections parsed; '
                                             f'{ix.get("embedded", 0)} chunks embedded, {ix.get("kept", 0)} unchanged and reused. '
                                             'Students see it on their next question.')
            st.rerun()

    st.markdown('<div class="section-title">Fact-check an uploaded file</div>', unsafe_allow_html=True)
    options = [r for r in rows if r["uploaded"]]
    if not options:
        st.markdown('<div class="small">Upload a file first. The fact-check asks the model to compare each section with the open textbook '
                    'and costs real money, so it is never run automatically.</div>', unsafe_allow_html=True)
        return
    titles = [r["title"] for r in options]
    pre = st.session_state.get("last_upload", {}).get("title")
    pick = st.selectbox("File", titles, index=titles.index(pre) if pre in titles else 0, key="fc_pick")
    n = next(r["sections"] for r in options if r["title"] == pick)
    est = notes_upload.estimate_cost(n)
    st.markdown(f'<div class="small">{n} sections × about $0.015 = <b>about {theme.dollars(est)}</b>. Results appear in the Review queue '
                'as AI-generated suggestions.</div>', unsafe_allow_html=True)
    sure = st.checkbox(f"Yes, spend about {theme.dollars(est)}", key="fc_confirm")
    if st.button("Run fact-check on this file", key="fc_run", type="primary", disabled=not sure):
        with st.status("Fact-checking…", expanded=True) as status:
            res = notes_upload.run_factcheck(pick, line=lambda t: None)
            status.update(label="Done" if res["ok"] else "The fact-check stopped", state="complete" if res["ok"] else "error")
        usage_log.log_event({"mode": "factcheck", "user": "professor", "lecture": pick, "cost": res["cost"]})
        if res["ok"]:
            theme.alert("success", "Fact-check finished", f"Actual cost {theme.dollars(res['cost'])}. See the Review queue.")
        else:
            theme.alert("error", "The fact-check did not finish", "Finished calls are saved, so running it again resumes. Last output:")
            st.code("\n".join(res["output"].splitlines()[-6:]))


# ----------------------------------------------------------------------------
# usage and settings
# ----------------------------------------------------------------------------

def money(x):
    """Dollars, or the plain 'course key' wording when the current model has no listed price."""
    return theme.dollars(x) if llm.cost_tracked(get_runtime().model) else llm.NOT_TRACKED


@instructors_only
def usage_tab():
    theme.section("Usage")
    theme.meta("What students and previews asked, and what it cost, split by type. Previews never count as student usage.")
    s = usage_log.summary()
    chat, guide_, prev = s["chat"], s["guide"], s["preview"]
    today = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    st.markdown('<div class="label">Students</div>', unsafe_allow_html=True)
    cols = st.columns(4)
    for col, label, value in ((cols[0], "Chat answers", chat["questions"]), (cols[1], "Guide steps", guide_["steps"]),
                              (cols[2], "Student cost", money(chat["cost"] + guide_["cost"])),
                              (cols[3], "Cost today, all kinds (UTC)", money(s["cost_by_day"].get(today, 0.0)))):
        col.markdown(theme.stat(label, value), unsafe_allow_html=True)
    cols = st.columns(2)
    for col, label, value in ((cols[0], "Web-sourced answers", len(chat["web"])), (cols[1], "Term lookups", chat["term"])):
        col.markdown(theme.stat(label, value, small=True), unsafe_allow_html=True)
    st.markdown('<div class="section-title">Professor previews (not counted as student usage)</div>',
                unsafe_allow_html=True)
    cols = st.columns(4)
    for col, label, value in ((cols[0], "Preview questions", prev["questions"]), (cols[1], "Preview Guide steps", prev["guide_steps"]),
                              (cols[2], "Preview cost", money(prev["cost"])),
                              (cols[3], "Fact-check runs", f'{s["factcheck"]["runs"]} ({money(s["factcheck"]["cost"])})')):
        col.markdown(theme.stat(label, value, small=True), unsafe_allow_html=True)
    earlier = (f' Earlier runs with a priced model: {theme.dollars(s["cost_total"])}.'
               if s["cost_total"] and not llm.cost_tracked(get_runtime().model) else "")
    st.markdown(f'<div class="small mt-4">Total cost, everything: {money(s["cost_total"])}.{earlier}</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="section-title">Cost per day</div>', unsafe_allow_html=True)
    if s["cost_by_day_kind"]:
        theme.cost_chart(s["cost_by_day_kind"])
        rows = [{"Day (UTC)": d, **{k: f"${v:,.4f}" for k, v in kinds.items()}, "Total": f"${sum(kinds.values()):,.4f}"}
                for d, kinds in s["cost_by_day_kind"].items()]
        st.dataframe(pd.DataFrame(rows).fillna("$0.0000"), hide_index=True, width="stretch")     # the chart's numbers, as text
    else:
        st.markdown('<div class="small">No questions yet.</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Lectures students ask about most</div>', unsafe_allow_html=True)
    if chat["top_lectures"]:
        st.dataframe(pd.DataFrame(chat["top_lectures"], columns=["Lecture", "Questions"]), hide_index=True, width="stretch")
    else:
        st.markdown('<div class="small">Nothing yet.</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Student questions the notes could not answer</div>'
                '<div class="small">Each one is a possible gap in the notes (or a question outside the course: treatment and diagnosis are declined).</div>',
                unsafe_allow_html=True)
    if chat["unanswered"]:
        df = pd.DataFrame([{"When (UTC)": e["ts"].replace("T", " "), "Student": e.get("user", ""), "Question": e["question"],
                            "Outcome": (e["status"] + (f" ({e['reason']})" if e.get("reason") else "")).replace("_", " ")}
                           for e in reversed(chat["unanswered"])])
        st.dataframe(df, hide_index=True, width="stretch")
    else:
        st.markdown('<div class="small">None logged yet.</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Web-sourced answers</div>'
                '<div class="small">Answers written from public web pages because the notes, dissection guides and OpenStax found nothing. '
                'Students saw them labelled "From the web". Check them, and add to the notes if they belong there.</div>',
                unsafe_allow_html=True)
    show = st.selectbox("Show", ["Web-sourced answers only", "All student questions"], key="usage_filter")
    entries = chat["web"] if show.startswith("Web") else [e for e in usage_log.read_log() if usage_log.kind_of(e) == "chat_answer"]
    if entries:
        st.dataframe(pd.DataFrame([{"When (UTC)": e["ts"].replace("T", " "), "Student": e.get("user", ""), "Question": e["question"],
                                    "Answered from": "web" if e.get("web") else e.get("tier", e.get("basis", "")),
                                    "Pages": ", ".join(e.get("web_urls", []))} for e in reversed(entries)]),
                     hide_index=True, width="stretch")
    else:
        st.markdown('<div class="small">None logged yet.</div>', unsafe_allow_html=True)
    st.markdown('<div class="small mt-4">Questions are stored on this machine, with the student’s username.</div>', unsafe_allow_html=True)


@instructors_only
def settings_tab():
    cur = usage_log.load_settings()
    theme.section("Settings")
    with st.form("settings", border=False):
        theme.label("Spending limit")
        cap = st.number_input("Spending cap per student session (US dollars)", min_value=0.0, value=float(cur["spending_cap_usd"]),
                              step=0.25, format="%.2f")
        theme.meta("When one student session has cost this much, the app says so politely and stops calling the model. Students never see the amount.")
        theme.label("Answer style")
        brief = st.toggle("Answers are brief by default", value=bool(cur["default_brief"]))
        theme.meta("Brief answers are about five lines. A student can switch to Detailed in the sidebar at any time.")
        if st.form_submit_button("Save settings", type="primary"):
            usage_log.save_settings(spending_cap_usd=float(cap), default_brief=bool(brief))
            toast("Settings saved. New sessions use them.")


def sidebar(user):
    with st.sidebar:
        theme.wordmark()
        theme.label("Professor")
        st.page_link(nav.PAGES["dashboard"], label="Dashboard", icon=":material/dashboard:")
        st.page_link(nav.PAGES["chat"], label="View as student", icon=":material/visibility:")
        st.page_link(nav.PAGES["guide"], label="Guide as student", icon=":material/menu_book:")
        if "quiz" in nav.PAGES:
            st.page_link(nav.PAGES["quiz"], label="Quiz as student", icon=":material/quiz:")
        theme.label("Signed in")
        st.markdown(f'<div class="small">{theme.esc(user["name"])}</div>', unsafe_allow_html=True)
        st.button("Sign out", key="signout_prof", on_click=nav.sign_out)
        st.markdown('<div class="small">Reloading this page signs you out.</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="footer">Model {theme.esc(get_runtime().model)} · preview session cost '
                    f'{money(st.session_state.cost)}</div>', unsafe_allow_html=True)


# ----------------------------------------------------------------------------

@instructors_only
def quiz_tab(user):
    quiz_review.render(user)


@instructors_only
def page(user):
    theme.set_title("Dashboard")
    state.init()
    sidebar(user)
    theme.page_title("Dashboard", "For Dr. Inglis. Students never see these pages. The Review queue is the first tab.")
    tabs = st.tabs(["Review queue", "Verified fixes", "Notes library", "Access", "Usage", "Quiz items", "Settings"])
    for tab, body in zip(tabs, (lambda: review_queue(user), ledger_tab, notes_tab, access_tab, usage_tab, lambda: quiz_tab(user), settings_tab)):
        with tab:
            body()
