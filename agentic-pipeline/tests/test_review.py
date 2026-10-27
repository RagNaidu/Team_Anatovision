"""Review queue: tabs, flags created on demand, decisions go through src.verified.resolve (same code as the CLI)."""
import pytest

from src import review, verified
from src.modes import qa

pytestmark = pytest.mark.skipif(not review.FACTCHECK_PATH.exists(), reason="reports/factcheck_all.json missing")


@pytest.fixture(autouse=True)
def tmp_files(tmp_path, monkeypatch):
    monkeypatch.setattr(verified, "FLAGS_PATH", tmp_path / "flags.jsonl")
    monkeypatch.setattr(verified, "FIXES_PATH", tmp_path / "fixes.jsonl")
    monkeypatch.setattr(qa, "FLAGS_PATH", tmp_path / "flags.jsonl")


@pytest.fixture(scope="module")
def items():
    return review.queue(review.load_report(), {})


def first(items, kind):
    return next(i for i in items if i["kind"] == kind)


def test_tab_sizes_match_the_report(items):
    assert len(review.start_here(items)) == review.START_HERE_MAX == 14
    assert {t: len(review.tab_items(items, t)) for t in review.TABS} == {
        "start_here": 14, "likely_factual": 90, "second_look": 474, "typo": 169}
    assert all(i["tier"] == "likely_factual" and i["severity"] == "high" for i in review.start_here(items))


def test_flag_key_is_the_one_qa_mode_writes(items):
    c, d = first(items, "likely_factual"), first(items, "doubtful")
    assert review.flag_key(c) == f"review|{c['lecture']}|{c['breadcrumb']}|{c['claim_quote']}"
    assert review.flag_key(d) == f"doubtful|{d['lecture']}|{d['breadcrumb']}|{d['claim_quote']}"


def test_a_flag_is_created_once_and_typed_by_kind(items):
    for kind, flag_type in (("likely_factual", "note_line_under_review"), ("doubtful", "note_line_doubtful"),
                            ("wording", "note_line_wording"), ("typo", "note_line_typo")):
        item = first(items, kind)
        n = review.ensure_flag(item)
        assert review.ensure_flag(item) == n
        flag = verified.read_jsonl(verified.FLAGS_PATH)[n - 1]
        assert flag["type"] == flag_type and flag["status"] == "open" and flag["notes_quote"] == item["claim_quote"]
    assert len(verified.read_jsonl(verified.FLAGS_PATH)) == 4


def test_deciding_uses_verified_resolve(items, monkeypatch):
    calls = []
    real = verified.resolve
    monkeypatch.setattr(verified, "resolve", lambda *a, **k: calls.append((a, k)) or real(*a, **k))
    item = first(items, "likely_factual")
    (fix,) = review.decide(item, "confirm_error", "The popliteal artery continues the femoral artery.", "Dr. Inglis")
    assert len(calls) == 1 and calls[0][0][1:4] == ("confirm_error", "The popliteal artery continues the femoral artery.", "Dr. Inglis")
    assert fix["by"] == "Dr. Inglis" and fix["lecture"] == item["lecture"] and fix["notes_quote"] == item["claim_quote"]
    (flag,) = verified.read_jsonl(verified.FLAGS_PATH)
    assert flag["status"] == "resolved" and flag["verified_fix_id"] == fix["id"]


def test_queue_shows_the_decision(items):
    item = first(items, "typo")
    review.decide(item, "notes_correct", "", "Dr. Inglis")
    again = review.queue(review.load_report(), review.decisions())
    mine = next(i for i in again if i["key"] == item["key"])
    assert mine["decision"]["status"] == "resolved" and mine["decision"]["decision"] == "notes_correct"
    assert mine["decision"]["by"] == "Dr. Inglis"


def test_a_correction_is_required_for_confirm_and_reword_and_a_name_always(items):
    item = first(items, "wording")
    with pytest.raises(ValueError, match="correction"):
        review.decide(item, "confirm_error", "  ", "Dr. Inglis")
    with pytest.raises(ValueError, match="correction"):
        review.decide(item, "reword", "", "Dr. Inglis")
    with pytest.raises(ValueError, match="name"):
        review.decide(item, "notes_correct", "", "   ")
    assert verified.load_fixes() == []


def test_a_decided_item_cannot_be_decided_twice(items):
    item = first(items, "doubtful")
    review.decide(item, "notes_correct", "", "Dr. Inglis")
    with pytest.raises(ValueError, match="already"):
        review.decide(item, "notes_correct", "", "Dr. Inglis")


def test_undo_reopens_the_flag(items):
    item = first(items, "likely_factual")
    (fix,) = review.decide(item, "reword", "Better wording.", "Dr. Inglis")
    assert [f["id"] for f in review.ledger()] == [fix["id"]]
    assert review.undo(fix["id"]) == 1
    assert review.ledger() == [] and verified.read_jsonl(verified.FLAGS_PATH)[0]["status"] == "open"


def test_apply_to_all_same_quote(items):
    twin = next((i for i in items if i["kind"] == "likely_factual" and review.same_quote_places(i)), None)
    if twin is None:
        pytest.skip("no quote appears in more than one place")
    fixes = review.decide(twin, "notes_correct", "", "Dr. Inglis", apply_all=True)
    assert len(fixes) == 1 + len(review.same_quote_places(twin))
