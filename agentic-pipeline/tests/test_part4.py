"""UI audit Part 4: the professor dashboard (review queue, ledger, reports, access, usage, settings), preview mode, mobile sheet."""
import json
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app import theme
from app.views import professor
from src import auth, review, usage, verified
from src.modes import qa
from tests.test_app import HAND, app, labels, texts, world  # noqa: F401  (fixtures)
from tests.test_service import chunk, reply, CLOSING  # noqa: F401

pytestmark = pytest.mark.skipif(not review.FACTCHECK_PATH.exists(), reason="reports/factcheck_all.json missing")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def items():
    return review.queue(review.load_report(), {})


def tmp_files(world):
    return qa.FLAGS_PATH, verified.FIXES_PATH


# ---- the review card ---------------------------------------------------------------------------------------------------

def test_a_review_card_has_the_line_why_and_a_meta_row_and_hides_the_details(world):
    at = app("prof")
    body = texts(at)
    assert "Why it was flagged." in body and "metarow" in body and "Show details" in [e.label for e in at.expander]
    card = professor.item_card(review.queue(review.load_report())[0])
    assert "Second check" not in card and "onfidence" not in card and "Basis" not in card         # details are behind the expander
    assert "Second check" in professor.item_details(review.queue(review.load_report())[0])
    assert "Page 1 of" in body and "Items per page" in [s.label for s in at.selectbox]
    assert {"Lecture", "How serious", "Kind of issue", "Show"} <= {s.label for s in at.selectbox}


def test_shown_in_student_answers_is_an_emphasised_chip_only_when_true(items):
    item = dict(next(i for i in items if i["kind"] == "likely_factual"))
    item["decision"] = {"status": "open", "seen_in_question": True}
    assert "chip chip-flag" in professor.item_card(item) and "Shown in student answers" in professor.item_card(item)
    item["decision"] = {"status": "open"}
    assert "Shown in student answers" not in professor.item_card(item)


def test_pager_next_goes_to_page_2(world):
    at = app("prof")
    before = texts(at)
    n = int(re.search(r"Page 1 of (\d+)", before).group(1))
    assert n >= 2
    next(b for b in at.button if b.key == "rq_next_start_here" or b.label == "Next" and not b.disabled).click().run()
    assert "Page 2 of" in texts(at)


def test_tab_is_called_student_reports_and_each_tab_explains_itself(world):
    at = app("prof")
    names = [t.label for t in at.tabs]
    assert any(n.startswith("Student reports") for n in names) and not any("Q&A flags" in n for n in names)
    body = texts(at)
    for line in (professor.TAB_HELP["start_here"], professor.TAB_HELP["typo"]):
        assert theme.esc(line) in body or line in body


# ---- deciding: Ctrl+Enter can never decide; a correction is required ------------------------------------------------------

def decide_buttons(at):
    return [b for b in at.button if b.key and re.match(r"^(noop|ok|fine|reword)_", b.key)]


def test_the_first_submit_button_of_a_decision_form_is_a_hidden_no_op(world):
    at = app("prof")
    assert any(e.label == "Decide" for e in at.expander)                                          # the Decide panel exists
    first_form = [b for b in at.button if b.key and re.match(r"^(noop|ok|fine|reword)_", b.key)][:4]
    assert [b.key.split("_")[0] for b in first_form] == ["noop", "ok", "fine", "reword"]          # the shortcut hits the no-op first
    assert re.search(r'st-key-noop_"\] \{ display: none', theme.CSS)
    assert "Confirm error: this will show the corrected line to students." in texts(at)


def test_the_no_op_and_an_empty_confirm_record_nothing(world):
    at = app("prof")
    noop = next(b for b in at.button if b.key and b.key.startswith("noop_"))
    noop.click().run()
    assert verified.load_fixes() == []
    ok = next(b for b in at.button if b.key and b.key.startswith("ok_"))
    ok.click().run()                                                                              # no correction typed
    assert verified.load_fixes() == [] and not at.exception


def test_confirm_error_with_a_correction_records_one_fix_and_hands_back_a_toast(world):
    at = app("prof")
    key = next(b.key for b in at.button if b.key and b.key.startswith("ok_"))[3:]
    at.text_area(key=f"corr_{key}").input("The corrected wording.")
    next(b for b in at.button if b.key == f"ok_{key}").click().run()
    assert not at.exception, [e.value for e in at.exception]                                       # (a stateful-widget key was once set after use)
    assert any("Recorded: Confirmed as an error" in t.value for t in at.toast)
    fixes = verified.load_fixes()
    assert len(fixes) == 1 and fixes[0]["correction"] == "The corrected wording." and fixes[0]["decision"] == "confirm_error"
    at.run()
    assert not at.exception and "Recorded:" not in texts(at)                                       # a toast, not a banner: nothing shifts


def test_bulk_action_touches_only_open_typos_of_one_lecture(world, items):
    lecture = next(i["lecture"] for i in items if i["kind"] == "typo")
    todo = review.bulk_typo_items(items, lecture)
    assert todo and all(i["kind"] == "typo" and i["lecture"] == lecture for i in todo)
    n = review.mark_typos_reviewed(items, lecture, "Dr. Inglis")
    assert n == len(todo)
    fixes = verified.load_fixes()
    assert len(fixes) >= 1 and {f["decision"] for f in fixes} == {"notes_correct"} and {f["lecture"] for f in fixes} == {lecture}
    assert not [i for i in review.queue(review.load_report()) if i["kind"] == "typo" and i["lecture"] == lecture and i["decision"]["status"] != "resolved"]


def test_bulk_action_asks_first_and_never_offers_confirm_error(world, items):
    lecture = next(i["lecture"] for i in items if i["kind"] == "typo")
    at = app("prof")
    at.session_state["rq_lecture"] = lecture
    at.run()
    ask = next(b for b in at.button if b.key and b.key.startswith("bulk_ask_"))
    assert re.search(r"Mark all \d+ typos in this lecture as reviewed", ask.label) and verified.load_fixes() == []
    ask.click().run()
    body = texts(at)
    assert "typos as reviewed?" in body and "changes nothing students read" in body and verified.load_fixes() == []     # a count, then a confirmation
    assert not any("confirm" in b.label.lower() and "all" in b.label.lower() for b in at.button)


# ---- ledger ----------------------------------------------------------------------------------------------------------------

def add_fix():
    verified.write_jsonl(verified.FIXES_PATH, [{"id": "vf-0001", "lecture": "Lecture 99", "breadcrumb": "Lecture 99 > A", "notes_quote": "Original line",
                                                  "correction": "Corrected line", "decision": "confirm_error", "by": "Dr. Inglis", "date": "2026-10-07"}])


def test_ledger_shows_before_and_after_and_undo_has_a_confirmation_step(world):
    add_fix()
    at = app("prof")
    body = texts(at)
    assert "Before (the notes)" in body and "After (what students see)" in body and "Original line" in body and "Corrected line" in body
    undo = next(b for b in at.button if b.key == "undo_vf-0001")
    assert undo.proto.type == "secondary"                                                          # a normal button, not red
    undo.click().run()
    assert "Undo vf-0001?" in texts(at) and len(verified.load_fixes()) == 1                         # asked, nothing removed yet
    next(b for b in at.button if b.key == "undo_no_vf-0001").click().run()
    assert len(verified.load_fixes()) == 1
    next(b for b in at.button if b.key == "undo_vf-0001").click().run()
    next(b for b in at.button if b.key == "undo_yes_vf-0001").click().run()
    assert verified.load_fixes() == []


# ---- student reports -----------------------------------------------------------------------------------------------------

def test_student_reports_are_listed_and_can_be_marked_handled(world):
    qa.append_flag({"type": "student_report", "student": "s_hand", "question": "What are the walls?", "answer": "Six walls.",
                    "cites": ["Lecture 9 > Walls"], "reason": "The answer is wrong", "comment": "it is five"}, key="r1")
    at = app("prof")
    body = texts(at)
    assert "The answer is wrong" in body and "it is five" in body and "What are the walls?" in body
    assert "Student reports (1)" in [t.label for t in at.tabs]
    next(b for b in at.button if b.label == "Mark as handled").click().run()
    assert review.open_student_reports() == [] and "Nothing reported yet." in texts(at)
    row = json.loads(qa.FLAGS_PATH.read_text().splitlines()[0])
    assert row["status"] == "handled" and row["comment"] == "it is five"                           # kept, just no longer open


# ---- access --------------------------------------------------------------------------------------------------------------

def test_revoke_all_asks_with_a_count_and_only_then_acts(world):
    at = app("prof")
    next(e for e in at.expander if e.label.startswith("Hand Student")).proto
    revoke = next(b for b in at.button if b.key == "danger_revoke_s_hand")
    revoke.click().run()
    body = texts(at)
    assert "Remove access to every lecture?" in body and "loses 1 lecture(s)" in body
    assert auth.get_user("s_hand")["allowed_lectures"] == [HAND]
    next(b for b in at.button if b.key == "acc_yes_s_hand").click().run()
    assert auth.get_user("s_hand")["allowed_lectures"] == []


def test_grant_all_shows_how_many_lectures_change(world):
    at = app("prof")
    next(b for b in at.button if b.label == "Grant all" and b.key and "s_none" in str(b.key) or b.label == "Grant all").click().run()
    assert "Grant access to every lecture?" in texts(at) or "gets" in texts(at)


def test_two_files_with_the_same_title_get_a_short_unique_suffix():
    files = [{"title": "Lecture 16 - A", "lecture_id": "L16-aaaaaa"}, {"title": "Lecture 16 - A", "lecture_id": "L16-bbbbbb"},
             {"title": "Lecture 17 - B", "lecture_id": "L17-cccccc"}]
    assert [professor.access_label(f, files) for f in files] == ["Lecture 16 - A · aaaaaa", "Lecture 16 - A · bbbbbb", "Lecture 17 - B"]


# ---- notes library: no server paths anywhere on the professor pages ---------------------------------------------------------

def test_no_server_paths_in_the_professor_pages(world):
    at = app("prof")
    body = texts(at)
    for bad in ("data/", ".venv", "src/", "reports/", "/Users/", ".jsonl"):
        assert bad not in body, bad
    assert "ANA407 Class 28 - The Posterior Abdominal Wall.docx" in body                          # file names, not paths


# ---- usage and settings -----------------------------------------------------------------------------------------------------

def test_usage_cost_is_split_by_day_and_type_and_shown_as_a_table():
    s = usage.summary([{"ts": "2026-10-08T10:00:00", "mode": "qa", "kind": "chat_answer", "cost": 0.01},
                       {"ts": "2026-10-08T11:00:00", "mode": "qa", "kind": "professor_preview", "cost": 0.02},
                       {"ts": "2026-10-09T11:00:00", "mode": "guide", "kind": "guide_step", "cost": 0.03}])
    assert s["cost_by_day_kind"] == {"2026-10-08": {"Student chat": 0.01, "Professor preview": 0.02}, "2026-10-09": {"Student Guide": 0.03}}


def test_usage_page_has_the_table_and_the_chart_has_axis_titles(world):
    usage.log_event({"mode": "qa", "kind": "chat_answer", "user": "s_hand", "question": "q", "status": "answered", "cost": 0.0123, "lectures": [HAND]})
    at = app("prof")
    assert any("Student chat" in str(df.value.columns.tolist()) for df in at.dataframe)
    src = Path(theme.__file__).read_text()
    assert 'title="Cost (US dollars)"' in src and 'title="Day (UTC)"' in src and 'format="$.2f"' in src


def test_settings_have_headings_and_helper_text(world):
    body = texts(app("prof"))
    assert "Spending limit" in body and "Answer style" in body
    assert "Students never see the amount." in body and "Brief answers are about five lines." in body


# ---- preview mode ----------------------------------------------------------------------------------------------------------

def preview_script():
    import streamlit as st
    from app import nav
    from app.views import student
    me = nav.current_user()
    nav.PAGES = {"dashboard": st.Page(lambda: None, title="D", url_path="d"), "chat": st.Page(lambda: None, title="c", url_path="c"),
                 "guide": st.Page(lambda: None, title="g", url_path="g"), "quiz": st.Page(lambda: None, title="q", url_path="q")}
    student.page(nav.preview_user(me) if me["role"] == "professor" else me, real_user=me)


def test_preview_has_an_unmistakable_bar_with_an_exit_and_a_students_own_session_never_does(world):
    at = AppTest.from_function(preview_script, default_timeout=60)
    at.session_state["auth_user"], at.session_state["preview_as"] = "prof", "s_hand"
    at.run()
    body = texts(at)
    assert "Previewing as Hand Student" in body and "access to 1 lecture" in body and "You are seeing exactly what they see." in body
    assert any(str(l.proto.label) == "Exit preview" for l in at.get("page_link"))
    st_at = AppTest.from_function(preview_script, default_timeout=60)
    st_at.session_state["auth_user"] = "s_hand"
    st_at.run()
    assert "Previewing as" not in texts(st_at) and "Exit preview" not in " ".join(str(l.proto.label) for l in st_at.get("page_link"))


# ---- phone and tablet: bottom sheet, no empty tab bar, tap targets -------------------------------------------------------------------

def test_no_pane_tab_bar_before_there_is_an_answer(world):
    at = app("s_hand", body_done=True)
    assert "Sources" not in [str(b.proto) for b in at.get("button_group")] if at.get("button_group") else True
    assert "pane-marker" not in " ".join(m.value for m in at.markdown)


def test_choosing_a_chip_marks_the_pane_as_a_sheet_with_a_close_button(world):
    spy, rt = world
    spy.chunks[:] = [chunk("- A line about the wall of the middle ear cavity.", lecture=HAND)]
    rt.client.reply = reply(f"A line about the wall of the middle ear cavity [{HAND} > Walls]\n{CLOSING}")
    at = app("s_hand", body_done=True)
    at.chat_input[0].set_value("walls?").run()
    at.run()
    assert "sheet-open" not in " ".join(m.value for m in at.markdown) and not any(b.key == "sheet_close_btn" for b in at.button)
    next(b for b in at.button if b.key and re.match(r"^chip_\d+_\d+_\d+$", b.key)).click().run()
    assert "sheet-open" in " ".join(m.value for m in at.markdown)
    close = next(b for b in at.button if b.key == "sheet_close_btn")
    close.click().run()
    assert at.session_state["sel"] is None and "sheet-open" not in " ".join(m.value for m in at.markdown)


def test_the_stylesheet_has_the_sheet_and_44px_tap_targets():
    css = theme.CSS
    assert re.search(r"@media \(max-width: 1130px\) \{\s*\[data-testid=\"stColumn\"\]:has\(\.sheet-open\) \{ position: fixed", css)
    assert re.search(r"@media \(max-width: 960px\) \{[^@]*st-key-chip_\"\] button[^}]*min-height: 44px", css, re.S)
    assert "bottom: 0" in css and "z-index: 120" in css


def test_the_empty_progress_track_is_visible_on_the_cream_page():
    assert re.search(r'\[data-testid="stProgressBarTrack"\] \{ background: var\(--progress-track\) !important; border: 1px solid var\(--input-border\)', theme.CSS)
    assert theme.TOKENS["progress-track"] != theme.TOKENS["surface"]
