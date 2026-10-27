"""The professor's review queue: fact-check items (reports/factcheck_all.json) and the flags Q&A logged (data/flags.jsonl).

Everything here is an AI-generated suggestion until Dr. Inglis decides. A decision goes through the SAME function as the
command line (`src.verified.resolve`): this module only finds or creates the matching flag first, because a fact-check item
only has a line in flags.jsonl once a student's question touched it (or once someone decides it here).

Tiers (as in the report): likely_factual (confirmed by the second check), second_look (wording, or factual but doubtful),
typo. 'Start here' is the report's own list: confirmed + severity high, best confidence first, at most START_HERE_MAX.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from src import reports, verified
from src.audit import factcheck

ROOT = Path(__file__).resolve().parents[1]
FACTCHECK_PATH = ROOT / "reports" / "factcheck_all.json"
START_HERE_MAX = factcheck.START_HERE_MAX
FLAG_TYPE = {"likely_factual": ("note_line_under_review", "review"), "doubtful": ("note_line_doubtful", "doubtful"),
             "wording": ("note_line_wording", "wording"), "typo": ("note_line_typo", "typo")}
TABS = ("start_here", "likely_factual", "second_look", "typo")


def kind_of(issue):
    """Which flag kind an item becomes: likely_factual / doubtful / wording / typo."""
    if issue["tier"] == "likely_factual":
        return "likely_factual"
    if issue["tier"] == "typo":
        return "typo"
    return "doubtful" if issue["type"] == "factual" else "wording"


def flag_key(issue):
    prefix = FLAG_TYPE[kind_of(issue)][1]
    return f"{prefix}|{issue['lecture']}|{issue['breadcrumb']}|{issue['claim_quote']}"


def load_report(path=None):
    """factcheck_all.json plus the per-file reports of uploaded lectures (see src/reports.py)."""
    return reports.load_merged(path or FACTCHECK_PATH)


def basis_text(issue):
    ref = issue.get("reference") or {}
    if issue.get("basis") == "openstax" and ref.get("cite"):
        return ref["cite"]
    return "general anatomy knowledge (not from the open text)"


def decisions():
    """flag key -> {status, n, decision, by, date, fix_id, student_question} from data/flags.jsonl."""
    out = {}
    for n, f in enumerate(verified.read_jsonl(verified.FLAGS_PATH), 1):
        out[f.get("key")] = {"n": n, "status": f.get("status", "open"), "decision": f.get("decision"),
                             "by": f.get("resolved_by"), "date": f.get("resolved_date"), "fix_id": f.get("verified_fix_id"),
                             "seen_in_question": bool(f.get("question")) and f.get("question") != "(review queue)"}
    return out


def queue(report=None, state=None):
    """Every item of the report with its decision state. Each item: the report's own fields + `key`, `kind`, `decision`."""
    report = report if report is not None else load_report()
    state = state if state is not None else decisions()
    items = []
    for i, issue in enumerate(report["issues"]):
        key = flag_key(issue)
        d = state.get(key, {})
        items.append({**issue, "idx": i, "key": key, "kind": kind_of(issue), "basis_text": basis_text(issue),
                      "decision": d if d else {"status": "open"}})
    return items


def start_here(items):
    high = sorted((i for i in items if i["tier"] == "likely_factual" and i["severity"] == "high"),
                  key=lambda i: (-i["confidence"], i["lecture"], i["order"]))
    return high[:START_HERE_MAX]


def tab_items(items, tab):
    if tab == "start_here":
        return start_here(items)
    return [i for i in items if i["tier"] == tab]


def ensure_flag(issue, source="reports/factcheck_all.json (review queue)"):
    """The 1-based line number of this item's flag in flags.jsonl, creating the flag if it does not exist yet."""
    key = flag_key(issue)
    flags = verified.read_jsonl(verified.FLAGS_PATH)
    for n, f in enumerate(flags, 1):
        if f.get("key") == key:
            return n
    flag_type = FLAG_TYPE[kind_of(issue)][0]
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "key": key, "status": "open",
             "type": flag_type, "question": "(review queue)", "lecture": issue["lecture"], "breadcrumb": issue["breadcrumb"],
             "notes_quote": issue["claim_quote"], "standard_statement": issue["issue"], "severity": issue["severity"],
             "source": source}
    if issue["type"] == "factual":
        entry["verifier_reason"] = issue.get("verification", {}).get("reason", "")
    flags.append(entry)
    verified.write_jsonl(verified.FLAGS_PATH, flags)
    return len(flags)


def decide(issue, decision, correction, by, apply_all=False):
    """Record Dr. Inglis's decision with the same code as `python -m src.verified resolve`. Returns the new fixes."""
    by = (by or "").strip()
    if not by:
        raise ValueError("Enter the name to record as the person who verified this.")
    if decision in ("confirm_error", "reword") and not (correction or "").strip():
        raise ValueError("A correction is required to confirm an error or to reword a line: type the corrected wording first.")
    n = ensure_flag(issue)
    return verified.resolve(n, decision, correction, by, apply_all)


def same_quote_places(issue):
    """Other (lecture, breadcrumb) places where this exact quote appears in the notes (for 'apply to all')."""
    return [p for p in verified.find_same_quote(issue["claim_quote"]) if p != (issue["lecture"], issue["breadcrumb"])]


def open_conflicts():
    """Flags that are not line-level (notes vs OpenStax): they cannot be resolved with a verified fix yet."""
    return [(n, f) for n, f in enumerate(verified.read_jsonl(verified.FLAGS_PATH), 1)
            if f.get("type") == "notes_vs_openstax_conflict" and f.get("status") == "open"]


def ledger():
    """Verified fixes, newest first."""
    return list(reversed(verified.load_fixes()))


def undo(fix_id):
    return verified.unresolve(fix_id)


# ----------------------------------------------------------------------------
# student reports and bulk actions
# ----------------------------------------------------------------------------

def open_student_reports():
    """[(flag number, flag)] for reports students sent with 'Report an error' that nobody has handled yet."""
    return [(n, f) for n, f in enumerate(verified.read_jsonl(verified.FLAGS_PATH), 1)
            if f.get("type") == "student_report" and f.get("status") == "open"]


def close_report(n):
    """Mark student report #n as handled (it stays in the file; it just leaves the open list)."""
    flags = verified.read_jsonl(verified.FLAGS_PATH)
    if not 1 <= n <= len(flags) or flags[n - 1].get("type") != "student_report":
        raise ValueError(f"flag #{n} is not a student report")
    flags[n - 1]["status"] = "handled"
    flags[n - 1]["handled_ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    verified.write_jsonl(verified.FLAGS_PATH, flags)


def bulk_typo_items(items, lecture):
    """The open typo items of one lecture: the only thing a bulk action may touch (never a factual item)."""
    return [i for i in items if i["kind"] == "typo" and i["lecture"] == lecture and i["decision"]["status"] != "resolved"]


def mark_typos_reviewed(items, lecture, by):
    """Record 'the notes are correct as written' for every open typo item of the lecture. Returns how many were recorded.
    A typo is not masked or corrected in student answers either way; this only takes it off the open list."""
    todo = bulk_typo_items(items, lecture)
    for item in todo:
        decide(item, "notes_correct", "", by)
    return len(todo)
