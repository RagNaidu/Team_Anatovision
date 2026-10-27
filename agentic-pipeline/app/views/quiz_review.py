"""Professor view of Quiz items: the evidence behind every generated question, and approve / reject. Called only from professor.quiz_tab,
which is role-checked. Approval is a separate recorded decision (who, when); AI agreement is shown as such and never as approval."""
import time

import streamlit as st

from app import theme
from app.views.quiz_ui import highlight
from src.quiz import service as qs
from src.quiz.store import QuizStore

STATUS = {"all": "All", "unreviewed": "Not reviewed", "approved": "Approved", "rejected": "Rejected"}


def decide(item_id, status, by):
    note = st.session_state.get(f"qzr_note_{item_id}", "")
    QuizStore().set_review(item_id, status, by, note)


def item_block(it, by):
    r = it["review"]
    badge = {"approved": "verified", "rejected": "review", "unreviewed": "uploaded"}[r["status"]]
    st.markdown(theme.badge_html(badge, STATUS[r["status"]]) + f' <span class="small">{theme.esc(qs.review_label(r))}</span>', unsafe_allow_html=True)
    if it["stem"]:
        st.markdown(f'<div class="qz-stem">{theme.esc(it["stem"])}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="qz-lead">{theme.esc(it["lead_in"])}</div>', unsafe_allow_html=True)
    rows = "".join(f'<li class="{"qz-opt-right" if o["id"] in it["answer_ids"] else ""}"><b>{o["id"]}.</b> {theme.esc(o["text"])}'
                   f'{" <span class=qz-tag>Key</span>" if o["id"] in it["answer_ids"] else ""}</li>' for o in it["options"])
    st.markdown(f'<ul class="qz-opts">{rows}</ul>', unsafe_allow_html=True)
    st.markdown(f"**Explanation.** {it['explanation'].replace('$', chr(92) + '$')}")
    why = "".join(f"<li><b>{i}.</b> {theme.esc(a['why_wrong'])}</li>" for i, a in sorted(it["alternatives"].items()))
    st.markdown(f'<div class="label">Why each alternative fails</div><ul class="qz-why">{why}</ul>', unsafe_allow_html=True)
    spans = it["key_support"] + it["explanation_support"] + [s for a in it["alternatives"].values() for s in a["support"]]
    theme.label("Evidence (supporting spans are highlighted)")
    for e in it["evidence"].values():
        link = f' · <a href="{theme.esc(e["url"])}" target="_blank" rel="noopener noreferrer">open source</a>' if e["url"] else ""
        st.markdown(f'<div class="qz-src"><b>{theme.esc(e["label"])}</b> <span class="small">({theme.esc(qs.TIER_LABEL[e["tier"]])}){link}</span>'
                    f'<div class="qz-pass">{highlight(e["text"], [s for s in spans if s["source_id"] == e["id"]])}</div></div>', unsafe_allow_html=True)
    c = it.get("checks") or {}
    if c:
        theme.meta(f'Checks: written by {c.get("generator")}; solved blind by {c.get("generator")} (picked {c.get("solver_generator", {}).get("answer")}) and '
                   f'{c.get("verifier")} (picked {c.get("solver_verifier", {}).get("answer")}); key, explanation and all alternatives audited against the cited spans. '
                   "This is model agreement, not proof.")
    st.text_input("Note (optional)", key=f"qzr_note_{it['item_id']}", value=r.get("note", ""), max_chars=200)
    with theme.button_row(f"qzr_btns_{it['item_id']}"):
        st.button("Approve", key=f"qzr_ok_{it['item_id']}", type="primary", on_click=decide, args=(it["item_id"], "approved", by), disabled=r["status"] == "approved")
        st.button("Reject", key=f"qzr_no_{it['item_id']}", on_click=decide, args=(it["item_id"], "rejected", by), disabled=r["status"] == "rejected")
        st.button("Clear decision", key=f"qzr_clr_{it['item_id']}", on_click=decide, args=(it["item_id"], "unreviewed", by), disabled=r["status"] == "unreviewed")


def render(user):
    theme.section("Quiz items")
    theme.meta("Every question that passed the automatic checks is listed here with its evidence. Approving a question is your decision, recorded with your name; "
               "students can choose to take only approved questions. Rejected questions are never used.")
    store = QuizStore()
    status = st.selectbox("Show", list(STATUS), format_func=STATUS.get, key="qzr_filter")
    items = store.list_items(None if status == "all" else status, 100)
    if not items:
        theme.meta("No questions yet. They appear after a student builds a quiz.")
    for it in items:
        with st.expander(f'{it["lead_in"][:110]}  ·  {STATUS[it["review"]["status"]]}'):
            item_block(it, user["name"])
    theme.label("Recent builds")
    runs = store.runs(15)
    if not runs:
        theme.meta("No builds yet.")
    for r in runs:
        when = time.strftime("%d %b %H:%M", time.localtime(r["ts"]))
        sc = r.get("scope", {})
        what = ", ".join(sc.get("selected") or []) or sc.get("topic", "")
        st.markdown(f'<div class="small">{when} · {theme.esc(r["user"])} · {theme.esc(what)} · asked {r.get("requested")}, passed {r.get("passed", 0)}, '
                    f'{theme.esc(r.get("outcome", ""))}{" · web used" if r.get("web_used") else ""}'
                    f'{" · rejected: " + theme.esc(str(r.get("rejected_by_stage"))) if r.get("rejected_by_stage") else ""}'
                    f'{" · " + theme.esc(r["message"]) if r.get("message") else ""}</div>', unsafe_allow_html=True)
