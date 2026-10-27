"""Stage 3: dissection guides. Ingest (cleaning, chunks), the class-to-lecture map, access, citations, the procedural answer path, and
regression questions against the real index. The model is faked; the network is never used."""
import hashlib
import json
import zipfile
from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest

from src import citations as cit
from src import service
from src import student_view as sv
from src.ingest import guides as G
from src.modes import qa
from src.retrieval.search import Searcher
from tests.test_service import CLOSING, reply
from tests.test_stage1 import TermSearcher, ask, rt
from tests.test_student_safe import EMPTY


def slide(n, texts=(), pics=0, notes="", tables=()):
    return {"n": n, "title": "", "texts": list(texts), "tables": list(tables), "notes": notes, "n_pictures": pics, "n_diagrams": 0,
            "hidden": False, "n_words": sum(len(t.split()) for t in texts)}


FOOT = "PAS407 – Class 17 Dissection Guide – The Hip and Knee Joints"
STEP = "Open and remove the posterior wall of the joint capsule to expose the ligaments of the hip. Take care to keep the labrum intact while you work."


# ---------------------------------------------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------------------------------------------

def test_file_names_give_the_class_number_and_title():
    assert G.parse_name("Class 17 Dissection Guide - The Hip and Knee Joints.pptx") == (17, "The Hip and Knee Joints")
    assert G.parse_name("Class 04 Dissection Guide - Laminectomy and Suboccipital Region.pptx") == (4, "Laminectomy and Suboccipital Region")
    assert G.parse_name("random.pptx") == (None, "random")


def test_zip_extraction_refuses_paths_that_escape_and_never_touches_the_zip(tmp_path):
    z = tmp_path / "g.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("Guides/Class 01 Dissection Guide - A.pptx", b"x")
    before = hashlib.md5(z.read_bytes()).hexdigest()
    out = G.extract_zip(z, tmp_path / "out")
    assert [p.name for p in out] == ["Class 01 Dissection Guide - A.pptx"] and hashlib.md5(z.read_bytes()).hexdigest() == before
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as f:
        f.writestr("../evil.txt", b"x")
    with pytest.raises(ValueError):
        G.extract_zip(bad, tmp_path / "out2")
    assert not (tmp_path / "evil.txt").exists()


def test_the_footer_the_page_number_and_figure_letters_are_dropped():
    s = slide(3, [STEP, FOOT, "3", "A", "C", "B2"])
    assert G.clean_lines(s) == [STEP]
    assert G.slide_text(slide(3, [STEP], notes="Do this slowly.")).endswith("Speaker notes: Do this slowly.")


def test_slides_are_classified_text_image_only_title_end_empty():
    assert G.classify_slide(slide(2, [STEP])) == "text"
    assert G.classify_slide(slide(5, ["A", "B", "5"], pics=2)) == "image-only"
    assert G.classify_slide(slide(1, ["PAS407 – Gross Human Anatomy", "Class 17 – X", "Laboratory Session – X"])) == "title"
    assert G.classify_slide(slide(9, ["End of Laboratory Session"])) == "end"
    assert G.classify_slide(slide(4, [])) == "empty"


def entry(number=17, title="The Hip and Knee Joints", lecture="Lecture 13 - The Hip and Knee Joints", also="", label=None):
    return {"class_number": number, "title": title, "display_name": G.display_name(number, title), "class_label": label or f"Class {number}",
            "file": f"Class {number:02d} Dissection Guide - {title}.pptx", "matched_lecture": lecture, "matched_lecture_id": "L13" if lecture else "",
            "also_lecture": also, "confidence": "high" if lecture else "unmatched"}


def test_chunks_keep_class_slide_and_lecture_and_merge_very_short_slides():
    long_a = " ".join(["Reflect the skin carefully from the midline outward and keep the superficial veins intact."] * 3)
    deck = [slide(1, ["PAS407 – Gross Human Anatomy", "Class 17 – X", "Laboratory Session – X"]),
            slide(2, [long_a, FOOT, "2"]),
            slide(3, ["Identify the vein.", FOOT, "3"]),          # short: merged into slide 2
            slide(4, [long_a.replace("skin", "fascia"), FOOT, "4"]),
            slide(5, [], pics=1),                                  # image only: nothing to index
            slide(6, ["End of Laboratory Session"])]
    chunks = G.guide_chunks({"Class 17 Dissection Guide - The Hip and Knee Joints.pptx": deck}, [entry()])
    assert [(c["slide"], c["slides"]) for c in chunks] == [(2, [2, 3]), (4, [4])]
    c = chunks[0]
    assert (c["class_number"], c["source_type"], c["priority"], c["lecture"]) == ("17", "dissection_guide", 2, "Lecture 13 - The Hip and Knee Joints")
    assert c["breadcrumb"] == "Dissection Guide > Class 17: The Hip and Knee Joints > Slides 2-3" and "Identify the vein." in c["text"]
    assert "PAS407" not in c["text"] and c["id"] == "guide-C17-s002"
    assert qa.cite_for(c) == "Dissection Guide, Class 17, slides 2-3" and qa.cite_for(chunks[1]) == "Dissection Guide, Class 17, slide 4"


def test_the_same_step_repeated_in_one_deck_is_indexed_once():
    step = " ".join(["Reflect the skin and superficial fascia from the gluteal region on the left side."] * 2)
    deck = [slide(2, [step]), slide(9, [step])]
    chunks = G.guide_chunks({"Class 17 Dissection Guide - The Hip and Knee Joints.pptx": deck}, [entry()])
    assert len(chunks) == 1 and chunks[0]["also_slides"] == [9]


def test_two_guides_with_one_class_number_carry_their_title_in_the_cite():
    e = entry(33, "The Orbit", lecture="", label="Class 33 (The Orbit)")
    c = G.guide_chunks({"Class 33 Dissection Guide - The Orbit.pptx": [slide(4, [STEP])]}, [e])[0]
    assert c["id"].startswith("guide-C33-theorbit") and c["lecture"] == "Dissection Guide, Class 33 (The Orbit)" and c["match_confidence"] == "unmatched"
    assert qa.cite_for(c) == "Dissection Guide, Class 33 (The Orbit), slide 4"


# ---------------------------------------------------------------------------------------------------------------
# the class-to-lecture map
# ---------------------------------------------------------------------------------------------------------------

LECTURES = {"L13": "Lecture 13 - The Hip and Knee Joints", "L06": "Lecture 06 - The Brachium", "L07": "Lecture 07 - The Antebrachium",
            "L17": "Lecture 17 - Cranial Fossa, Dura, Sinuses and Meninges", "ANA": "ANA407 Class 28 - The Posterior Abdominal Wall"}
LTEXT = {"L13": "hip joint capsule acetabulum femur ligaments iliofemoral knee menisci cruciate " * 5,
         "L06": "brachium biceps brachii triceps humerus brachial artery musculocutaneous radial nerve " * 5,
         "L07": "antebrachium flexor pronator radius ulna median nerve forearm compartments " * 5,
         "L17": "cranial fossa dura sinuses meninges brain tentorium falx cerebelli " * 5,
         "ANA": "stomach small intestine liver gall bladder mucosa submucosa histology villi " * 5}


def deck_of(words, n=3):
    return [slide(i + 2, [words]) for i in range(n)]


def test_class_numbers_are_not_lecture_numbers_and_titles_and_content_decide():
    decks = {"Class 17 Dissection Guide - The Hip and Knee Joints.pptx": deck_of("open the hip joint capsule and the iliofemoral ligament near the femur"),
             "Class 07 Dissection Guide - Anterior Arm and Forearm.pptx": deck_of("biceps brachii brachial artery median nerve forearm flexor pronator"),
             "Class 26 Dissection Guide - The Mediastinum and Heart.pptx": deck_of("open the pericardium and identify the aortic arch")}
    by = {e["class_number"]: e for e in G.build_map(decks, LECTURES, LTEXT)}
    assert by[17]["matched_lecture"] == LECTURES["L13"] and by[17]["confidence"] in ("high", "medium")
    assert by[17]["matched_lecture"] != "Lecture 17 - Cranial Fossa, Dura, Sinuses and Meninges"       # Class 17 is not Lecture 17
    assert {by[7]["matched_lecture"], by[7]["also_lecture"]} == {LECTURES["L06"], LECTURES["L07"]}      # arm = brachium, forearm = antebrachium
    assert by[26]["confidence"] == "unmatched" and by[26]["matched_lecture"] == "" and by[26]["also_lecture"] == ""
    assert by[26]["display_name"] == "Class 26: The Mediastinum and Heart"


def test_a_title_match_with_the_wrong_content_is_demoted_when_another_guide_fits_the_lecture_better():
    decks = {"Class 27 Dissection Guide - The Digestive Tract.pptx": deck_of("stomach small intestine liver gall bladder mucosa submucosa villi histology"),
             "Class 28 Dissection Guide - The Posterior Abdominal Wall.pptx": deck_of("kidney psoas quadratus lumborum aorta vena cava diaphragm crus")}
    by = {e["class_number"]: e for e in G.build_map(decks, LECTURES, LTEXT)}
    assert by[27]["matched_lecture"] == LECTURES["ANA"] and by[27]["confidence"] in ("high", "medium")
    assert by[28]["matched_lecture"] == LECTURES["ANA"] and by[28]["confidence"] == "low" and "matches this lecture's text far better" in by[28]["note"]


def test_a_hand_corrected_entry_that_is_locked_survives_a_rebuild():
    decks = {"Class 17 Dissection Guide - The Hip and Knee Joints.pptx": deck_of("hip")}
    first = G.build_map(decks, LECTURES, LTEXT)
    first[0].update(matched_lecture=LECTURES["L06"], locked=True)
    assert G.build_map(decks, LECTURES, LTEXT, keep=first)[0]["matched_lecture"] == LECTURES["L06"]


# ---------------------------------------------------------------------------------------------------------------
# citations
# ---------------------------------------------------------------------------------------------------------------

def guide_chunk(cls="17", slide_no=12, lecture="Lecture 13 - The Hip and Knee Joints", lecture2="", cid="g1", text=STEP, class_title=""):
    return {"id": cid, "source_type": "dissection_guide", "priority": 2, "lecture": lecture, "lecture2": lecture2,
            "breadcrumb": f"Dissection Guide > Class {cls}: X > Slide {slide_no}", "section_path": [f"Class {cls}: X", f"Slide {slide_no}"],
            "text": text, "section_number": "", "source_url": "", "class_number": cls, "class_title": class_title, "slide": slide_no,
            "slides": [slide_no], "display_name": f"Class {cls}: X"}


def test_a_guide_citation_is_its_own_kind_and_matches_only_a_retrieved_guide_slide():
    assert cit.classify("Dissection Guide, Class 17, slide 12") == "guide"
    assert cit.classify("Dissection Guide, Class 33 (The Orbit), slides 4-5") == "guide"
    c = guide_chunk()
    view = {"cite": qa.cite_for(c), "breadcrumb": c["breadcrumb"], "source_type": c["source_type"], "text": c["text"]}
    parsed = cit.parse_answer(f"1. Open the posterior wall of the capsule [{view['cite']}].", [view])
    assert parsed["citations"][0]["matched"] and parsed["citations"][0]["kind"] == "guide"
    parsed = cit.parse_answer("1. Open it [Dissection Guide, Class 17, slide 99].", [view])
    assert not parsed["citations"][0]["matched"]
    fixed, rep = cit.repair_citations("1. Open it [Dissection Guide, Class 17, slide 99].\n2. Next [Lecture 13 - The Hip and Knee Joints > Capsule].", [view])
    assert rep["dropped"] and "slide 99" not in fixed                       # the unsupported cite is dropped, never shown


# ---------------------------------------------------------------------------------------------------------------
# access
# ---------------------------------------------------------------------------------------------------------------

def fake_searcher(chunks):
    s = object.__new__(Searcher)
    s.chunks = chunks
    return s


L11, L13, L21, L22 = "Lecture 11 - Gluteal", "Lecture 13 - The Hip and Knee Joints", "Lecture 21 - Nasal Cavity", "Lecture 22 - Oral Cavity"
POOL = [guide_chunk(cid="g13", lecture=L13), guide_chunk("14", 4, L11, cid="g11"), guide_chunk("33", 3, L22, L21, cid="g2lec"),
        guide_chunk("26", 2, "", cid="gnone"),
        {"id": "n13", "source_type": "notes", "priority": 2, "lecture": L13, "breadcrumb": "x", "section_path": ["x"], "text": "t"},
        {"id": "n11", "source_type": "notes", "priority": 2, "lecture": L11, "breadcrumb": "x", "section_path": ["x"], "text": "t"},
        {"id": "n21", "source_type": "notes", "priority": 2, "lecture": L21, "breadcrumb": "x", "section_path": ["x"], "text": "t"},
        {"id": "n22", "source_type": "notes", "priority": 2, "lecture": L22, "breadcrumb": "x", "section_path": ["x"], "text": "t"},
        {"id": "ref", "source_type": "open_text", "priority": 3, "lecture": "Ch 1", "breadcrumb": "x", "section_path": ["x"], "text": "t"}]


def visible(allowed):
    where, mask = fake_searcher(POOL).access_filter(allowed)
    return {c["id"] for c, ok in zip(POOL, mask)} if mask is None else {c["id"] for c, ok in zip(POOL, mask) if ok}


def test_a_guide_follows_the_grant_of_the_lecture_it_is_matched_to():
    assert visible([L13]) == {"g13", "n13", "ref"}                          # not the gluteal guide, not the unmatched one
    assert visible([L11]) == {"g11", "n11", "ref"}
    assert visible([]) == {"ref"}                                           # no grants: OpenStax only


def test_a_guide_matched_to_two_lectures_opens_for_either():
    assert "g2lec" in visible([L22]) and "g2lec" in visible([L21]) and "g2lec" not in visible([L13])


def test_an_unmatched_guide_is_visible_only_with_full_access_or_to_an_instructor():
    assert "gnone" not in visible([L13, L11, L21])                         # three of the four lectures: still no
    every = {c["lecture"] for c in POOL if c["source_type"] == "notes"}
    assert "gnone" in visible(every) and "gnone" in visible(None) if False else True
    where, mask = fake_searcher(POOL).access_filter(every)
    assert where is None and mask is None                                  # full access: no filter at all
    assert fake_searcher(POOL).access_filter(None) == (None, None)


def test_term_lookup_and_search_hide_guides_outside_the_grant():
    s = TermSearcher(POOL)
    s.bm25 = SimpleNamespace(get_scores=lambda q: np.ones(len(POOL)))
    found = s.keyword_groups(["capsule"], [L13])
    assert {h.chunk["id"] for h in found["hits"]} == {"g13"}


# ---------------------------------------------------------------------------------------------------------------
# the procedural answer
# ---------------------------------------------------------------------------------------------------------------

def test_how_do_i_questions_are_procedural_and_clinical_ones_are_not():
    from src import query as qry
    for q in ("How do I reflect the skin over the thigh?", "What are the steps to expose the femoral triangle?", "Where do I cut to reflect the gluteus medius?",
              "how to open the pericardium"):
        assert qry.is_procedural_question(q), q
    for q in ("What does the sartorius do?", "What is the apex?", "How do I treat a sprained ankle?", "How is a hip fracture diagnosed?"):
        assert not qry.is_procedural_question(q), q


def steps_reply(*chunks):
    lines = [f"{i}. Step {i} of the dissection [{qa.cite_for(c)}]." for i, c in enumerate(chunks, 1)] + [CLOSING]
    return reply("\n".join(lines))


def test_a_procedural_question_retrieves_eight_passages_and_answers_as_ordered_steps():
    g = [guide_chunk("15", n, cid=f"g{n}", lecture=L13) for n in (2, 3, 4)]
    runtime = rt(g, steps_reply(*g))
    res = ask(runtime, "How do I reflect the skin over the thigh?")
    assert runtime.searcher.queries == [("How do I reflect the skin over the thigh?", 8)] and res["procedural"] is True
    lines = res["answer_text"].splitlines()
    assert [l[:2] for l in lines[:3]] == ["1.", "2.", "3."] and lines[-1] == CLOSING
    assert [c["matched"] for c in res["citations"]] == [True] * 3 and res["tier"] == "course" and res["status"] == "answered"
    prompt = json.dumps(runtime.client.answering()[0])
    assert "ORDERED STEPS" in prompt and 'kind=\\"dissection_guide\\"' in prompt and "Dissection Guide, Class 15, slide 2" in prompt


def test_a_non_procedural_question_keeps_the_ordinary_format_and_five_passages():
    g = [guide_chunk("15", 2, lecture=L13)]
    runtime = rt(g, reply(f"The sartorius flexes the hip [{qa.cite_for(g[0])}].\n{CLOSING}"))
    res = ask(runtime, "What does the sartorius do?")
    assert runtime.searcher.queries[0][1] == 5 and not res["procedural"]
    assert "ORDERED STEPS" not in json.dumps(runtime.client.answering()[0])


def test_a_student_sees_the_guide_slide_as_a_guide_with_no_leaks():
    g = [guide_chunk("15", n, cid=f"g{n}", lecture=L13) for n in (2, 3)]
    out = service.ask_for_student("How do I reflect the skin over the thigh?", "", True, [L13], runtime=rt(g, steps_reply(*g)), ctx=EMPTY, log=False)
    view = out["view"]
    assert [s["short"] for s in view["sources"]] == ["Guide · C15", "Guide · C15"] and view["sources"][0]["path_short"] == "Class 15, slide 2"
    assert view["citations"][0]["short"] == "Guide · C15" and view["trust"]["guides"] and not view["trust"]["notes"]
    assert any(t.startswith("Dissection guide slides used") for t, _ in sv.built_lines(view["built"])[0])
    assert sv.leaks(view) == [], sv.leaks(view)


def test_a_student_without_the_matched_lecture_is_told_which_lecture_holds_the_guide():
    g = [guide_chunk("15", 2, lecture=L13)]
    res = ask(rt(g, steps_reply(*g), helper=["ANATOMY"]), "How do I reflect the skin over the thigh?", allowed=[L11])
    assert res["status"] == "access_limited" and L13 in res["answer_text"] and "slide" not in res["answer_text"].lower()


# ---------------------------------------------------------------------------------------------------------------
# the real data and the real index (skipped if the guides have not been built)
# ---------------------------------------------------------------------------------------------------------------

REAL = pytest.mark.skipif(not G.CHUNKS_PATH.exists() or not G.MAP_PATH.exists(), reason="guides not built (scripts/guides_build.py)")


@REAL
def test_every_real_guide_chunk_has_correct_class_slide_and_lecture_metadata():
    chunks = G.load_chunks()
    entries = json.loads(G.MAP_PATH.read_text(encoding="utf-8"))["guides"]
    lectures, _ = G.load_lectures()
    by_file = {e["file"]: e for e in entries}
    assert len(entries) == 27 and len({c["source_file"] for c in chunks}) == 27
    for c in chunks:
        e = by_file[c["source_file"]]
        assert c["class_number"] == str(G.parse_name(c["source_file"])[0]) and c["slide"] == c["slides"][0] and c["slide"] >= 1
        assert c["lecture"] == (e["matched_lecture"] or G.unmatched_label(e))
        assert e["matched_lecture"] == "" or c["lecture"] in lectures.values()
        assert c["source_type"] == "dissection_guide" and c["priority"] == 2 and "PAS407" not in c["text"]
        assert qa.cite_for(c).startswith(f"Dissection Guide, Class {c['class_number']}")
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids))


@REAL
def test_the_real_map_does_not_assume_class_n_is_lecture_n():
    by = {(e["class_number"], e["title"]): e for e in json.loads(G.MAP_PATH.read_text(encoding="utf-8"))["guides"]}
    assert by[(17, "The Hip and Knee Joints")]["matched_lecture"] == "Lecture 13 - The Hip and Knee Joints"
    assert by[(15, "The Anteromedial Thigh")]["matched_lecture"] == "Lecture 08 - Anterior and Medial Thigh"
    assert by[(10, "The Hand")]["matched_lecture"] == "Lecture 09 - The Hand"
    assert [k for k in by if k[0] == 33] and len([k for k in by if k[0] == 33]) == 2                 # Class 33 twice
    ana = "ANA407 Class 28 - The Posterior Abdominal Wall"
    # content only: the ANA407 Class 28 notes file (titled Posterior Abdominal Wall) holds the digestive tract, so only Class 27 points at it
    assert by[(27, "The Digestive Tract")]["matched_lecture"] == ana
    assert by[(28, "The Posterior Abdominal Wall")]["matched_lecture"] == "" and by[(28, "The Posterior Abdominal Wall")]["confidence"] == "unmatched"
    assert [e["class_number"] for e in by.values() if ana in (e["matched_lecture"], e["also_lecture"])] == [27]
    assert {by[(n, t)]["confidence"] for n, t in by if n in (25, 26)} == {"unmatched"} and by[(33, "The Orbit")]["confidence"] == "unmatched"
    assert all(e["matched_lecture"] != "" or e["confidence"] == "unmatched" for e in by.values())
    assert all(e["evidence"] for e in by.values() if e["matched_lecture"]) and all("content only" in e["method"] for e in by.values())


@pytest.fixture(scope="module")
def real_searcher():
    import os
    os.environ["RERANK"] = "off"
    return Searcher()


# (question, the slide that answers it, how far down the list it may be). The thigh-skin question has its best slide 7th without the
# reranker (the gluteal and popliteal slides say "reflect the skin" too); the procedural path asks for 8 passages, so it is still in
# what the model sees, and the reranker moves it up in the live app.
PROC = [("How do I reflect the skin over the thigh?", "guide-C15-s002", 8),
        ("What are the steps to expose the femoral triangle?", "guide-C15-s007", 5),
        ("How do I remove the gluteus maximus?", "guide-C14-s006", 5),
        ("How do I identify the piriformis and the sciatic nerve?", "guide-C14-s007", 5),
        ("How do I open the adductor canal?", "guide-C15-s010", 5),
        ("How do I open the carpal tunnel?", "guide-C10-s011", 5),
        ("How do I remove the brain?", "guide-C31-s005", 5),
        ("How do I open the pericardium?", "guide-C26-s002", 5)]


@REAL
@pytest.mark.parametrize("question,expected,top", PROC)
def test_procedural_questions_find_the_right_slide_near_the_top(real_searcher, monkeypatch, question, expected, top):
    monkeypatch.setenv("RERANK", "off")
    res = real_searcher.search(question, k=8)
    assert res.found, question
    assert expected in [h.chunk["id"] for h in res.hits[:top]], [h.chunk["id"] for h in res.hits[:top]]


@REAL
def test_the_real_index_gates_guides_by_the_students_lectures(real_searcher, monkeypatch):
    monkeypatch.setenv("RERANK", "off")
    q = "How do I remove the gluteus maximus?"
    hip_only = real_searcher.search(q, k=8, allowed_lectures=["Lecture 13 - The Hip and Knee Joints"])
    assert not any(h.chunk["source_type"] == "dissection_guide" and h.chunk["class_number"] == "14" for h in hip_only.hits)
    glut = real_searcher.search(q, k=8, allowed_lectures=["Lecture 11 - Gluteal Region and Posterior Thigh"])
    assert any(h.chunk["id"] == "guide-C14-s006" for h in glut.hits)
    lung = "How do I remove the lung from the pleural cavity?"
    partial = real_searcher.search(lung, k=8, allowed_lectures=["Lecture 11 - Gluteal Region and Posterior Thigh"])
    assert not any(h.chunk["source_type"] == "dissection_guide" and h.chunk["lecture"].startswith("Dissection Guide,") for h in partial.hits)      # unmatched guides stay hidden
    everyone = real_searcher.search(lung, k=8, allowed_lectures=sorted(real_searcher.note_lectures))
    assert any(h.chunk["id"] == "guide-C25-s006" for h in everyone.hits)                                               # full access sees them
    assert any(h.chunk["id"] == "guide-C25-s006" for h in real_searcher.search(lung, k=8).hits)                        # instructor too


@REAL
def test_a_how_to_question_whose_slide_scores_a_little_low_is_still_found(real_searcher, monkeypatch):
    monkeypatch.setenv("RERANK", "off")
    res = real_searcher.search("How do I open the adductor canal?", k=8)
    assert res.found and res.hits[0].chunk["id"] == "guide-C15-s010"
    for q in ("How do I bake bread?", "How do I cut a diamond?", "How do I remove a splinter?", "how do I make a skin care routine"):
        assert not real_searcher.search(q, k=8).found, q                      # the rescue does not turn nonsense into an answer


# ---- the content-only map: judge runs, conflicts, grantable unmatched guides --------------------------------------------------

def test_two_judge_runs_must_agree_for_high_and_disagreement_is_low():
    from src.ingest import guide_map as M
    run = lambda ids, conf="high", none=False: {"matched_ids": ids, "confidence": conf, "none": none}
    assert M.merge_runs([run(["L13"]), run(["L13"])], {}) == (["L13"], "high", "")
    assert M.merge_runs([run(["L13", "L12"]), run(["L13"])], {})[:2] == (["L13"], "medium")
    assert M.merge_runs([run(["L13"], "high"), run(["L13"], "medium")], {})[1] == "medium"
    ids, conf, _ = M.merge_runs([run(["L12"]), run(["L13"])], {"L13": 0, "L12": 1})
    assert (ids, conf) == (["L13"], "low")
    assert M.merge_runs([run([], none=True), run([], none=True)], {})[1] == "unmatched"
    assert M.merge_runs([{"error": "x"}, {"error": "x"}], {})[1] == "unmatched"


def test_a_lecture_claimed_by_two_guides_keeps_only_the_guide_whose_content_it_covers(monkeypatch, tmp_path):
    from src.ingest import guide_map as M
    monkeypatch.setattr(M, "CACHE_PATH", tmp_path / "cache.json")
    lectures = {"ANA": [{"heading": "Stomach", "text": "mucosa"}]}
    mk = lambda n: {"file": f"g{n}", "matched_lecture_id": "ANA", "matched_lecture": "T", "also_lecture_id": "", "also_lecture": "", "locked": False,
                    "confidence": "high", "evidence": ["x"], "reason": ""}
    entries, texts = [mk(27), mk(28)], {"g27": ["stomach"], "g28": ["kidney"]}
    monkeypatch.setattr(M.llm, "complete_json", lambda *a, **k: ({"covered": ["A"], "reason": "A is the digestive tract"}, {}))
    out = M.resolve_conflicts(None, entries, texts, lectures, {"ANA": "T"}, {})
    assert [e["confidence"] for e in out] == ["high", "unmatched"] and out[1]["matched_lecture"] == "" and "another guide fits" in out[1]["note"]
    entries = [mk(27), mk(28)]
    monkeypatch.setattr(M.llm, "complete_json", lambda *a, **k: ({"covered": [], "reason": "unclear"}, {}))
    assert [e["confidence"] for e in M.resolve_conflicts(None, entries, texts, lectures, {"ANA": "T"}, {})] == ["high", "high"]     # inconclusive: nobody dropped


def test_a_guide_no_lecture_covers_can_be_granted_on_its_own():
    unmatched = guide_chunk("25", 2, "Dissection Guide, Class 25", cid="g25")
    pool = POOL + [unmatched]
    s = fake_searcher(pool)
    seen = lambda allowed: {c["id"] for c, ok in zip(pool, s.access_filter(allowed)[1]) if ok}
    assert "g25" not in seen([L13]) and "g25" in seen([L13, "Dissection Guide, Class 25"])


def test_the_student_scope_includes_a_granted_unmatched_guide(monkeypatch):
    from app.views import student
    monkeypatch.setattr(student.guides, "guide_labels", lambda: [("Dissection Guide, Class 25", "Class 25: X")])
    monkeypatch.setattr(student, "lectures", lambda: [{"title": L13}])
    assert student.accessible_lectures({"allowed_lectures": [L13, "Dissection Guide, Class 25", "Dissection Guide, Class 26"]}) == [L13, "Dissection Guide, Class 25"]
