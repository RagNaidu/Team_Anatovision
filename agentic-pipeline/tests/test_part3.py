"""UI audit Part 3: citations and the Sources pane data, trust line, error reports, and the Guide's describe-first flow."""
import json
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import citations as cit
from src import student_report as sr
from src import student_view as sv
from src import trust, usage
from src.modes import guide, qa
from tests.test_app import HAND, app, labels, texts, world  # noqa: F401  (fixtures)
from tests.test_service import CLOSING, chunk, isolated, reply, runtime  # noqa: F401
from tests.test_student_safe import guide_script, run_student

ROOT = Path(__file__).resolve().parents[1]
CITE = f"[{HAND} > Walls]"
INDENTED = ("- Triangular landmark\n- Borders\n  - Superior - inguinal canal\n  - Medial - adductor longus muscle\n"
            "  - Lateral - sartorius muscle\n- Floor formed by pectineus and iliopsoas muscles")


# ---- citations: one supporting line, per sentence ---------------------------------------------------------------

def one_chunk(text):
    return [{"cite": f"{HAND} > Walls", "breadcrumb": f"{HAND} > Walls", "source_type": "notes", "text": text}]


def test_each_sentence_highlights_only_its_own_supporting_line():
    chunks = one_chunk(INDENTED)
    r = cit.parse_answer(f"The medial border is the adductor longus muscle {CITE}\nThe floor is formed by pectineus and iliopsoas muscles {CITE}", chunks)
    u1, u2 = r["units"]
    (s1,), (s2,) = u1["support"][1], u2["support"][1]
    assert len(u1["support"][1]) == 1 and INDENTED[s1[0]:s1[1]].strip() == "- Medial - adductor longus muscle"
    assert INDENTED[s2[0]:s2[1]].strip().startswith("- Floor formed by pectineus")
    assert all(len(sup["spans"]) <= 1 for c in r["citations"] for sup in c["support"])         # never three lines for one citation


def test_passage_text_keeps_its_indentation_and_line_breaks():
    html_ = cit.passage_html(INDENTED, [])
    assert "<br>" not in html_ and 'class="pl pl-1 pl-b">Superior' in html_ and 'class="pl pl-0 pl-b">Borders' in html_   # one div per line, level from the indent
    assert html_.count('class="pl ') == 6 and "\n" not in html_


# ---- the student view: titles, labels, trust line -----------------------------------------------------------------

@pytest.mark.parametrize("breadcrumb,title,crumb", [
    ("Lecture 16b - Middle Ear > III. Middle Ear (Tympanic Cavity) > 3. Walls of the Middle Ear", "Lecture 16b · Middle Ear",
     "III. Middle Ear (Tympanic Cavity) › 3. Walls of the Middle Ear"),
    ("Lecture 08 - Anterior and Medial Thigh > Anterior and Medial Thigh > The Femoral Triangle", "Lecture 08 · Anterior and Medial Thigh",
     "Anterior and Medial Thigh › The Femoral Triangle"),
    ("OpenStax A&P 2e > Chapter 1 > Sec", "OpenStax A&P 2e", "Chapter 1 › Sec")])
def test_long_path_is_split_into_a_title_and_a_muted_breadcrumb(breadcrumb, title, crumb):
    assert sv.split_path(breadcrumb) == (title, crumb)


@pytest.mark.parametrize("kind,lecture,sec,label", [("notes", "Lecture 16b - Middle Ear", "", "Notes · L16b"),
                                                   ("notes", "ANA407 Class 28 - The Posterior Abdominal Wall", "", "Notes · ANA407"),
                                                   ("open_text", "Chapter 14", "14.1", "OpenStax · §14.1")])
def test_short_chip_labels(kind, lecture, sec, label):
    assert sv.short_label(kind, lecture, sec) == label


def test_notes_date_is_when_the_index_was_loaded_never_a_files_old_date(tmp_path):
    import os, time
    index = tmp_path / "chunks.jsonl"; index.write_text("x")
    sections = tmp_path / "sections.jsonl"
    sections.write_text("\n".join(json.dumps(r) for r in [
        {"lecture_title": "Lecture 1", "source_file": "a.docx"},
        {"lecture_title": "Lecture 2", "source_file": "b.docx", "uploaded": "2026-10-09T10:00:00"}]))
    d = trust.lecture_dates(sections, index)
    assert re.fullmatch(r"\d{4}-\d\d-\d\d", d["Lecture 1"]) and d["Lecture 2"] == "2026-10-09"
    old = time.mktime((2014, 9, 10, 0, 0, 0, 0, 0, -1)); os.utime(index, (old, old))
    assert trust.index_date(index) == "" and "Lecture 1" not in trust.lecture_dates(sections, index)      # a 2014 date is never shown
    assert trust.pretty("2026-10-06") == "6 Oct 2026" and trust.pretty("") == ""


def test_the_answer_carries_chip_labels_per_sentence_support_and_a_trust_line():
    from tests.test_student_safe import rt_for
    from src import service
    rt = rt_for([chunk(INDENTED, lecture=HAND)], reply(f"The medial border is the adductor longus muscle {CITE}\n{CLOSING}"))
    view = service.ask_for_student("borders?", "", True, None, runtime=rt, ctx={"confirmed": [], "doubtful": [], "fixes": []})["view"]
    assert view["citations"][0]["short"] == "Notes · L09" and view["used"] == [0]
    assert view["units"][0]["support"] and view["trust"]["notes"] is True and view["trust"]["textbook"] is False
    src = view["sources"][0]
    assert src["title"] == "Lecture 09 · The Hand" and src["crumb"] == "Walls" and sv.leaks(view) == []


def test_card_lines_are_shown_once():
    card = {"what_you_should_see": [{"text": "Mucosa lines the lumen of the tube", "mark": None}],
            "landmarks_relations": [{"text": "Mucosa lines the lumen", "mark": None}, {"text": "Deep to the serosa", "mark": None}],
            "identify_these": [{"text": "Mucosa", "mark": None}, {"text": "Serosa", "mark": None}, {"text": "serosa", "mark": None}],
            "variation_if_stated": []}
    out = sv.dedupe_card(card)
    assert [i["text"] for i in out["landmarks_relations"]] == ["Deep to the serosa"]
    assert [i["text"] for i in out["identify_these"]] == ["Mucosa", "Serosa"]          # exact repeats go, short names stay


def test_the_no_consequence_line_is_not_shown_to_students():
    turn = {"detail": {"station": 1, "verdict": "no", "feedback": "Look again.", "should_see": "a wall", "consequence": guide.NO_CONSEQUENCE}}
    assert sv.guide_turn(turn)["detail"]["consequence"] == ""
    turn["detail"]["consequence"] = "What the notes say can go wrong: x"
    assert sv.guide_turn(turn)["detail"]["consequence"].startswith("What the notes say")


def test_the_prompt_forbids_meta_language():
    for text in (qa.system_prompt(True, "student"), qa.system_prompt(False)):
        assert 'Never write "the sources"' in text and "the sources list" in text


# ---- error reports -------------------------------------------------------------------------------------------------

def test_a_report_is_an_open_flag_through_the_existing_flags_function(tmp_path, monkeypatch):
    monkeypatch.setattr(qa, "FLAGS_PATH", tmp_path / "flags.jsonl")
    assert sr.report_error("s1", "walls?", "The walls are six.", ["Lecture 9 > Walls"], sr.REASONS[1], "  not what the notes say  ")
    (row,) = [json.loads(l) for l in (tmp_path / "flags.jsonl").read_text().splitlines()]
    assert row["type"] == "student_report" and row["status"] == "open" and row["student"] == "s1"
    assert row["reason"] == sr.REASONS[1] and row["comment"] == "not what the notes say" and row["cites"] == ["Lecture 9 > Walls"]
    with pytest.raises(ValueError):
        sr.report_error("s1", "q", "a", [], "because I said so")
    assert len((tmp_path / "flags.jsonl").read_text().splitlines()) == 1


def test_student_screens_never_read_the_flags_file():
    for f in ("student.py", "pane.py", "report.py", "guide_ui.py"):
        text = (ROOT / "app" / "views" / f).read_text()
        assert not re.search(r"FLAGS_PATH|read_jsonl|flags\.jsonl|load_flags|open_conflicts", text), f
    assert "read_jsonl" not in Path(sr.__file__).read_text() and "open(" not in Path(sr.__file__).read_text()   # the report module only writes


def answer_script():
    pass


def test_reporting_from_the_screen_writes_a_flag_and_says_thanks_without_showing_other_flags(world):
    spy, rt = world
    qa.append_flag({"type": "student_report", "student": "someone_else", "reason": "SECRET other student's report"}, key="x")
    at = app("s_hand", body_done=True)
    at.chat_input[0].set_value("What are the walls?").run()
    at.run()
    assert not at.exception
    opens = [e.label for e in at.expander]
    assert "Report an error" in opens and "Report a problem" in opens                    # inline expanders, not floating popovers
    assert "SECRET" not in run_student(at)
    at.selectbox(key="rr_a1").select(sr.REASONS[0])
    at.text_area(key="rc_a1").input("wrong")
    next(b for b in at.button if b.label == "Send report").click().run()
    assert "Thanks, sent to Dr. Inglis." in texts(at) and "SECRET" not in run_student(at)
    rows = [json.loads(l) for l in qa.FLAGS_PATH.read_text().splitlines()]
    mine = [r for r in rows if r["type"] == "student_report" and r["student"] == "s_hand"]
    assert len(mine) == 1 and mine[0]["question"] == "What are the walls?" and mine[0]["reason"] == sr.REASONS[0]


# ---- the Sources pane -------------------------------------------------------------------------------------------------

def test_sources_pane_shows_used_passages_first_and_the_rest_collapsed(world):
    spy, rt = world
    spy.chunks[:] = [chunk(INDENTED, lecture=HAND), chunk("- Another passage that was only looked at.", lecture=HAND, cid="n9")]
    rt.client.reply = reply(f"The medial border is the adductor longus muscle {CITE}\n{CLOSING}")
    at = app("s_hand", body_done=True)
    at.chat_input[0].set_value("borders?").run()
    at.run()
    body = texts(at)
    assert "Used in this answer" in body and "Sources for the answer above" in body and "Notes: Dr. Inglis" in body
    assert [e.label for e in at.expander if e.label.startswith("Also looked at")] == ["Also looked at (1)"]
    chips = [b for b in at.button if b.key and re.match(r"^chip_\d+_\d+_\d+$", b.key)]
    assert chips and chips[0].label == "Source 1"                       # the hidden button a marker presses
    assert 'class="srcnum">1<' in body and "Lecture 09" in body


def test_choosing_a_source_marker_opens_the_sources_tab_and_back_is_a_normal_button(world):
    spy, rt = world
    spy.chunks[:] = [chunk(INDENTED, lecture=HAND)]
    rt.client.reply = reply(f"The medial border is the adductor longus muscle {CITE}\n{CLOSING}")
    at = app("s_hand", body_done=True)
    at.chat_input[0].set_value("borders?").run()
    at.run()
    at.session_state["pane"] = "How this answer was built"
    at.run()
    next(b for b in at.button if b.key and b.key.startswith("chip_1_")).click().run()
    assert at.session_state["pane"] == "Sources"                           # a marker switches the right panel to Sources
    body = texts(at)
    assert "Source 1" in body and "Supports:" in body and "The medial border is the adductor longus muscle" in body
    back = next(b for b in at.button if b.label == "Back to all sources")
    assert back.proto.type == "secondary"
    back.click().run()
    assert at.session_state["sel"] is None and at.session_state["pane"] == "Sources"


def test_a_doubtful_line_gets_its_own_marker_button(world, monkeypatch):
    spy, rt = world
    text = "- Plain line.\n- Doubt me line.\n"
    spy.chunks[:] = [chunk(text, lecture=HAND)]
    item = {"lecture": HAND, "breadcrumb": f"{HAND} > Walls", "claim_quote": "Doubt me line", "issue": "x", "severity": "high",
            "confidence": 0.9, "tier": "second_look", "type": "factual", "verification": {"reason": "r", "verdict": "doubtful"}}
    monkeypatch.setattr(qa, "load_context", lambda: {"confirmed": [], "doubtful": [item], "fixes": []})
    rt.client.reply = reply(f"Plain line {CITE}\nThe doubted line (flagged for review, see fact-check) {CITE}\n{CLOSING}", doubtful_used=["D1"])
    at = app("s_hand", body_done=True)
    at.chat_input[0].set_value("walls?").run()
    at.run()
    assert any(b.label == "Check before relying on this" and b.key.startswith("sflag_") for b in at.button)


def test_the_send_arrow_counter_and_scroll_script_exist():
    from app import theme
    assert "av-count" in theme.A11Y_JS and "480" in theme.A11Y_JS and "scrollIntoView" in theme.A11Y_JS
    assert "stChatInputSubmitButton" in theme.CSS and ":disabled" in theme.CSS


# ---- the Guide ---------------------------------------------------------------------------------------------------------

def test_the_guide_hides_the_notes_until_described_or_peeked_and_logs_a_peek(world, monkeypatch, tmp_path):
    at = AppTest.from_function(guide_script, default_timeout=60).run()
    assert "wall a" not in run_student(at) and "Describe what you see" in run_student(at)
    assert "Show the notes" in labels(at) and "Check my description" in labels(at)
    log = []
    monkeypatch.setattr(usage, "log_event", lambda e: log.append(e))
    next(b for b in at.button if b.label == "Show the notes").click().run()
    assert "wall a" in run_student(at) and "Show the notes" not in labels(at)
    assert log and log[0]["kind"] == "guide_peek" and log[0]["event"] == "peek" and log[0]["station"] == 1
    assert usage.kind_of(log[0]) == "guide_peek"


def test_peeks_are_counted_apart_from_guide_steps():
    s = usage.summary([{"ts": "2026-10-09T10:00:00", "mode": "guide", "kind": "guide_peek", "user": "s1"},
                       {"ts": "2026-10-09T10:00:00", "mode": "guide", "kind": "guide_step", "user": "s1", "cost": 0.01}])
    assert s["guide"]["steps"] == 1 and s["guide"]["peeks"] == 1 and s["chat"]["questions"] == 0


def test_an_empty_description_is_asked_for_not_judged(world):
    at = AppTest.from_function(guide_script, default_timeout=60).run()
    next(b for b in at.button if b.label == "Check my description").click().run()
    assert "Describe it first" in texts(at) and "Not quite yet" not in texts(at)


def test_pass_and_not_yet_are_different_alerts_and_locked_stations_answer(world):
    at = AppTest.from_function(guide_script, default_timeout=60).run()
    at.text_area[0].set_value("a wall")
    next(b for b in at.button if b.label == "Check my description").click().run()
    body = texts(at)
    assert "alert alert-warning" in body and "Not quite yet" in body and "Look again at:" in body
    assert "no consequence" not in body.lower() and "ask your instructor" not in body.lower()
    locked = next(b for b in at.button if b.key and b.key.startswith("step_locked_"))
    assert not locked.disabled                                                      # a locked station can be clicked ...
    locked.click().run()
    assert "Finish the earlier stations first." in texts(at)                         # ... and says why it won't open
    at.run()
    assert "Finish the earlier stations first." not in texts(at)                     # once: it does not linger


def test_the_guide_shows_real_station_names_and_a_progress_line(world):
    at = AppTest.from_function(guide_script, default_timeout=60).run()
    body = texts(at)
    assert "1. Walls" in " ".join(labels(at)) and "2. Floor" in " ".join(labels(at))
    assert "0 of 2 stations done" in body or any("0 of 2 stations done" in str(p.proto) for p in at.get("progress"))
    assert "Station 1 of 2 ·" in body and "Previous station" in labels(at) and "Next station" in labels(at)
    assert body.count("Sample mode") <= 1                                           # the banner is not repeated on every step


# ---- a withheld line shows ONLY the neutral sentence --------------------------------------------------------------

def test_a_withheld_line_leaks_no_claim_text_anywhere_a_student_can_see():
    from src import service
    from tests.test_student_safe import rt_for, CTX
    claim = "The superior border is the subinguinal canal, bounded by the inguinal ligament"
    from tests.test_student_safe import REVIEW_Q, TEXT
    from src.modes import qa
    c99 = chunk(TEXT, lecture="Lecture 99 - Test")
    own = f"[{qa.cite_for(c99)}]"                     # a citation that matches the retrieved passage (others are now dropped)
    leaky = f"{claim}: {sv.NEUTRAL_REVIEW} {own}\nThe floor is pectineus {own}\n{CLOSING}"
    rt = rt_for([c99], reply(leaky, under_review_addressed=["U1"]))
    view = service.ask_for_student("borders?", "", True, None, runtime=rt, ctx=CTX)["view"]
    blob = sv.dumps(view)
    assert "subinguinal" not in blob and "inguinal ligament" not in blob                     # not in the answer, chips, support or pane
    assert view["units"][0]["text"] == sv.NEUTRAL_REVIEW and view["units"][0]["reviewing"] is True
    assert REVIEW_Q not in blob and view["answer_text"].count(sv.NEUTRAL_REVIEW) == 1
    assert sv.leaks(view) == []


def test_scrub_replaces_the_whole_sentence_and_drops_the_second_half():
    text, replaced = sv.scrub_text(f"Intro line. The border is X: {sv.NEUTRAL_REVIEW}")
    assert replaced and text == f"Intro line. {sv.NEUTRAL_REVIEW}"
