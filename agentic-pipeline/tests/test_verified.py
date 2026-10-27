"""Verified fixes, doubtful items, and the Q&A guards. No API calls: the model is replaced by canned answers."""
import json

import pytest

from src import verified
from src.modes import qa
from src.retrieval.search import Hit, SearchResult

QUOTE = "Superior – inguinal canal"
L8 = "Lecture 08 - Anterior and Medial Thigh"
BC8 = f"{L8} > Anterior and Medial Thigh > The Femoral Triangle"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated flags / fixes / sections files."""
    monkeypatch.setattr(verified, "FLAGS_PATH", tmp_path / "flags.jsonl")
    monkeypatch.setattr(verified, "FIXES_PATH", tmp_path / "fixes.jsonl")
    monkeypatch.setattr(verified, "SECTIONS_PATH", tmp_path / "sections.jsonl")
    monkeypatch.setattr(qa, "FLAGS_PATH", tmp_path / "flags.jsonl")
    return tmp_path


def flag(lecture, breadcrumb, quote=QUOTE, type_="note_line_under_review", status="open", key=None):
    return {"ts": "t", "key": key or f"{lecture}|{breadcrumb}|{quote}", "status": status, "type": type_,
            "lecture": lecture, "breadcrumb": breadcrumb, "notes_quote": quote, "standard_statement": "standard"}


def seed(env, flags, sections=()):
    verified.write_jsonl(verified.FLAGS_PATH, flags)
    verified.write_jsonl(verified.SECTIONS_PATH, [
        {"lecture_title": l, "breadcrumb": b, "text_clean": t} for l, b, t in sections])


# ---- the CLI logic ---------------------------------------------------------------------------------------

def test_resolve_writes_fix_and_closes_flag(env):
    seed(env, [flag(L8, BC8)])
    (fix,) = verified.resolve(1, "confirm_error", "Superior border: inguinal ligament", "TEST", today="2026-10-06")
    assert {"id", "lecture", "breadcrumb", "notes_quote", "correction", "decision", "by", "date"} <= set(fix)
    assert fix["date"] == "2026-10-06" and fix["by"] == "TEST" and fix["notes_quote"] == QUOTE
    f = verified.read_jsonl(verified.FLAGS_PATH)[0]
    assert f["status"] == "resolved" and f["verified_fix_id"] == fix["id"]
    assert verified.list_open() == []
    assert verified.citation(fix) == "Verified by TEST, 2026-10-06"


def test_resolve_rejects_bad_requests(env):
    seed(env, [flag(L8, BC8), flag(L8, BC8, status="resolved", key="k2"),
               {"key": "c", "status": "open", "type": "notes_vs_openstax_conflict", "topic": "x"}])
    with pytest.raises(ValueError, match="correction"):
        verified.resolve(1, "confirm_error", "", "TEST")
    with pytest.raises(ValueError, match="already"):
        verified.resolve(2, "notes_correct", "", "TEST")
    with pytest.raises(ValueError, match="not supported"):
        verified.resolve(3, "notes_correct", "", "TEST")
    with pytest.raises(ValueError, match="no flag"):
        verified.resolve(9, "notes_correct", "", "TEST")
    assert verified.load_fixes() == []


def test_notes_correct_needs_no_correction(env):
    seed(env, [flag(L8, BC8)])
    (fix,) = verified.resolve(1, "notes_correct", "", "Dr. Inglis")
    assert fix["decision"] == "notes_correct" and fix["correction"] == ""


def test_same_quote_in_two_lectures_per_breadcrumb_and_apply_all(env):
    l12, b12 = "Lecture 12 - Leg", "Lecture 12 - Leg > Popliteal Fossa > Popliteal Artery"
    l16, b16 = "Lecture 16 - Thigh", "Lecture 16 - Thigh > Popliteal Fossa > Popliteal Artery"
    q = "Continuation of femoral nerve past the adductor hiatus"
    sections = [(l12, b12, f"- {q}"), (l16, b16, f"- {q}"), ("Lecture 01", "Lecture 01 > X", "- other text")]
    seed(env, [flag(l12, b12, q, key="a")], sections)            # only Lecture 12 was ever flagged
    one = verified.resolve(1, "confirm_error", "continuation of the femoral artery", "TEST")
    assert [f["breadcrumb"] for f in one] == [b12]                # default: just that breadcrumb + quote
    verified.unresolve(one[0]["id"])
    both = verified.resolve(1, "confirm_error", "continuation of the femoral artery", "TEST", apply_all=True)
    assert sorted(f["breadcrumb"] for f in both) == sorted([b12, b16])
    assert len(verified.load_fixes()) == 2


def test_unresolve_removes_fix_and_reopens_flag(env):
    seed(env, [flag(L8, BC8)])
    (fix,) = verified.resolve(1, "reword", "Superior border: inguinal ligament", "TEST")
    assert verified.unresolve(fix["id"]) == 1
    assert verified.load_fixes() == []
    f = verified.read_jsonl(verified.FLAGS_PATH)[0]
    assert f["status"] == "open" and "verified_fix_id" not in f and "decision" not in f
    with pytest.raises(ValueError):
        verified.unresolve(fix["id"])


# ---- Q&A: how lines are treated ---------------------------------------------------------------------------

def chunk(text, lecture=L8, breadcrumb=BC8, source_type="notes"):
    return {"id": "c1", "source_type": source_type, "priority": 2, "lecture": lecture, "breadcrumb": breadcrumb,
            "section_path": breadcrumb.split(" > ")[1:], "text": text, "section_number": "", "source_url": ""}


def item(quote, lecture=L8, breadcrumb=BC8, verdict="confirmed", issue="standard statement"):
    return {"lecture": lecture, "breadcrumb": breadcrumb, "claim_quote": quote, "issue": issue,
            "severity": "high", "type": "factual", "verification": {"verdict": verdict, "reason": "r"}}


def fix(decision="confirm_error", quote=QUOTE, correction="Superior border: inguinal ligament", lecture=L8,
        breadcrumb=BC8):
    return {"id": "vf-0001", "lecture": lecture, "breadcrumb": breadcrumb, "notes_quote": quote,
            "correction": correction, "decision": decision, "by": "Dr. Inglis", "date": "2026-10-06"}


def ctx(confirmed=(), doubtful=(), fixes=()):
    return {"confirmed": list(confirmed), "doubtful": list(doubtful), "fixes": list(fixes)}


def ids():
    return {"U": 0, "D": 0, "V": 0}


TEXT = f"- Medial – adductor longus\n- {QUOTE}\n- Lateral – sartorius"


def test_verified_fix_replaces_the_line_and_wins_over_factcheck():
    text, marks = qa.annotate_chunk(chunk(TEXT), ctx([item(QUOTE)], fixes=[fix()]), ids())
    assert QUOTE not in text and "[LINE CORRECTED V1]" in text
    assert [m[0] for m in marks] == ["verified"]          # the fact-check mask is not applied on top of it
    assert "Medial – adductor longus" in text             # other lines untouched


def test_notes_correct_stops_masking_and_flagging():
    text, marks = qa.annotate_chunk(chunk(TEXT), ctx([item(QUOTE)], [item(QUOTE, verdict="doubtful")],
                                                     [fix("notes_correct", correction="")]), ids())
    assert text == TEXT and marks == []


def test_verified_fix_is_per_breadcrumb():
    other = "Lecture 12 - Leg > Popliteal Fossa > Popliteal Artery"
    c = chunk(TEXT, lecture="Lecture 12 - Leg", breadcrumb=other)
    text, marks = qa.annotate_chunk(c, ctx(fixes=[fix()]), ids())      # the fix is for Lecture 08, not 12
    assert text == TEXT and marks == []


def test_doubtful_line_is_kept_and_tagged_not_masked():
    text, marks = qa.annotate_chunk(chunk(TEXT), ctx(doubtful=[item(QUOTE, verdict="doubtful")]), ids())
    assert QUOTE in text and "[flagged for review D1]" in text and "LINE UNDER REVIEW" not in text
    assert [m[0] for m in marks] == ["doubtful"]


def test_confirmed_line_is_still_masked():
    text, marks = qa.annotate_chunk(chunk(TEXT), ctx([item(QUOTE)]), ids())
    assert QUOTE not in text and "[LINE UNDER REVIEW U1]" in text and marks[0][0] == "review"


def test_prompt_carries_verified_fix_with_its_citation():
    hit = Hit(chunk=chunk(TEXT), score=1, rrf=1, cosine=0.8, bm25=1, dense_rank=1, bm25_rank=1)
    msg, marks = qa.build_user_message("q", [hit], "", ctx(fixes=[fix()]), {})
    assert '<verified_fix id="V1"' in msg and 'cite="Verified by Dr. Inglis, 2026-10-06"' in msg and 'by="Dr. Inglis"' in msg
    assert "Superior border: inguinal ligament" in msg and QUOTE not in msg


def test_scope_rule_is_in_the_system_prompt():
    assert "treatment" in qa.SYSTEM_PROMPT and "covered=false" in qa.SYSTEM_PROMPT
    assert "Verified fixes" in qa.SYSTEM_PROMPT and "(flagged for review, see fact-check)" in qa.SYSTEM_PROMPT


# ---- Q&A end to end with a canned model -------------------------------------------------------------------

class FakeSearcher:
    def __init__(self, chunks):
        self.hits = [Hit(chunk=c, score=1, rrf=1, cosine=0.8, bm25=1, dense_rank=1, bm25_rank=1) for c in chunks]

    def search(self, question):
        return SearchResult(query=question, found=True, hits=self.hits, best_cosine=0.8)


def canned(**over):
    base = {"covered": True, "basis": "course_notes", "answer": "answer", "conflicts": [],
            "under_review_addressed": [], "verified_used": [], "doubtful_used": []}
    base.update(over)
    return lambda client, model, msg, **kw: (base, {"input_tokens": 1, "output_tokens": 1})


def test_doubtful_use_is_logged_as_note_line_doubtful(env, monkeypatch):
    monkeypatch.setattr(qa, "call_claude", canned(doubtful_used=["D1"]))
    c = ctx(doubtful=[item(QUOTE, verdict="doubtful")])
    out = qa.answer_question(FakeSearcher([chunk(TEXT)]), None, "m", "q", "", c, {})
    (entry,) = verified.read_jsonl(verified.FLAGS_PATH)
    assert entry["type"] == "note_line_doubtful" and entry["status"] == "open" and entry["notes_quote"] == QUOTE
    assert out["flags"][0][0].startswith("doubtful")
    qa.answer_question(FakeSearcher([chunk(TEXT)]), None, "m", "q again", "", c, {})   # no duplicate entry
    assert len(verified.read_jsonl(verified.FLAGS_PATH)) == 1


def test_doubtful_line_not_used_is_not_logged(env, monkeypatch):
    monkeypatch.setattr(qa, "call_claude", canned())
    qa.answer_question(FakeSearcher([chunk(TEXT)]), None, "m", "q", "", ctx(doubtful=[item(QUOTE, verdict="doubtful")]), {})
    assert verified.read_jsonl(verified.FLAGS_PATH) == []


def test_verified_use_is_reported_and_nothing_is_flagged(env, monkeypatch):
    monkeypatch.setattr(qa, "call_claude", canned(verified_used=["V1"]))
    out = qa.answer_question(FakeSearcher([chunk(TEXT)]), None, "m", "q", "", ctx([item(QUOTE)], fixes=[fix()]), {})
    assert [f["id"] for _, f in out["verified"]] == ["vf-0001"]
    assert verified.read_jsonl(verified.FLAGS_PATH) == []


def test_model_level_decline_is_reported(env, monkeypatch):
    monkeypatch.setattr(qa, "call_claude", canned(covered=False, basis="not_covered", answer="no clinical advice"))
    out = qa.answer_question(FakeSearcher([chunk("heart text")]), None, "m", "How do I diagnose a heart attack?", "",
                             ctx(), {})
    assert out["basis"] == "not_covered" and any("declined" in n for n in out["notes"])
