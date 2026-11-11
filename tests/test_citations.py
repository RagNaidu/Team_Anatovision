"""Citation chips: parsing, matching against retrieved chunks, the unmatched case, passage highlighting."""
from src import citations as cit

NOTE = "Lecture 16b - Middle Ear > III. Middle Ear (Tympanic Cavity) > 3. Walls of the Middle Ear"
CHUNKS = [
    {"cite": NOTE, "breadcrumb": "Lecture 16b - Middle Ear > III. Middle Ear (Tympanic Cavity) > 3. Walls of the Middle Ear",
     "source_type": "notes", "text": "x"},
    {"cite": "OpenStax A&P 2e §14.1", "breadcrumb": "OpenStax A&P 2e > ch > sec", "source_type": "open_text", "text": "y"},
]
FIX = {"by": "Dr. Inglis", "date": "2026-10-07", "marker": "V1"}


def parse(text, fixes=()):
    return cit.parse_answer(text, CHUNKS, list(fixes))


def test_bracketed_note_citation_becomes_a_numbered_chip():
    r = parse(f"The middle ear has walls [{NOTE}].")
    (c,) = r["citations"]
    assert c["n"] == 1 and c["kind"] == "notes" and c["matched"] and c["chunk"] == 0
    assert r["units"][0]["text"] == "The middle ear has walls." and r["units"][0]["chips"] == [1]


def test_full_stops_inside_a_citation_do_not_split_the_sentence():
    r = parse(f"Inferior wall has a canaliculus. (flagged for review, see fact-check) [{NOTE}]")   # '3. Walls' is inside
    assert [u["chips"] for u in r["units"]] == [[1]]
    assert r["units"][0]["status"] == [{"kind": "doubtful", "label": "flagged for review"}]
    assert "[" not in r["units"][0]["text"] and "flagged" not in r["units"][0]["text"]


def test_same_citation_keeps_one_number():
    r = parse(f"First [{NOTE}].\nSecond [{NOTE}].")
    assert [u["chips"] for u in r["units"]] == [[1], [1]] and len(r["citations"]) == 1
    assert r["citations"][0]["sentences"] == ["First.", "Second."]


def test_citation_not_in_the_retrieved_chunks_is_reported_unmatched():
    r = parse(f"Real [{NOTE}]. Invented [Lecture 99 - Ghost > Nothing here].")
    ghost = next(c for c in r["citations"] if "Ghost" in c["cite"])
    assert ghost["matched"] is False and ghost["chunk"] is None
    assert r["n_unmatched"] == 1 and next(c for c in r["citations"] if "Ghost" not in c["cite"])["matched"]


def test_a_similar_but_different_section_does_not_match():
    r = parse("Claim [Lecture 16b - Middle Ear > III. Middle Ear (Tympanic Cavity) > 4. Something else].")
    assert r["citations"][0]["matched"] is False


def test_openstax_cited_with_or_without_brackets():
    r = parse("Bracketed [OpenStax A&P 2e §14.1].\nBare OpenStax A&P 2e §14.1.\nOther [OpenStax A&P 2e §99.9].")
    assert [c["matched"] for c in r["citations"]] == [True, False]
    assert r["citations"][0]["kind"] == "openstax"


def test_a_note_cite_cannot_be_matched_by_an_openstax_chunk():
    chunks = [{"cite": "OpenStax A&P 2e §14.1", "breadcrumb": "b", "source_type": "open_text"}]
    assert cit.parse_answer("x [OpenStax A&P 2e §14.1].", chunks)["citations"][0]["matched"] is True
    assert cit.parse_answer("x [Lecture 1 > A].", chunks)["citations"][0]["matched"] is False


def test_verified_citation_matches_only_the_recorded_name():
    ok = parse("Corrected [Verified by Dr. Inglis, 2026-10-07].", [FIX])
    assert ok["citations"][0]["matched"] and ok["citations"][0]["fix"] == 0
    assert ok["units"][0]["status"] == [{"kind": "verified", "label": "Verified by Dr. Inglis, 2026-10-07"}]
    bad = parse("Corrected [Verified by Someone Else, 2026-10-07].", [FIX])
    assert bad["citations"][0]["matched"] is False


def test_under_review_sentence_gets_the_review_status():
    r = parse(f"This line in the course notes is currently under review [{NOTE}].")
    assert r["units"][0]["status"] == [{"kind": "review", "label": "under review"}]


def test_brackets_that_are_not_citations_are_left_alone():
    r = parse("See item [1] and [sic].")
    assert r["citations"] == [] and r["units"][0]["text"] == "See item [1] and [sic]."


def test_abbreviations_do_not_split_sentences():
    r = parse(f"Dr. Inglis lists six walls, e.g. the roof [{NOTE}]. Next one [{NOTE}].")
    assert len(r["units"]) == 2 and r["units"][0]["text"].startswith("Dr. Inglis")


def test_a_trailing_status_note_after_the_citation_joins_that_line():
    r = parse(f"Inferior: a canaliculus [{NOTE}] (flagged for review, see fact-check)")
    assert len(r["units"]) == 1 and r["units"][0]["status"][0]["kind"] == "doubtful"


def test_best_spans_find_the_source_line_or_nothing():
    passage = "a. Lateral wall\ni. Tympanic membrane.\nb. Posterior wall: aditus to the mastoid antrum.\nc. Inferior wall."
    (a, b), = cit.best_spans(passage, "The posterior wall has the aditus to the mastoid antrum.")
    assert "aditus" in passage[a:b] and "Lateral" not in passage[a:b]
    assert cit.best_spans(passage, "Something about the heart valves entirely.") == []


def test_passage_html_escapes_and_marks():
    text = "Line <b>one</b>. Hidden [LINE UNDER REVIEW U1] tail. Fixed [LINE CORRECTED V1] end."
    out = cit.passage_html(text, [(0, 4)], {"V1": {"correction": "The right thing"}})
    assert "<b>one</b>" not in out and "&lt;b&gt;" in out and "<mark>Line</mark>" in out
    assert "chip-review" in out and "chip-verified" in out and "The right thing" in out


def test_withheld_line_markers_are_not_matched_as_evidence():
    passage = "- The median nerve supplies most flexors. [LINE UNDER REVIEW U1]"
    assert cit.best_spans(passage, "This line in the course notes is currently under review.") == []
