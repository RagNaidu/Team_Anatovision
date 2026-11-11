"""What the revised notes do to the rest of the app: labels for an earlier version, changed fact-check items, grants, a student's place in a guide, old citations."""
import json
import sys
from pathlib import Path

from app_api import convert
from app_api.routers import admin
from src import guide_store
from src import revision_status as RS
from src import student_view as sv
from src.ingest import revision as R

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import revision_swap as SW  # noqa: E402


def test_titles_and_version_metadata_of_a_revised_file():
    assert R.v2_stem("Lecture 04 - The_Shoulder - Notes.docx") == "Lecture 04 - The Shoulder"
    assert R.v2_stem("Lecture 01 - The Vertebral Column - Notes - Reviewed.docx") == "Lecture 01 - The Vertebral Column"
    assert R.v2_stem("Lecture 16 - Anterolateral Thoracoabdominal Wall script.docx") == "Lecture 16 - Anterolateral Thoracoabdominal Wall"
    rec = {"lecture_id": "L09-the-hand", "order": 3, "section_path": ["Nerves", "Median"]}
    out = R.with_version(rec, 2)
    assert out["doc_id"] == "L09-the-hand" and out["version"] == 2 and out["section_id"] == "L09-the-hand#003:Nerves > Median" and "superseded" not in out
    assert R.with_version(rec, 1, superseded=True)["superseded"] == "Earlier version, not in revised notes"


def test_a_flagged_quote_is_found_where_it_lives_now_or_not_at_all():
    docs = [("Lecture 11", [(["Gluteus"], "Origin:   ilium\nInsertion: femur"), (["Nerve"], "Supplied by the sciatic nerve")])]
    assert R.find_quote("origin: ilium insertion: femur", docs) == ("Lecture 11", 0)
    assert R.find_quote("supplied by the femoral nerve", docs) is None
    assert R.best_sentence("Supplied by the femoral nerve", ["Supplied by the sciatic nerve. Other text."]) == "Supplied by the sciatic nerve."


def test_an_old_answers_sources_say_updated_or_removed_only_when_they_are():
    chunks = [{"source_type": "notes", "lecture": "Lecture 08", "breadcrumb": "Lecture 08 > Femoral Triangle", "text": "Borders are the inguinal ligament, sartorius and adductor longus muscles."},
              {"source_type": "dissection_guide", "lecture": "Lecture 08", "breadcrumb": "Dissection Guide > Class 15 > Slide 7", "text": "Open the femoral sheath along the vessels and identify the nerve."}]
    cur = RS.CurrentIndex(chunks)
    same = {"source_type": "notes", "lecture": "Lecture 08", "breadcrumb": "Lecture 08 > Femoral Triangle", "text": "Borders are the inguinal ligament, sartorius and adductor longus muscles."}
    changed = {**same, "text": "Floor formed by iliopsoas, pectineus and the obturator externus muscle in the old notes."}
    gone = {**changed, "lecture": "Lecture 14", "breadcrumb": "Lecture 14 > Anterior Triangle"}
    assert cur.status(same) is None and cur.status(changed) == "updated" and cur.status(gone) == "removed"
    assert cur.status({"source_type": "open_text", "text": "anything at all that is long enough to matter here"}) is None
    assert RS.LABELS == {"updated": "Source updated", "removed": "Source removed"}


def test_an_earlier_version_source_is_labelled_in_the_source_and_the_footer():
    src = {"source_type": "notes", "lecture": "Lecture 17 - Cranial Fossa, Dura, Sinuses and Meninges", "crumb": "Cranial Meninges", "breadcrumb": "x", "text": "t",
           "superseded": R.SUPERSEDED_NOTE}
    assert convert.source_of(1, src)["subtitle"].endswith("(Earlier version, not in revised notes)")
    assert "Earlier version" not in convert.source_of(1, {**src, "superseded": ""})["subtitle"]


def test_a_fact_check_item_whose_quote_changed_is_listed_but_cannot_be_decided():
    item = {"key": "review|L|B|q", "kind": "likely_factual", "issue": "wrong", "section_path": ["A"], "breadcrumb": "L > A", "lecture": "L", "claim_quote": "old line",
            "decision": {"status": "open"}, "revision": {"status": "changed", "new_text": "new line", "new_breadcrumb": "L2 > A", "new_lecture": "L2"}}
    assert admin.item_status(item) == "changed"
    shown = admin.review_item(item)
    assert shown["status"] == "changed" and "no longer there" in shown["ai_note"] and "New wording: new line" in shown["ai_note"] and len(shown["sources"]) == 2
    assert admin.item_status({**item, "revision": {"status": "unchanged"}}) == "open"
    from src.modes import qa
    from src import reports
    assert not [i for i in [{**item, "tier": "likely_factual"}] if (i.get("revision") or {}).get("status") != "changed"]


def test_grants_follow_the_renamed_lectures_and_guides_and_brand_new_documents_are_granted_to_nobody():
    m = {"notes": [{"v1_title": "Lecture 14 - Anterior Triangle", "v2_title": "Lecture 22 - Anterior Triangle"}, {"v1_title": "Lecture 09 - The Hand", "v2_title": "Lecture 09 - The Hand"}],
         "guides": [{"v1_label": "Dissection Guide, Class 33 (The Orbit)", "v2_label": "Dissection Guide, Class 33"}]}
    new, dropped = SW.new_grants(["Lecture 14 - Anterior Triangle", "Dissection Guide, Class 33 (The Orbit)", "Gone"], m)
    assert new == ["Dissection Guide, Class 33", "Lecture 22 - Anterior Triangle"] and dropped == ["Gone"]
    everything, _ = SW.new_grants(["Lecture 14 - Anterior Triangle", "Lecture 09 - The Hand", "Dissection Guide, Class 33 (The Orbit)"], m)
    assert everything == ["Dissection Guide, Class 33", "Lecture 09 - The Hand", "Lecture 22 - Anterior Triangle"]      # someone with everything does NOT get a lecture that is new in the revision


def test_a_students_place_is_carried_to_the_station_that_says_the_same_thing():
    stations = [{"text": "Open the femoral sheath along the line of the vessels."}, {"text": "Remove the skull cap with a saw and chisel."}]
    assert SW.carry_station("Cut the femoral sheath open along the vessels line", stations) == 0
    assert SW.carry_station("Something about the liver and the bile duct entirely", stations) is None
    assert SW.carry_station("", stations) is None


def test_a_moved_place_keeps_a_one_time_notice_cleared_by_the_next_visit(tmp_path):
    gs = guide_store.GuideStore(tmp_path / "g.db")
    gs.put_history_row("a", "guide:class-17", "guide", "class-17", "Class 17", 0, 19, "more_fat", "This guide was updated.")
    row = gs.history_of("a")[0]
    assert row["notice"] == "This guide was updated." and row["body_type"] == "more_fat"
    gs.touch_history("a", "guide", "class-17", "Class 17", 2, 19)
    assert gs.history_of("a")[0]["notice"] is None and gs.history_of("a")[0]["body_type"] == "more_fat"


def test_new_revision_flags_are_shown_tagged_not_hidden_and_one_setting_switches_it(tmp_path, monkeypatch):
    from src.modes import qa

    def issue(quote, status, tier="likely_factual", verdict="confirmed"):
        rev = {"revision": {"status": status}} if status else {}
        return {"lecture": "L", "breadcrumb": "L > A", "claim_quote": quote, "tier": tier, "type": "factual", "verification": {"verdict": verdict}, **rev}
    path = tmp_path / "f.json"
    path.write_text(json.dumps({"issues": [issue("old confirmed", None), issue("new confirmed", "new_in_revision"), issue("gone confirmed", "changed"),
                                           issue("doubtful", None, "second_look", "doubtful")]}), encoding="utf-8")
    monkeypatch.delenv("NEW_REVISION_FLAGS", raising=False)
    hidden = [i["claim_quote"] for i in qa.load_review_items(path)]
    tagged = [i["claim_quote"] for i in qa.load_doubtful_items(path)]
    assert hidden == ["old confirmed"] and sorted(tagged) == ["doubtful", "new confirmed"]       # the older flag stays hidden; the new one is tagged; a changed line is neither
    monkeypatch.setenv("NEW_REVISION_FLAGS", "hide")
    assert sorted(i["claim_quote"] for i in qa.load_review_items(path)) == ["new confirmed", "old confirmed"]
    assert [i["claim_quote"] for i in qa.load_doubtful_items(path)] == ["doubtful"]
