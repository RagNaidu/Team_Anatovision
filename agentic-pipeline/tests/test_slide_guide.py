"""Guide mode on the dissection guides: stations from slides, the walk-through session, access, the picker. The model is faked."""
import pytest

from src import llm
from tests.test_app import world  # noqa: F401  (fixture)
from src import student_view as sv
from src.ingest import guides as G
from src.modes import guide_slides as GS


def slide(n, texts=(), pics=0, title=""):
    return {"n": n, "title": title, "texts": list(texts), "tables": [], "notes": "", "n_pictures": pics, "n_diagrams": 0, "hidden": False,
            "n_words": sum(len(t.split()) for t in texts)}


FOOT = "PAS407 – Class 17 Dissection Guide – The Hip and Knee Joints"
A = "Open and remove the posterior wall of the joint capsule to expose the ligaments of the hip. Take care to keep the labrum intact."
B = "Identify the iliofemoral ligament, which runs from the anterior inferior iliac spine to the intertrochanteric line."
C = "Cut the ligament of the head of the femur and dislocate the head from the acetabulum. Examine the acetabular labrum."


def deck():
    return [slide(1, ["PAS407 – Gross Human Anatomy", "Class 17 – The Hip", "Laboratory Session – The Hip"]),
            slide(2, [A, FOOT, "2"]), slide(3, [B, FOOT, "3"]), slide(4, ["A", "B"], pics=2),
            slide(5, [C, FOOT, "5"]), slide(6, ["End of Laboratory Session"])]


# ---- stations -------------------------------------------------------------------------------------------------------------

def test_stations_follow_slide_order_with_their_slide_numbers_and_skip_title_and_end_slides():
    st = GS.build_stations(deck(), "Class 17")
    assert [s["slides"] for s in st] == [[2], [3], [4], [5]] and [s["n"] for s in st] == [1, 2, 3, 4]
    assert st[0]["steps"] == ["Open and remove the posterior wall of the joint capsule to expose the ligaments of the hip.",
                              "Take care to keep the labrum intact."]
    assert st[0]["cite"] == "Dissection Guide, Class 17, slide 2" and "PAS407" not in st[0]["text"]
    assert st[0]["title"] == "Open and remove the posterior wall of the…"


def test_consecutive_slides_with_the_same_title_become_one_station():
    d = [slide(2, [A], title="Hip capsule"), slide(3, [B], title="Hip capsule"), slide(4, [C], title="Ligaments")]
    st = GS.build_stations(d, "Class 17")
    assert [s["slides"] for s in st] == [[2, 3], [4]] and st[0]["title"] == "Hip capsule" and len(st[0]["steps"]) == 3
    assert st[0]["cite"] == "Dissection Guide, Class 17, slides 2-3"


def test_an_image_only_slide_stays_as_a_station_that_points_to_the_slide():
    st = GS.build_stations(deck(), "Class 17")
    pic = st[2]
    assert pic["image_only"] and pic["steps"] == [] and pic["text"] == "See slide 4 in your lab guide." and pic["cite"].endswith("slide 4")


def test_numbered_and_bulleted_lines_become_clean_steps():
    assert GS.split_steps(["1.\tReflect the skin. Keep the veins.", "- Identify the nerve."]) == ["Reflect the skin.", "Keep the veins.", "Identify the nerve."]


def test_a_guide_with_no_usable_text_says_so():
    s = GS.SlideGuideSession(entry={"display_name": "Class 99: Empty", "class_label": "Class 99", "file": "x"}, stations=GS.build_stations([slide(1, ["Laboratory Session – X"])], "Class 99"))
    st = s.state()
    assert st["usable"] is False and st["no_text"].startswith("This guide has no usable text") and not s.goto(1)


# ---- the session ----------------------------------------------------------------------------------------------------------

ENTRY = {"display_name": "Class 17: The Hip and Knee Joints", "class_label": "Class 17", "file": "x.pptx"}


def session(verdicts):
    s = GS.SlideGuideSession(entry=ENTRY, stations=GS.build_stations(deck(), "Class 17"), model="m")
    seq = iter(verdicts)
    s.judge = lambda st, d: next(seq)
    return s


def test_navigation_is_free_next_back_and_jump():
    s = session([])
    assert s.current == 1 and s.next() and s.current == 2 and s.back() and s.current == 1 and s.goto(4) and s.current == 4
    assert not s.next() and not s.goto(9) and not s.goto(0) and s.current == 4
    st = s.state()
    assert st["can_back"] and not st["can_next"] and st["station"]["slides"] == [5]


def test_a_matching_description_marks_the_station_done_a_partial_one_does_not():
    s = session([{"match": "partial", "feedback": "You opened the capsule but not the labrum."}, {"match": "yes", "feedback": "Right: the capsule is open."}])
    t = s.assess("I opened it")
    assert t["detail"]["verdict"] == "partial" and s.state()["done"] == []
    t = s.assess("I opened the posterior capsule and kept the labrum")
    assert t["detail"]["verdict"] == "yes" and s.state()["done"] == [1]


def test_a_failing_judge_is_reported_not_raised():
    s = GS.SlideGuideSession(entry=ENTRY, stations=GS.build_stations(deck(), "Class 17"), model="m")

    def boom(st, d):
        raise llm.LLMError("down")
    s.judge = boom
    assert s.assess("x")["detail"]["verdict"] == "error" and s.state()["done"] == []


def test_a_picture_station_needs_no_description_and_counts_when_assessed():
    s = session([])
    s.goto(3)
    t = s.assess("")
    assert t["detail"]["verdict"] == "picture" and "See slide 4 in your lab guide" in t["detail"]["feedback"] and 3 in s.state()["done"]


def test_a_vague_description_is_judged_against_only_the_station_text():
    seen = []
    s = GS.SlideGuideSession(entry=ENTRY, stations=GS.build_stations(deck(), "Class 17"), model="m")
    s.judge = lambda st, d: (seen.append(st["text"]) or {"match": "partial", "feedback": "The guide asks you to open the capsule."})
    s.assess("I looked at it")
    assert seen == [s.station(1)["text"]] and "PAS407" not in seen[0]


def test_the_student_view_of_the_state_and_a_turn_has_no_leaks():
    s = session([{"match": "no", "feedback": "That is not what the guide shows. This is under review by the fact-check."}])
    turn = sv.slide_guide_turn(s.assess("something else"))
    state = sv.slide_guide_state(s.state())
    assert sv.leaks(state) == [] and sv.leaks(turn) == [], (sv.leaks(state), sv.leaks(turn))
    assert set(state) >= {"guide", "stations", "station", "progress"} and "cost" not in state and "events" not in turn


# ---- access ---------------------------------------------------------------------------------------------------------------

def entries(*rows):
    return {e["file"]: e for e in ({"class_number": n, "file": f"{n}.pptx", "title": t, "class_label": f"Class {n}", "display_name": f"Class {n}: {t}",
                                    "matched_lecture": lec, "also_lecture": also} for n, t, lec, also in rows)}


MAP = entries((14, "Gluteal", "Lecture 11 - Gluteal", ""), (17, "Hip", "Lecture 13 - Hip", ""), (33, "Oronasal", "Lecture 22 - Oral", "Lecture 21 - Nasal"),
              (26, "Heart", "", ""))


@pytest.fixture
def fake_map(monkeypatch):
    monkeypatch.setattr(G, "map_by_file", lambda path=None: MAP)
    monkeypatch.setattr(G, "load_lectures", lambda path=None: ({"a": "Lecture 11 - Gluteal", "b": "Lecture 13 - Hip", "c": "Lecture 22 - Oral", "d": "Lecture 21 - Nasal"}, {}))


def names(allowed):
    return [e["class_number"] for e in G.accessible_guides(allowed)]


def test_guides_follow_the_lecture_grant_a_guide_grant_or_full_access(fake_map):
    assert names(["Lecture 13 - Hip"]) == [17] and names(["Lecture 21 - Nasal"]) == [33] and names([]) == []
    assert names(["Dissection Guide, Class 14", "Dissection Guide, Class 26"]) == [14, 26]       # a guide granted on its own, matched or not
    assert names(["Lecture 11 - Gluteal", "Lecture 13 - Hip", "Lecture 22 - Oral", "Lecture 21 - Nasal"]) == [14, 17, 26, 33]   # every lecture: every guide
    assert names(None) == [14, 17, 26, 33]


def test_every_real_guide_can_be_granted_on_its_own():
    labels = G.guide_labels()
    assert len(labels) == 27 and len({l for l, _ in labels}) == 27
    assert ("Dissection Guide, Class 17", "Class 17: The Hip and Knee Joints") in labels
    assert any(l == "Dissection Guide, Class 33 (The Orbit)" for l, _ in labels)


def test_a_granted_guide_is_searchable_in_q_and_a_too():
    from tests.test_dissection_guides import guide_chunk, fake_searcher
    c = guide_chunk("17", 12, "Lecture 13 - Hip", cid="g")
    c["guide"] = "Dissection Guide, Class 17"
    s = fake_searcher([c])
    assert bool(s.access_filter(["Dissection Guide, Class 17"])[1][0]) and not s.access_filter(["Dissection Guide, Class 18"])[1][0]


# ---- real guides ----------------------------------------------------------------------------------------------------------

REAL = pytest.mark.skipif(not G.SLIDES_PATH.exists() or not G.MAP_PATH.exists(), reason="guides not built")


@REAL
def test_every_real_guide_builds_stations_in_slide_order():
    for e in G.map_by_file().values():
        st = GS.build_stations(GS.slides_of(e["file"]), e["class_label"])
        assert st, e["file"]
        firsts = [s["slides"][0] for s in st]
        assert firsts == sorted(firsts) and all(s["cite"].startswith(f"Dissection Guide, {e['class_label']}, slide") for s in st)
        assert all(s["steps"] or s["image_only"] for s in st)


@REAL
def test_class_14_stations_match_the_real_slides():
    e = next(e for e in G.map_by_file().values() if e["class_number"] == 14)
    st = GS.build_stations(GS.slides_of(e["file"]), e["class_label"])
    assert st[0]["slides"] == [2] and "surface anatomy of the thigh" in st[0]["text"] and st[-1]["slides"][0] == 10
    assert any("gluteus maximus" in s["text"] and 6 in s["slides"] for s in st)


# ---- the screens ----------------------------------------------------------------------------------------------------------
