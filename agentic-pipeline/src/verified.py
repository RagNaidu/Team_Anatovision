"""Verified fixes: Dr. Inglis's replies to flagged lines of his notes. The notes files are NEVER edited.

Files:
  data/flags.jsonl           flags written by Q&A mode (status "open" -> "resolved")
  data/verified_fixes.jsonl  one record per verified decision:
                             {id, lecture, breadcrumb, notes_quote, correction, decision, by, date, ...}

Decisions:
  confirm_error  the line in the notes is wrong; `correction` is the right statement
  reword         the line should be worded differently; `correction` is Dr. Inglis's wording
  notes_correct  the line is fine as written: Q&A stops flagging or masking it

Q&A mode (src/modes/qa.py) treats a verified fix as the TOP-priority source for the matching line
(same lecture + breadcrumb + quote).

CLI (repo root):
  .venv/bin/python -m src.verified list
  .venv/bin/python -m src.verified resolve <n> --decision confirm_error|notes_correct|reword \\
        --correction "text" --by "Dr. Inglis" [--apply-all-same-quote]
  .venv/bin/python -m src.verified unresolve <fix-id>      remove a fix and reopen its flag(s)
<n> is the line number of the flag in data/flags.jsonl (as shown by `list`; it stays the same).
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAGS_PATH = ROOT / "data" / "flags.jsonl"
FIXES_PATH = ROOT / "data" / "verified_fixes.jsonl"
SECTIONS_PATH = ROOT / "data" / "processed" / "sections.jsonl"

DECISIONS = ("confirm_error", "notes_correct", "reword")
RESOLVABLE_TYPES = ("note_line_under_review", "note_line_doubtful", "note_line_wording", "note_line_typo")


def norm(text):
    return re.sub(r"\s+", " ", text).strip()


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    tmp.replace(path)


def load_fixes(path=None):
    return read_jsonl(path or FIXES_PATH)


def citation(fix):
    return f"Verified by {fix['by']}, {fix['date']}"


def find_same_quote(quote, sections_path=None):
    """Every (lecture, breadcrumb) in the notes whose text contains this exact quote."""
    q = norm(quote)
    found = []
    for s in read_jsonl(sections_path or SECTIONS_PATH):
        if q and q in norm(s["text_clean"]):
            found.append((s["lecture_title"], s["breadcrumb"]))
    return list(dict.fromkeys(found))


def list_open(flags=None):
    flags = read_jsonl(FLAGS_PATH) if flags is None else flags
    return [(n, f) for n, f in enumerate(flags, 1) if f.get("status") == "open"]


def resolve(n, decision, correction, by, apply_all=False, today=None):
    """Create verified fix(es) for flag #n and mark the matching flag(s) resolved. Returns the new fixes."""
    flags = read_jsonl(FLAGS_PATH)
    if not 1 <= n <= len(flags):
        raise ValueError(f"no flag #{n} (data/flags.jsonl has {len(flags)} lines)")
    flag = flags[n - 1]
    if flag.get("status") != "open":
        raise ValueError(f"flag #{n} is already {flag.get('status')}")
    if flag["type"] not in RESOLVABLE_TYPES:
        raise ValueError(f"flag #{n} is a '{flag['type']}' flag; only {', '.join(RESOLVABLE_TYPES)} can be "
                         "resolved with a verified fix (notes-vs-OpenStax conflicts are not supported yet)")
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {', '.join(DECISIONS)}")
    if decision != "notes_correct" and not norm(correction or ""):
        raise ValueError(f"--correction is required for {decision}")

    quote = flag["notes_quote"]
    targets = [(flag["lecture"], flag["breadcrumb"])]
    if apply_all:
        targets += [t for t in find_same_quote(quote) if t not in targets]

    fixes = read_jsonl(FIXES_PATH)
    next_id = max([int(f["id"].split("-")[1]) for f in fixes] + [0]) + 1
    new = []
    for lecture, breadcrumb in targets:
        if any(f["lecture"] == lecture and f["breadcrumb"] == breadcrumb and norm(f["notes_quote"]) == norm(quote)
               for f in fixes):
            continue  # already decided for this exact line
        rec = {"id": f"vf-{next_id:04d}", "lecture": lecture, "breadcrumb": breadcrumb, "notes_quote": quote,
               "correction": norm(correction or ""), "decision": decision, "by": by,
               "date": today or date.today().isoformat()}
        next_id += 1
        fixes.append(rec)
        new.append(rec)
    id_for = {(f["lecture"], f["breadcrumb"]): f["id"] for f in fixes if norm(f["notes_quote"]) == norm(quote)}
    for f in flags:  # every open flag for those exact lines
        key = (f.get("lecture"), f.get("breadcrumb"))
        if f.get("status") == "open" and f.get("type") in RESOLVABLE_TYPES and key in id_for \
                and norm(f.get("notes_quote", "")) == norm(quote):
            f.update(status="resolved", decision=decision, resolved_by=by,
                     resolved_date=today or date.today().isoformat(), verified_fix_id=id_for[key])
    write_jsonl(FIXES_PATH, fixes)
    write_jsonl(FLAGS_PATH, flags)
    return new


def unresolve(fix_id):
    """Remove a verified fix and reopen the flag(s) it resolved. Returns the number of flags reopened."""
    fixes = read_jsonl(FIXES_PATH)
    if not any(f["id"] == fix_id for f in fixes):
        raise ValueError(f"no verified fix {fix_id}")
    write_jsonl(FIXES_PATH, [f for f in fixes if f["id"] != fix_id])
    flags, reopened = read_jsonl(FLAGS_PATH), 0
    for f in flags:
        if f.get("verified_fix_id") == fix_id:
            for k in ("decision", "resolved_by", "resolved_date", "verified_fix_id"):
                f.pop(k, None)
            f["status"] = "open"
            reopened += 1
    write_jsonl(FLAGS_PATH, flags)
    return reopened


def cmd_list():
    flags = read_jsonl(FLAGS_PATH)
    open_items = list_open(flags)
    print(f"{len(open_items)} open of {len(flags)} flags in {FLAGS_PATH.relative_to(ROOT)}\n")
    for n, f in open_items:
        kind = {"note_line_under_review": "CONFIRMED-ERROR?", "note_line_doubtful": "doubtful",
                "note_line_wording": "wording", "note_line_typo": "typo",
                "notes_vs_openstax_conflict": "notes vs OpenStax"}.get(f["type"], f["type"])
        print(f"#{n:<3} [{kind}] {f.get('breadcrumb', f.get('topic', ''))[:110]}")
        if "notes_quote" in f:
            print(f'      notes say: "{f["notes_quote"][:160]}"')
            print(f'      standard : {(f.get("standard_statement") or f.get("issue") or "")[:200]}')
        else:
            print(f'      topic: {f.get("topic")} | notes: {f.get("notes_say", "")[:100]} | OpenStax: {f.get("openstax_say", "")[:100]}')
    resolved = [f for f in flags if f.get("status") == "resolved"]
    if resolved:
        print(f"\n{len(resolved)} resolved (see data/verified_fixes.jsonl)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("resolve")
    r.add_argument("n", type=int)
    r.add_argument("--decision", required=True, choices=DECISIONS)
    r.add_argument("--correction", default="")
    r.add_argument("--by", required=True)
    r.add_argument("--apply-all-same-quote", action="store_true")
    u = sub.add_parser("unresolve")
    u.add_argument("fix_id")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "list":
            cmd_list()
        elif args.cmd == "resolve":
            new = resolve(args.n, args.decision, args.correction, args.by, args.apply_all_same_quote)
            print(f"Resolved flag #{args.n} as {args.decision}. Verified fix(es) written:")
            for f in new:
                print(f"  {f['id']}  {f['breadcrumb'][:100]}")
            if not new:
                print("  (none new: a verified fix already existed for this line)")
        else:
            n = unresolve(args.fix_id)
            print(f"Removed {args.fix_id}; reopened {n} flag(s).")
    except ValueError as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
