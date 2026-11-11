"""Regression tests on the REVISED notes (version 2 is the live data): one core question per region retrieves the right lecture, and a citation the model joined inside one
bracket ("[notes cite, Dissection Guide, Class 29, slides 11-14]") no longer makes a good answer vanish into "Not covered"."""
import os

import pytest

from src import citations as cit
from src import service
from src.modes import qa
from src.retrieval.index import CHUNKS_PATH
from tests.test_service import CLOSING, reply
from tests.test_stage1 import rt
from tests.test_student_safe import EMPTY

def _revised_index():
    return CHUNKS_PATH.exists() and any("Lecture 22 - Anterior Triangle" in line for line in CHUNKS_PATH.open(encoding="utf-8"))


LIVE = pytest.mark.skipif(not _revised_index(), reason="the revised index is not the live index")

REGIONS = [("back", "What are the spinal curvatures of the vertebral column?", "Lecture 01 - The Vertebral Column"),
           ("upper limb", "What is the nerve supply of the hypothenar muscles?", "Lecture 09 - The Hand"),
           ("lower limb", "What are the boundaries of the femoral triangle?", "Lecture 08 - Anterior and Medial Thigh"),
           ("thorax", "What are the layers of the heart wall?", "Lecture 19 - The Heart"),
           ("abdomen", "What are the layers of the wall of the gastrointestinal tract?", "Lecture 20 - The Digestive System"),
           ("head and neck", "What are the boundaries of the anterior triangle of the neck?", "Lecture 22 - Anterior Triangle of the Neck")]


@pytest.fixture(scope="module")
def searcher():
    os.environ["RERANK"] = "off"
    from src.retrieval.search import Searcher
    return Searcher()


@LIVE
@pytest.mark.parametrize("region,question,lecture", REGIONS)
def test_a_core_question_per_region_finds_its_revised_lecture(searcher, region, question, lecture):
    res = searcher.search(question)
    assert res.found, question
    assert any(h.chunk["lecture"] == lecture for h in res.hits), [h.chunk["breadcrumb"] for h in res.hits]


def test_two_citations_joined_in_one_bracket_are_split_and_the_answer_survives():
    a = "It is bounded by the mandible [Lecture 22 - Anterior Triangle of the Neck > Triangles of the Neck > Triangles of the Neck, Dissection Guide, Class 29, slides 11-14]."
    out = cit.split_joined_cites(a)
    assert out.count("[") == 2 and "[Dissection Guide, Class 29, slides 11-14]" in out
    one = "Kept [Lecture 08 - Thigh, Femoral Triangle > Borders] as it is, and [1] too."
    assert cit.split_joined_cites(one) == one                              # a comma inside ONE citation is not a join
    assert cit.split_joined_cites("[Lecture 22 - X, nonsense words]") == "[Lecture 22 - X, nonsense words]"


def chunk(cid, crumb, text, st="notes", lecture="Lecture 22 - Anterior Triangle of the Neck", **extra):
    return {"id": cid, "source_type": st, "priority": 2, "lecture": lecture, "lecture2": "", "breadcrumb": crumb, "section_path": crumb.split(" > ")[1:], "text": text,
            "section_number": "", "source_url": "", "class_number": extra.get("class_number", ""), "slide": extra.get("slide", ""), "slides": extra.get("slides", [])}


def test_the_anterior_triangle_question_is_answered_when_the_model_joins_two_citations():
    notes = chunk("n1", "Lecture 22 - Anterior Triangle of the Neck > Triangles of the Neck > Triangles of the Neck",
                  "- anterior triangle defined by midline, mandible, sternocleidomastoid")
    guide = chunk("g1", "Dissection Guide > Class 29: The Triangles of the Neck > Slides 11-14", "Identify the boundaries of the anterior triangle.", st="dissection_guide",
                  class_number="29", slide=11, slides=[11, 12, 13, 14])
    joined = f"[{qa.cite_for(notes)}, {qa.cite_for(guide)}]"
    runtime = rt([notes, guide], reply(f"The anterior triangle is bounded by the midline, the mandible and sternocleidomastoid {joined}.\n{CLOSING}"))
    res = service.ask("What are the boundaries of the anterior triangle of the neck?", "", True, None, runtime=runtime, ctx=EMPTY, log=False)
    assert res["status"] == "answered" and "midline" in res["answer_text"]
    assert [c["matched"] for c in res["citations"]] == [True, True]
