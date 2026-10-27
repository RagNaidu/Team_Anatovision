"""Guide mode UI: a station stepper, the station card, 'Describe what you see', and the judge's verdict in plain words.

A thin layer over src.modes.guide.GuideSession: every rule (no skipping, back to the first missing station, a consequence
only when it is tied to the mistake) lives there. SAMPLE MODE: the notes are descriptive, so this walks a lecture's own
order, not a dissection procedure.
"""
import re

import streamlit as st

from app import nav, state, theme
from app.data import get_runtime
from app.views import pane
from src import citations as cit
from src import student_view as sv
from src import usage as usage_log
from src import guide_service, guide_store
from src.ingest import guides as guide_files
from src.modes import guide, guide_slides, qa

VERDICT = {"yes": "Matches the notes", "partial": "Partly matches", "no": "Not yet", "error": "Could not check"}


def accessible(user):
    """Lecture titles this user may walk through in the sample (lecture notes) mode."""
    from app.views.student import lecture_options
    return lecture_options(user)


def accessible_guide_entries(user):
    """Dissection guides this user may open: their matched lecture is granted, the guide itself is granted, or full access."""
    from app.views.student import accessible_lectures
    return guide_files.accessible_guides(accessible_lectures(user))


MARK_NOTE = {"check": sv.CHECK_LABEL, "corrected": sv.corrected_sentence("").strip()}


def item_html(item, corrected_by=""):
    """One card item (from sv.guide_state): the text, and a muted neutral note after it when the line is flagged or corrected.
    Nothing is coloured inside the notes text."""
    out = theme.esc(item["text"])
    if item["mark"] == "corrected":
        out += f' <span class="small">{theme.esc(sv.corrected_sentence(corrected_by))}</span>'
    elif item["mark"] == "check":
        out += f' <span class="small">{theme.esc(sv.CHECK_LABEL)}</span>'
    return out


def items_block(title, items, corrected_by=""):
    if not items:
        return ""
    rows = "".join(f"<li>{item_html(i, corrected_by)}</li>" for i in items)
    return f'<div class="label">{theme.esc(title)}</div><ul class="items">{rows}</ul>'


# ----------------------------------------------------------------------------
# starting a session
# ----------------------------------------------------------------------------

SAMPLE_NOTE = guide.BANNER.replace("SAMPLE MODE: ", "").capitalize()
LOCKED_MSG = "Finish the earlier stations first."


SOURCES = ["Dissection guide", "Lecture notes (sample)"]
EMPTY_MSG = "No lectures or dissection guides have been shared with you yet. Ask your instructor."


def has_saved(username, entry, real_user):
    if real_user and real_user["role"] == "professor":
        return False
    try:
        return entry["file"] in guide_store.GuideStore().guides_of(username)
    except Exception:
        return False


def access_card():
    """A student with nothing granted: what is missing and what still works, in one compact card."""
    st.markdown('<div class="gwelcome"><p><b>No dissection guides are open to you yet.</b></p>'
                '<p class="small">Your instructor chooses which guides and lectures you can use. Ask them to open a guide for you. '
                'In the meantime, Ask the lab still answers from the OpenStax reference text.</p></div>', unsafe_allow_html=True)
    st.page_link(nav.PAGES["chat"], label="Go to Ask the lab", icon=":material/chat:")


def picker(user, real_user=None):
    guides_ok, options = accessible_guide_entries(user), accessible(user)
    st.markdown('<div class="ghead"><span class="gname">Guide</span><span class="gpos">Talk through a dissection guide, step by step</span></div>',
                unsafe_allow_html=True)
    if not guides_ok and not options:
        access_card()
        return
    if st.session_state.get("guide_lecture_pref"):                     # the example button on the landing page opens the lecture-notes sample
        st.session_state.guide_source = SOURCES[1]
    source = st.radio("Source", SOURCES, key="guide_source", horizontal=True,
                      help="Dissection guides are Dr. Inglis's lab slides. The lecture notes walk-through is a sample.")
    if source == SOURCES[0]:
        guide_picker(user, guides_ok, real_user)
    else:
        notes_picker(user, options)


def guide_picker(user, entries, real_user=None):
    if not entries:
        theme.meta("No dissection guides have been shared with you yet. Ask your instructor.")
        return
    labels = {}
    for e in entries:
        labels[e["display_name"] + ("  ·  in progress" if has_saved(user["username"], e, real_user) else "")] = e
    pick = st.selectbox("Search or choose a dissection guide", list(labels), key="guide_pick")
    entry = labels[pick]
    n = len(guide_service.steps_of(entry))
    theme.meta(f"{n} steps." if n else guide_slides.NO_TEXT)
    if n and st.button("Open guide", key="guide_start", type="primary"):
        open_guide(user, real_user, entry)


def open_guide(user, real_user, entry):
    """Start or restore THIS guide's own session. Access is checked again here, at the moment of opening."""
    from app.views.student import accessible_lectures
    preview = bool(real_user and real_user["role"] == "professor")
    rt = get_runtime()
    sess = guide_service.open_session(user["username"], entry["file"], accessible_lectures(user), rt.client, rt.model,
                                      st.session_state.body_type, persist=not preview)
    if sess is None:
        theme.alert("error", "Guide not available", "That guide is not available to you.")
        return
    st.session_state.body_done = True
    st.session_state.gsess, st.session_state.gjob, st.session_state.gerr, st.session_state.gshow = sess, None, None, False
    st.rerun()


def notes_picker(user, options):
    theme.alert("info", "Sample mode", SAMPLE_NOTE)                  # only for this option: it is not a dissection procedure
    if not options:
        theme.meta("No lectures have been shared with you yet. Ask your instructor.")
        return
    pref = st.session_state.pop("guide_lecture_pref", None)
    if pref:
        st.session_state.guide_lecture = next((t for t in options if t.startswith(pref)), options[0])
    title = st.selectbox("Lecture", options, key="guide_lecture")
    rt = get_runtime()
    ctx = qa.load_context()
    _, rows = guide.find_lecture(title, guide.load_sections())
    stations = guide.build_stations(rows)
    cached, total = guide.count_cached(rt.model, rows[0]["lecture_id"], stations, ctx)
    missing = total - cached
    if missing:
        theme.meta(f"{total} stations. The first time a lecture is used, its stations are prepared from the notes. "
                   "That takes a moment.")
    else:
        theme.meta(f"{total} stations, all prepared.")
    if st.button("Start", key="guide_start", type="primary"):
        if title not in options:                       # the lecture must be one this user may use (checked again here)
            theme.alert("error", "Lecture not available", "That lecture is not available to you.")
            return
        if missing and state.cap_reached():
            theme.alert("warning", "Session limit reached", "A new lecture cannot be prepared in this session.")
            return
        st.session_state.body_done = True
        loading = st.empty()
        loading.markdown(theme.loading_html("Preparing the stations…"), unsafe_allow_html=True)
        try:
            session = guide.GuideSession.open(rt.client, rt.model, title, ctx=ctx, body_type=st.session_state.body_type,
                                              flag_logger=guide.make_flag_logger())
        finally:
            loading.empty()
        fresh = session.prep
        state.add_cost(qa.cost_of(fresh, rt.model) if fresh["calls"] else 0.0,
                       {"input": fresh["input_tokens"], "output": fresh["output_tokens"]})
        st.session_state.guide, st.session_state.guide_turn, st.session_state.sel = session, None, None
        st.session_state.guide_turn_raw = None
        st.session_state.guide_revealed, st.session_state.guide_notice = set(), ""
        st.rerun()


# ----------------------------------------------------------------------------
# the running session
# ----------------------------------------------------------------------------

def go(text):
    """Navigation turns (no model call) run in the button callback. Only the student-safe turn is kept for the screens."""
    g = st.session_state.guide
    g.body_type = st.session_state.body_type
    st.session_state.guide_notice = ""
    turn = g.step(text)
    st.session_state.guide_turn = sv.guide_turn(turn)
    st.session_state.guide_turn_raw = turn if st.session_state.get("guide_keep_raw") else None


def locked_click():
    """A locked station answers with words instead of doing nothing."""
    st.session_state.guide_notice = LOCKED_MSG


def leave():
    st.session_state.guide, st.session_state.guide_turn, st.session_state.guide_turn_raw = None, None, None
    st.session_state.guide_revealed, st.session_state.guide_notice = set(), ""


def revealed(s, n):
    """The notes for a station are shown only after the student has described it, or chosen to look (open book)."""
    return n in st.session_state.get("guide_revealed", set()) or n in s["done"]


def station_button(prefix, item, locked_all, label):
    n, status = item["n"], item["status"]
    st.button(label, key=f"{prefix}_{status}_{n}", on_click=locked_click if status == "locked" else go,
              args=() if status == "locked" else (f"station {n}",), disabled=(locked_all and status != "current"))


def stepper(s):
    theme.label("Stations")
    locked_all = s["stage"] == "check"
    with st.container(horizontal=True, gap="small", key="stepper"):
        for item in s["stations"]:
            station_button("step", item, locked_all, str(item["n"]))
    st.progress(s["progress"], text=f"{len(s['done'])} of {s['total']} stations done")
    st.markdown('<div class="legend">A tick means done, a padlock means locked until the stations before it are done.</div>',
                unsafe_allow_html=True)
    if notice := st.session_state.pop("guide_notice", ""):             # shown once, right after the click
        theme.alert("warning", "That station is locked", notice)
    with st.expander("All stations, with names"):          # the real names (also the phone layout, where the numbers are hidden)
        for item in s["stations"]:
            station_button("stlist", item, locked_all, f'{item["n"]}. {item["name"]}')


def verdict_block(detail):
    if detail["verdict"] == "error":
        theme.alert("warning", "Could not check", "The check did not run. Try again, or press \"I re-checked it\".")
    elif detail["verdict"] == "yes":
        theme.alert("success", "Matches the notes", detail["feedback"])
    else:
        look = f' Look again at: {detail["should_see"]}' if detail.get("should_see") else ""
        theme.alert("warning", "Not quite yet", f'{detail["feedback"]}{look}')
        if detail.get("consequence"):
            theme.meta(detail["consequence"])


def notes_card(s):
    """The notes for this station, each fact once (see student_view.dedupe_card)."""
    card, meta = s["card"], s["meta"]
    by = meta["corrected_by"]
    parts = [items_block("You should see", card["what_you_should_see"], by), items_block("Landmarks", card["landmarks_relations"], by),
             items_block("Identify", card["identify_these"], by)]
    if meta["reviewing"]:
        parts.append(theme.alert_html("warning", sv.REVIEW_LABEL, sv.NEUTRAL_REVIEW))
    if card["variation_if_stated"]:
        who = f" ({theme.esc(s['body_type'])})" if s["body_type"] else ""
        parts.append(f'<div class="label">Body type</div><p class="small">The notes mention variation{who}: '
                     f'{item_html(card["variation_if_stated"][0], by)}</p>')
    st.markdown("".join(parts), unsafe_allow_html=True)


def log_guide(g, n, kind, mode, user, real_user, **extra):
    preview = bool(real_user and real_user["role"] == "professor")
    entry = {"mode": mode, "kind": "professor_preview" if preview else kind,
             "user": real_user["username"] if preview else user["username"], "lecture": g.lecture, "station": n, **extra}
    if preview:
        entry["as_user"] = user["username"]
    usage_log.log_event(entry)


def station_card(g, s, user, real_user=None):
    n, card = s["current"], s["card"]
    st.markdown(f'<h2 class="station-title"><span class="station-count">Station {n} of {s["total"]} · </span>'
                f'{theme.esc(s["stations"][n - 1]["name"])}</h2>', unsafe_allow_html=True)
    nav_row = theme.button_row(f"navrow_{n}")
    nav_row.button("Previous station", key=f"prev_{n}", on_click=go, args=(f"station {n - 1}",), disabled=n <= 1,
                   icon=":material/arrow_back:")
    nav_row.button("Next station" if not s["finished"] else "Lecture finished", key=f"next_{n}", on_click=go, args=("next",),
                   disabled=not s["can_advance"], icon=":material/arrow_forward:", icon_position="right")
    if s["finished"]:
        theme.meta("You have finished every station in this lecture.")
    elif not s["can_advance"] and not s["empty"]:
        theme.meta("Describe what you see to unlock the next station.")
    if s["empty"]:
        theme.meta("The notes give nothing to identify at this station.")
        notes_card(s)
    else:
        shown = revealed(s, n)
        if not shown:                                              # the answer key stays hidden until they have described it
            st.markdown('<div class="prompt-card"><h3>Describe what you see</h3><p>Look at this station and say, in your own words, '
                        'what you can see and point to. The notes come after you describe it.</p></div>', unsafe_allow_html=True)
        with st.form(f"describe_{n}", border=False):
            text = st.text_area("Your description", key=f"desc_{n}", height=110,
                                placeholder="Say what you can see and point to at this station, in your own words.")
            row = theme.button_row(f"checkrow_{n}")
            with row:
                check = st.form_submit_button("Check my description", type="primary", disabled=state.cap_reached())
                peek = False if shown else st.form_submit_button("Show the notes")
        if s["needs_recheck"]:
            st.button("I re-checked it", key=f"recheck_{n}", on_click=go, args=("rechecked",))
        if peek:
            st.session_state.guide_revealed.add(n)
            log_guide(g, n, "guide_peek", "guide", user, real_user, event="peek")
            st.rerun()
        if check:
            if not text.strip():
                theme.alert("warning", "Describe it first", "Type what you can see, then press Check my description.")
            else:
                g.body_type = st.session_state.body_type
                loading = st.empty()
                loading.markdown(theme.loading_html("Comparing with the notes…"), unsafe_allow_html=True)
                try:
                    turn = g.step(text)
                finally:
                    loading.empty()
                state.add_cost(turn["cost"], turn["tokens"])
                preview = bool(real_user and real_user["role"] == "professor")
                log_guide(g, n, "guide_step", "guide", user, real_user, verdict=(turn["detail"] or {}).get("verdict"),
                          cost=turn["cost"], tokens=turn["tokens"])
                st.session_state.guide_revealed.add(n)
                st.session_state.guide_turn = sv.guide_turn(turn)                      # the screens only ever get this
                st.session_state.guide_turn_raw = turn if preview else None
                st.rerun()
        if state.cap_reached():
            theme.alert("warning", "Session limit reached", "Descriptions cannot be checked in this session. Ask your instructor.")
        turn = st.session_state.guide_turn
        if turn and turn["detail"] and turn["detail"].get("station") == n:
            verdict_block(turn["detail"])
        if shown:
            notes_card(s)


def check_card(s):
    lines = s["check"]["lines"]
    rows = "".join(f"<li>{theme.esc(l)}</li>" for l in lines[1:-1])
    st.markdown(f'<div class="card"><h4>{theme.esc(lines[0])}</h4><ul class="checklist">{rows}</ul>'
                '<p>Have you identified these?</p></div>', unsafe_allow_html=True)
    row = theme.button_row("check_buttons")
    row.button("Yes, I have", key="check_yes", on_click=go, args=("yes",), type="primary")
    row.button("Not yet", key="check_no", on_click=go, args=("no",))


def right_pane(g, s, instructor=False):
    st.markdown('<span class="pane-marker"></span>', unsafe_allow_html=True)
    options = pane.PANES + (["Instructor detail"] if instructor else [])
    which = st.segmented_control("Pane", options, key="pane", label_visibility="collapsed", default=pane.PANES[0])
    in_station = s["stage"] == "station_active"
    passages = g.passages(s["current"]) if in_station else []
    if which == "How this answer was built":
        theme.label("How this was built")
        if in_station and revealed(s, s["current"]):
            built, corrections = sv.guide_built(passages)
            groups, _ = sv.built_lines(built)
            pane.show_built(groups, corrections)
        else:
            theme.meta("Pick a station and describe it to see the notes it is built from.")
        return
    if which == "Instructor detail" and instructor:
        raw = st.session_state.get("guide_turn_raw")
        pane.instructor_detail({"events": (raw or {}).get("events") or [{"i": 1, "t": 0.0, "kind": "info", "label": "No steps recorded yet", "detail": {}}],
                                "tokens": (raw or {}).get("tokens", {"input": 0, "output": 0}), "cost": (raw or {}).get("cost", 0.0),
                                "model": g.model})
        if g.prep:
            st.markdown(f'<div class="kv">Station cards: {g.prep["cached"]} read from the saved cache, {g.prep["calls"]} '
                        'written by the model when this lecture was prepared.</div>', unsafe_allow_html=True)
        return
    if not in_station:
        theme.meta("The notes behind a station appear here once you are at it.")
        return
    if not revealed(s, s["current"]):
        theme.meta("The notes for this station appear here after you describe what you see, or when you choose Show the notes.")
        return
    theme.label("The notes behind this station")
    for p in sv.guide_passages(passages):
        notes = "".join(f'<div class="kv">{theme.esc(n)}</div>' for n in p["notes"])
        st.markdown(f'{pane.badge("notes")}<div class="pane-title">{theme.esc(p["breadcrumb"])}</div>'
                    f'<div class="passage">{cit.passage_html(p["text"], [])}</div>{notes}', unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# the conversation on a dissection guide (src/modes/guide_chat.py holds every rule)
# ----------------------------------------------------------------------------

WELCOME = "Are you starting from the beginning, or where are you now?"
HINT = 'Choose Start from the beginning, or type where you are. For example: "I\'m at slide 7", "I\'ve reflected the gluteus maximus", "I\'m at the knee joint".'


def md_safe(text):
    return (text or "").replace("$", "\\$")


def queue(text=None, action=None):
    """A click or a typed message becomes ONE queued job. While a job exists every control is disabled, so nothing can be sent twice."""
    if st.session_state.get("gjob") is None:
        st.session_state.gjob = {"text": text, "action": action}
        st.session_state.gerr = None


def retry():
    err = st.session_state.get("gerr")
    st.session_state.gerr = None
    if err and st.session_state.get("gjob") is None:
        st.session_state.gjob = err["job"]


def dismiss_error():
    st.session_state.gerr = None


def toggle_passage():
    st.session_state.gshow = not st.session_state.get("gshow")


def leave_chat():
    st.session_state.gsess, st.session_state.gjob, st.session_state.gerr, st.session_state.gshow = None, None, None, False


def start_over():
    sess = st.session_state.get("gsess")
    if sess is not None:
        sess.reset()
    st.session_state.gjob, st.session_state.gerr, st.session_state.gshow = None, None, False


def step_label(step):
    return f"Slide {step['slide']}" + (f" (part {step['part']})" if step["parts"] > 1 else "")


def sources_html(sess, cites):
    by = {s["id"]: s for s in sess.steps}
    rows = []
    for cid in cites:
        s = by.get(cid)
        if not s:
            continue
        body = theme.esc(s["text"]) if s["text"] else "This slide has no text I can read."
        pic = " This slide also has a picture that cannot be read here; look at it in your lab guide." if s["picture"] else ""
        rows.append(f'<details><summary>{theme.esc(step_label(s))}</summary><div class="gpass">{body}{theme.esc(pic)}'
                    f'<span class="gpass-cite">{theme.esc(s["cite"])}</span></div></details>')
    return f'<div class="gsrcs">{"".join(rows)}</div>' if rows else ""


def outline_html(v):
    mark = {"current": "You are here", "done": "Reported done", "missing": "Missing?", "open": ""}
    rows = []
    for o in v["outline"]:
        cls = {"current": "cur", "missing": "miss"}.get(o["status"], "")
        part = f" (part {o['part']})" if o["parts"] > 1 else ""
        rows.append(f'<li class="{cls}"><span class="gmark">{mark[o["status"]] or "&nbsp;"}</span>'
                    f'<span>Slide {o["slide"]}{part}: {theme.esc(o["label"])}</span></li>')
    return f'<ul class="goutline">{"".join(rows)}</ul>'


def render_messages(sess, v):
    if not v["messages"]:
        st.markdown(f'<div class="gwelcome"><p><b>{theme.esc(WELCOME)}</b></p><p class="small">{theme.esc(HINT)}</p></div>', unsafe_allow_html=True)
    for i, m in enumerate(v["messages"]):
        if m["role"] == "user":
            st.markdown(f'<div class="msg-user gmsg-u" role="group" aria-label="You said">{theme.esc(m["text"])}</div>', unsafe_allow_html=True)
            continue
        with st.container(key=f"gma_{i}"):
            st.markdown(md_safe(m["text"]))
        st.markdown(sources_html(sess, m["cites"]), unsafe_allow_html=True)


def log_turn(sess, user, real_user, reply, job):
    preview = bool(real_user and real_user["role"] == "professor")
    entry = {"mode": "guide", "kind": "professor_preview" if preview else "guide_step",
             "user": real_user["username"] if preview else user["username"], "lecture": sess.entry["display_name"],
             "step": sess.state.get("pos"), "ok": reply.ok, "via": job.get("action") or "text",
             "cost": 0.0, "tokens": {"input": reply.usage["input_tokens"], "output": reply.usage["output_tokens"]}}
    if preview:
        entry["as_user"] = user["username"]
    usage_log.log_event(entry)


def run_job(sess, user, real_user, preview):
    """Run the queued job (one engine turn), keep the result, and rerun. A failed turn leaves the saved position as it was."""
    job = st.session_state.gjob
    if job.get("text"):
        st.markdown(f'<div class="msg-user gmsg-u">{theme.esc(job["text"])}</div>', unsafe_allow_html=True)
    loading = st.empty()
    loading.markdown(theme.loading_html("Reading the guide…"), unsafe_allow_html=True)
    sess.state["body_type"] = st.session_state.body_type
    try:
        reply = sess.turn(text=job.get("text"), action=job.get("action"))
    finally:
        loading.empty()
    state.add_cost(0.0, {"input": reply.usage["input_tokens"], "output": reply.usage["output_tokens"]})
    log_turn(sess, user, real_user, reply, job)
    st.session_state.gerr = None if reply.ok else {"message": reply.error, "job": job}
    st.session_state.gjob = None
    st.session_state.gevents = reply.events if preview else None
    st.rerun()


def chat_view(user, real_user=None):
    sess = st.session_state.gsess
    preview = bool(real_user and real_user["role"] == "professor")
    if sess.entry["file"] not in {e["file"] for e in accessible_guide_entries(user)}:      # access is re-read on every run
        leave_chat()
        theme.alert("error", "Guide not available", "That guide is no longer available to you.")
        picker(user, real_user)
        return
    v = sess.view()
    busy = st.session_state.get("gjob") is not None
    err = st.session_state.get("gerr")
    pos = f"Slide {v['slide']} · step {v['position']} of {v['total']}" if v["started"] else f"Not started · {v['total']} steps"
    with st.container(key="ghead_wrap"):                      # stays at the top while the conversation scrolls
        with st.container(horizontal=True, vertical_alignment="center", gap="small", key="ghead_row"):
            st.markdown(f'<div class="ghead"><span class="gname">{theme.esc(v["guide"])}</span><span class="gpos">{theme.esc(pos)}</span></div>',
                        unsafe_allow_html=True)
            st.button("Change guide", key="gchange", on_click=leave_chat, disabled=busy)
            with st.popover("Start over", help="Clears this guide's conversation and progress", disabled=busy):
                st.markdown("This clears your conversation and progress **for this guide only**.")
                st.button("Yes, start over", key="gresetyes", on_click=start_over, type="primary")
        st.progress(min(1.0, v["position"] / max(1, v["total"])),
                    text=f"At step {v['position']} of {v['total']} · {v['done']} reported done by you" if v["started"] else "Progress appears once you start")
    with st.expander("All steps in this guide"):
        st.markdown(outline_html(v), unsafe_allow_html=True)

    main, side = st.columns([3, 2], gap="large")
    with main:
        render_messages(sess, v)
        if err:
            with st.container(key="gerr_box"):
                theme.alert("warning", "That didn't go through", err["message"])
                with theme.button_row("gerr_buttons"):
                    st.button("Try again", key="gretry", on_click=retry, type="primary", disabled=busy)
                    st.button("Dismiss", key="gdismiss", on_click=dismiss_error, disabled=busy)
        if busy:
            run_job(sess, user, real_user, preview)
        with theme.button_row("gquick"):
            if not v["started"]:
                st.button("Start from the beginning", key="gquick_start", on_click=queue, kwargs={"action": "start"}, type="primary", disabled=busy)
            else:
                st.button("Continue", key="gquick_next", on_click=queue, kwargs={"action": "next"}, type="primary", icon=":material/arrow_forward:",
                          icon_position="right", disabled=busy or v["position"] >= v["total"])
                st.button("Back", key="gquick_back", on_click=queue, kwargs={"action": "back"}, icon=":material/arrow_back:", disabled=busy or v["position"] <= 1)
                st.button("Hide guide passage" if st.session_state.get("gshow") else "Show guide passage", key="gquick_show", on_click=toggle_passage,
                          icon=":material/menu_book:", disabled=busy)
        if v["started"] and st.session_state.get("gshow"):
            st.markdown(sources_html(sess, [v["step_id"]]).replace("<details>", "<details open>", 1), unsafe_allow_html=True)
        if state.cap_reached():
            theme.alert("warning", "Session limit reached", "No more replies can be written in this session. Ask your instructor.")
        st.markdown('<div class="chat-end"></div>', unsafe_allow_html=True)
    with side:
        st.markdown('<span class="pane-marker gside"></span>', unsafe_allow_html=True)
        theme.label("Where you are")
        cur = next((s for s in sess.steps if s["id"] == v["step_id"]), None)
        if cur is None:
            theme.meta("Your place in the guide appears here once you start.")
        else:
            st.markdown(f'{pane.badge("dissection_guide")}<div class="pane-title">{theme.esc(cur["cite"])}</div>'
                        f'<div class="passage">{cit.passage_html(cur["text"] or "No readable text on this slide.", [])}</div>', unsafe_allow_html=True)
        if preview and st.session_state.get("gevents"):
            pane.instructor_detail({"events": st.session_state.gevents, "tokens": st.session_state.tokens, "cost": 0.0, "model": sess.chat.model})
    if sess.persist:
        theme.meta("Your conversation and progress for this guide are saved to your account. Reloading signs you out; sign in again to continue.")
    else:
        theme.meta("Previews are not saved.")
    prompt = st.chat_input("Say where you are, what you see, or ask about this step", max_chars=C_MAX, disabled=busy or state.cap_reached())
    if prompt:
        queue(text=prompt.strip())
        st.rerun()


C_MAX = 600



def guide_view(user, real_user=None):
    if st.session_state.get("gsess") is not None:
        chat_view(user, real_user)
        return
    g = st.session_state.get("guide")
    if g is None:
        picker(user, real_user)
        return
    st.session_state.setdefault("guide_revealed", set())
    preview = bool(real_user and real_user["role"] == "professor")
    st.session_state.guide_keep_raw = preview
    g.body_type = st.session_state.body_type
    s = sv.guide_state(g.state())                       # the screens below see only this, never the raw session state
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key="guide_top"):
        st.markdown(f'<div class="section-title">{theme.esc(s["lecture"])}</div>', unsafe_allow_html=True)
        st.markdown(theme.badge_html("uploaded", "Sample mode"), unsafe_allow_html=True)
        st.button("Change lecture", key="guide_leave", on_click=leave)
    stepper(s)
    main, side = st.columns([3, 2], gap="large")
    with main:
        if s["stage"] == "check":
            check_card(s)
        elif s["stage"] == "station_active":
            station_card(g, s, user, real_user)
        else:
            st.markdown('<div class="card"><h4>Which station are you at?</h4><p>Choose its number above. If you are not at the '
                        'first station, I will first check that you have identified the earlier ones.</p></div>',
                        unsafe_allow_html=True)
    with side:
        right_pane(g, s, preview)
