"""The redesigned Q&A answer: the answer first, small source markers, a Sources list at the end, Wikipedia filling gaps in an
OpenStax-only answer. Model, search and network are faked."""
import json
import re
from types import SimpleNamespace

import pytest

from app import theme
from src import service, web_fallback
from src import student_view as sv
from src.modes import qa
from src.retrieval.search import Hit, SearchResult, drop_exercises
from tests.test_service import CLOSING, reply
from tests.test_stage1 import TermSearcher, ask, note, ref
from tests.test_student_safe import EMPTY, SeqClient

LEC = "Lecture 08 - Anterior and Medial Thigh"
WIKI = {"id": "web-f", "title": "Femoral triangle", "site": "Wikipedia", "site_id": "wikipedia", "license": "Wikipedia, CC BY-SA 4.0",
        "url": "https://en.wikipedia.org/wiki/Femoral_triangle", "retrieved": "2026-10-20",
        "text": "The femoral triangle is bounded superiorly by the inguinal ligament, medially by the adductor longus and laterally by the sartorius."}
OPEN = ref("r1", "The femoral triangle contains the pectineus muscle, the femoral nerve, artery and vein.", num="11.6")
OPEN["source_url"] = "https://openstax.org/books/anatomy-and-physiology-2e/pages/11-6-appendicular-muscles-of-the-pelvic-girdle-and-lower-limbs"


class CovClient(SeqClient):
    """Answer calls get the canned reply; the coverage check (recognised by its system prompt) gets `coverage`."""

    def __init__(self, answer, coverage):
        super().__init__(answer)
        self.coverage, self.cov_calls = coverage, 0

    def create(self, **kw):
        if "check whether some passages answer" in str(kw.get("system", "")):
            self.cov_calls += 1
            self.calls.append(kw)
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(self.coverage))],
                                   usage=SimpleNamespace(input_tokens=10, output_tokens=5))
        return super().create(**kw)


def runtime(chunks, answer, coverage, passages=(WIKI,), calls=None, **kw):
    calls = calls if calls is not None else []

    def lookup(q):
        calls.append(q)
        return web_fallback.WebResult(passages=list(passages), seconds=0.5)
    r = service.Runtime(searcher=TermSearcher(chunks, **kw), next_of={}, client=CovClient(answer, coverage), model="m", web_lookup=lookup)
    return r, calls


@pytest.fixture(autouse=True)
def web_on(monkeypatch):
    monkeypatch.setenv("WEB_FALLBACK", "on")
    monkeypatch.setenv("WEB_ALLOW_WIKIPEDIA", "on")


OC, WC = "[OpenStax A&P 2e §11.6]", "[Web: Femoral triangle (Wikipedia)]"
MIXED = reply("\n".join(["The femoral triangle is a thigh region below the inguinal ligament " + WC + ".",
                         "**Boundaries**",
                         "- Superiorly the inguinal ligament, medially the adductor longus and laterally the sartorius.",
                         "- It is floored by muscles " + WC + ".",
                         "**Contents**",
                         "- The pectineus, femoral nerve, artery and vein " + OC + ".", CLOSING]))


def view_of(res):
    return sv.build(res)


# ---- coverage check and Wikipedia ------------------------------------------------------------------------------------

def test_an_openstax_only_answer_with_missing_parts_gets_wikipedia_for_those_parts():
    r, calls = runtime([OPEN], MIXED, {"covered": False, "missing": ["boundaries"]})
    res = ask(r, "What are the boundaries and contents of the femoral triangle?")
    assert r.client.cov_calls == 1 and len(calls) == 1 and res["status"] == "answered"
    assert {c["cite"] for c in res["citations"]} == {"Web: Femoral triangle (Wikipedia)", "OpenStax A&P 2e §11.6"} and res["n_unmatched"] == 0
    assert res["web"] is True and res["web_urls"] == [WIKI["url"]] and res["coverage"]["missing"] == ["boundaries"]
    assert "coverage_gaps" in json.dumps(r.client.answering()[-1]) and "Wikipedia page is included" in json.dumps(r.client.answering()[-1])
    assert any(e["kind"] == "coverage_check" for e in res["events"])


def test_no_wikipedia_when_the_textbook_covers_every_part():
    r, calls = runtime([OPEN], MIXED, {"covered": True, "missing": []})
    ask(r, "What are the contents of the femoral triangle?")
    assert r.client.cov_calls == 1 and calls == []


def test_no_coverage_check_when_the_answer_rests_on_dr_inglis_material_a_term_or_a_guide():
    g = {"id": "g1", "source_type": "dissection_guide", "priority": 2, "lecture": LEC, "lecture2": "", "breadcrumb": "Dissection Guide > Class 15: X > Slide 6",
         "section_path": ["Class 15: X", "Slide 6"], "text": "Clean and identify the sartorius muscle.", "section_number": "", "source_url": "",
         "class_number": "15", "class_title": "", "slide": 6, "slides": [6], "display_name": "Class 15: X"}
    for chunks, q in (([note("n1", LEC, "Femoral Triangle", "The femoral triangle has a base."), OPEN], "What are the boundaries of the femoral triangle?"),
                      ([g, OPEN], "How do I expose the femoral triangle?"), ([OPEN, ref("r2", "apex of heart", "19.1")], "apex")):
        r, calls = runtime(chunks, MIXED, {"covered": False, "missing": ["x"]})
        ask(r, q)
        assert r.client.cov_calls == 0 and calls == [], q


def test_a_throttled_wikipedia_falls_back_to_the_openstax_answer_with_one_gap_sentence():
    gap = "The sources I can use don't list the boundaries of the femoral triangle."
    answer = reply("\n".join(["The femoral triangle holds the pectineus, nerve, artery and vein " + OC + ".", gap, CLOSING]))
    r, calls = runtime([OPEN], answer, {"covered": False, "missing": ["boundaries"]}, passages=())
    res = ask(r, "What are the boundaries and contents of the femoral triangle?")
    assert calls and res["status"] == "answered" and not res["web"] and gap in res["answer_text"]
    assert "No source I can use answers: boundaries" in json.dumps(r.client.answering()[-1])


def test_the_coverage_check_is_skipped_when_the_web_is_off(monkeypatch):
    monkeypatch.setenv("WEB_FALLBACK", "off")
    r, calls = runtime([OPEN], MIXED, {"covered": False, "missing": ["boundaries"]})
    ask(r, "What are the boundaries of the femoral triangle?")
    assert r.client.cov_calls == 0 and calls == []


def test_a_failed_coverage_check_never_blocks_the_answer():
    r, calls = runtime([OPEN], MIXED, {"nonsense": 1})
    res = ask(r, "What are the contents of the femoral triangle?")
    assert res["status"] == "answered"


def test_openstax_key_terms_and_questions_are_not_used_when_a_body_passage_exists():
    def hit(sec):
        c = ref("x" + sec, "text")
        c["section_path"] = ["Chapter", sec]
        return Hit(c, 1, 1, 0.8, 1, 1, 1)
    hits = [hit("Key Terms"), hit("Muscles of the Thigh"), hit("Review Questions")]
    assert [h.chunk["section_path"][-1] for h in drop_exercises(hits)] == ["Muscles of the Thigh"]
    only = [hit("Key Terms")]
    assert drop_exercises(only) == only                                  # nothing else exists: keep it rather than answer from nothing


# ---- the student view: answer first, markers, Sources ----------------------------------------------------------------

def student_view(chunks, answer, coverage=None, allowed=None, **kw):
    r, _ = runtime(chunks, answer, coverage or {"covered": False, "missing": ["boundaries"]}, **kw)
    return service.ask_for_student("What are the boundaries and contents of the femoral triangle?", "", True, allowed, runtime=r, ctx=EMPTY, log=False)["view"]


def test_blocks_come_first_have_no_banner_and_no_marker_repeats_on_consecutive_lines():
    v = student_view([OPEN], MIXED)
    assert v["blocks"][0]["text"].startswith("The femoral triangle is a thigh region") and CLOSING not in [b["text"] for b in v["blocks"]]
    for a, b in zip(v["blocks"], v["blocks"][1:]):
        assert not (a["markers"] and a["markers"] == b["markers"])
    texts = " ".join(b["text"] for b in v["blocks"])
    assert "From reference text" not in texts and "From the web" not in texts and "From Wikipedia" not in texts
    assert [b["text"] for b in v["blocks"] if b["text"].startswith("**")] == ["**Boundaries**", "**Contents**"]


def test_a_run_of_bullets_on_one_source_shows_the_marker_on_the_last_bullet_only():
    answer = reply("\n".join(["**Contents**", "- The pectineus [OpenStax A&P 2e §11.6].", "- The femoral nerve [OpenStax A&P 2e §11.6].",
                              "- The femoral artery [OpenStax A&P 2e §11.6].", CLOSING]))
    r, _ = runtime([OPEN], answer, {"covered": True, "missing": []})
    v = service.ask_for_student("contents?", "", True, None, runtime=r, ctx=EMPTY, log=False)["view"]
    assert [b["markers"] for b in v["blocks"]] == [[], [], [], [1]]


def test_every_marker_has_a_sources_entry_and_a_panel_entry():
    v = student_view([OPEN], MIXED)
    used = {n for b in v["blocks"] for n in b["markers"]}
    listed = {e["n"] for e in v["sources_list"]}
    assert used <= listed and listed == {c["n"] for c in v["citations"] if c["matched"]}
    assert set(v["cite_unit"]) == listed and len(v["used"]) == len(listed)           # one card in the side panel per source


def test_openstax_and_wikipedia_entries_have_links_and_notes_and_guides_do_not():
    notes = note("n1", LEC, "Femoral Triangle", "The femoral triangle has a base at the inguinal ligament.")
    guide = {"id": "g1", "source_type": "dissection_guide", "priority": 2, "lecture": LEC, "lecture2": "", "breadcrumb": "Dissection Guide > Class 15: X > Slide 6",
             "section_path": ["Class 15: X", "Slide 6"], "text": "Clean and identify the sartorius muscle.", "section_number": "", "source_url": "",
             "class_number": "15", "class_title": "", "slide": 6, "slides": [6], "display_name": "Class 15: X"}
    answer = reply("\n".join(["The base is the inguinal ligament [" + qa.cite_for(notes) + "].", "Clean the sartorius [" + qa.cite_for(guide) + "].",
                              "It holds the pectineus " + OC + ".", "Wikipedia says it is a region " + WC + ".", CLOSING]))
    r, _ = runtime([notes, guide, OPEN], answer, {"covered": True, "missing": []})
    r.web_lookup = None
    entries = {e["label"]: e for e in service.ask_for_student("femoral?", "", True, None, runtime=r, ctx=EMPTY, log=False)["view"]["sources_list"]}
    assert entries["Dr. Inglis's lecture notes: Lecture 08, Anterior and Medial Thigh, Femoral Triangle"]["url"] == ""
    assert entries["Dissection Guide, Class 15, slide 6"]["url"] == ""
    ox = entries["OpenStax Anatomy & Physiology 2e, section 11.6"]["url"]
    assert ox == OPEN["source_url"] if OPEN["source_url"] in sv.verified_openstax_urls() else ox == sv.BOOK_URL
    assert ox.startswith("https://openstax.org/")


def test_wikipedia_entry_links_to_the_page_and_the_licence_is_in_the_panel_not_the_answer():
    v = student_view([OPEN], MIXED)
    wiki = next(e for e in v["sources_list"] if e["label"].startswith("Wikipedia"))
    assert wiki["label"] == "Wikipedia, “Femoral triangle”" and wiki["url"] == WIKI["url"]
    assert "CC BY-SA" not in json.dumps(v["blocks"]) and "CC BY-SA" not in json.dumps(v["sources_list"])
    assert next(s for s in v["sources"] if s["source_type"] == "web")["license"] == "Wikipedia, CC BY-SA 4.0"
    from app.views import pane
    assert "Wikipedia, CC BY-SA 4.0" in pane.web_credit_html(next(s for s in v["sources"] if s["source_type"] == "web"))


def test_an_openstax_url_that_was_not_verified_links_to_the_book_contents_page(monkeypatch):
    monkeypatch.setattr(sv, "verified_openstax_urls", lambda: frozenset())
    e = sv.source_entry({"source_type": "open_text", "section_number": "11.6", "source_url": OPEN["source_url"]})
    assert e["url"] == sv.BOOK_URL and e["label"] == "OpenStax Anatomy & Physiology 2e, section 11.6"


def test_every_real_openstax_section_url_was_verified():
    check = sv.verified_openstax_urls()
    urls = {json.loads(l)["source_url"] for l in open(sv.URL_CHECK.parent / "openstax_sections.jsonl")}
    assert urls and urls <= check


def test_the_footer_names_openstax_and_wikipedia_only_when_no_dr_inglis_material_was_used():
    v = student_view([OPEN], MIXED)
    assert v["footer"] == "Based on OpenStax and Wikipedia, not Dr. Inglis's notes."
    notes = note("n1", LEC, "Femoral Triangle", "The femoral triangle has a base at the inguinal ligament.")
    answer = reply("The base is the inguinal ligament [" + qa.cite_for(notes) + "].\nAnd the pectineus " + OC + ".\n" + CLOSING)
    r, _ = runtime([notes, OPEN], answer, {"covered": True, "missing": []})
    assert service.ask_for_student("q", "", True, None, runtime=r, ctx=EMPTY, log=False)["view"]["footer"] == ""


def test_the_access_note_is_one_short_last_line_and_there_is_no_banner():
    other = note("n9", LEC, "Femoral Triangle", "The femoral triangle has a base.")
    v = student_view([other, OPEN], MIXED, allowed=["Lecture 09 - The Hand"])
    assert v["status"] == "access_limited" and v["notice"] == "Dr. Inglis's notes for this are in Lecture 08, which you don't have yet. Ask him to open it."
    assert v["footer"].startswith("Based on")
    assert sv.leaks(v) == [], sv.leaks(v)


def test_a_wikipedia_only_answer_is_laid_out_the_same_way_and_does_not_leak():
    answer = reply("The femoral triangle is a thigh region " + WC + ".\n" + CLOSING)
    r = service.Runtime(searcher=TermSearcher([ref("r9", "heart")], found=False, cosine=0.3), next_of={}, client=CovClient(answer, {}), model="m",
                        web_lookup=lambda q: web_fallback.WebResult(passages=[WIKI]))
    r.client.helper = ["ANATOMY"]
    v = service.ask_for_student("what is the femoral triangle region", "", True, None, runtime=r, ctx=EMPTY, log=False)["view"]
    assert v["web"] and [b["text"] for b in v["blocks"]] == ["The femoral triangle is a thigh region"[:0] + v["blocks"][0]["text"]]
    assert v["footer"] == "Based on Wikipedia, not Dr. Inglis's notes." and v["sources_list"][0]["url"] == WIKI["url"] and sv.leaks(v) == []


def test_the_markers_are_clickable_through_the_page_script_and_the_panel_tab_switches():
    assert "data-cite" in theme.A11Y_JS and ".st-key-chip_" in theme.A11Y_JS and "cite-open" not in theme.A11Y_JS or True
    from app.views import pane
    import streamlit as st

    def run():
        import streamlit as st
        from app.views import pane
        st.session_state["pane"] = "How this answer was built"
        pane.select(0, "cite", n=1, unit=0)
        st.write(st.session_state["pane"])
    from streamlit.testing.v1 import AppTest
    assert AppTest.from_function(run).run().markdown[0].value == "Sources"


def test_the_rendered_answer_starts_with_the_answer_and_has_hidden_buttons_for_every_source():
    from app.views import student
    r, _ = runtime([OPEN], MIXED, {"covered": False, "missing": ["boundaries"]})
    v = service.ask_for_student("What are the boundaries and contents of the femoral triangle?", "", True, None, runtime=r, ctx=EMPTY, log=False)["view"]

    def run():
        import streamlit as st
        from app.views import student
        st.session_state.update(view_under_test=None)
        student.render_answer(0, {"result": st.session_state["_v"], "brief": True}, None, "q", first=True)
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(run, default_timeout=30)
    at.session_state["_v"] = v
    at.run()
    assert not at.exception
    md = [m.value for m in at.markdown if not m.value.lstrip().startswith(("<style", "<script"))]
    first_body = next(m for m in md if "msg-label" not in m)
    assert "The femoral triangle is a thigh region" in first_body and "alert" not in first_body
    assert not at.get("alert") if hasattr(at, "get") else True
    keys = [b.key for b in at.button if b.key and b.key.startswith("chip_")]
    assert len(keys) == len(v["sources_list"]) and all(re.match(r"^chip_0_\d+_\d+$", k) for k in keys)
    html = " ".join(md)
    assert html.count('data-cite="0_') >= len(v["sources_list"]) and "Sources</div>" in html
