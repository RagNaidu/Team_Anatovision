"""Bank operations used by the API: listing with statistics, AI checks, import preview and commit."""
import json
import time
import uuid
from pathlib import Path

from src.qbank import checks, importer, stats as bank_stats
from src.qbank import store as S
from src.qbank.store import BankError, BankStore

IMPORT_TTL = 3600


def stats_map(bank, quiz_store=None):
    from src.quiz.store import QuizStore
    qs = quiz_store or QuizStore()
    by_item = {q["quiz_item_id"]: q["id"] for q in bank.all() if q["quiz_item_id"]}
    cache = {}

    def quiz_item(i):
        if i not in cache:
            cache[i] = qs.item(i)
        return cache[i]
    return bank_stats.compute(qs.attempts(), quiz_item, by_item)


def counts_now():
    bank = BankStore()
    return S.counts(bank.all(), stats_map(bank))


def listing(bank, f, page=1, per=50):
    qs = bank.all()
    stats = stats_map(bank)
    kept = [q for q in qs if S.matches(q, f, stats.get(q["id"]))]
    rows = [S.row_of(q, stats.get(q["id"])) for q in kept]
    lectures = sorted({q["data"]["lecture"] or q["data"]["guide"] for q in qs if q["data"]["lecture"] or q["data"]["guide"]})
    return {"items": rows[(page - 1) * per: page * per], "total": len(rows), "counts": S.counts(qs, stats), "lectures": lectures,
            "regions": sorted({q["data"]["region"] for q in qs if q["data"]["region"]}), "tags": sorted({t for q in qs for t in q["data"]["tags"]}, key=str.lower)}


def filtered(bank, f):
    stats = stats_map(bank)
    return [q for q in bank.all() if S.matches(q, f, stats.get(q["id"]))]


def detail(bank, qid):
    q = bank.get(qid)
    if q is None:
        raise BankError("That question was not found.", 404)
    st = stats_map(bank).get(qid) or {"n": 0, "p_correct": None, "discrimination": None, "distractors": [], "flags": [], "enough": False}
    vers = bank.versions(qid)
    changes = {v["version"]: [d["field"] for d in S.diff_data(vers[i + 1]["data"], v["data"])] if i + 1 < len(vers) else ["created"] for i, v in enumerate(vers)}
    flags = q["flags"] + [{**f, "dismissed": False} for f in st["flags"]]
    return {"id": qid, "version": q["version"], "created_at": q["created"], "updated_at": q["updated"], "data": q["data"], "sample": q["data"]["sample"], "flags": flags,
            "needs_recheck": q["recheck"], "stats": {"n": st["n"], "p_correct": st["p_correct"], "discrimination": st["discrimination"], "enough": st["enough"], "distractors": st["distractors"],
                                                     "min_for_stats": bank_stats.MIN_FOR_STATS, "min_for_flags": bank_stats.MIN_FOR_FLAGS},
            "comments": [{"id": c["id"], "at": c["ts"], "by": c["by"], "text": c["text"]} for c in bank.comments(qid)],
            "versions": [{"version": v["version"], "at": v["ts"], "by": v["by"], "note": v["note"], "changed": changes[v["version"]]} for v in vers]}


def run_local_checks(bank, qid):
    q = bank.get(qid)
    others = [(o["id"], o["data"]) for o in bank.all()]
    bank.replace_flags(qid, ("nbme", "duplicate"), checks.local_checks(q["data"], qid, others))


def run_ai_checks(bank, qid, rt):
    """Rule checks, duplicates, auto-tag (fills EMPTY fields only) and the answer-key check. Flags only: status and text are never changed."""
    run_local_checks(bank, qid)
    q = bank.get(qid)
    tag, tag_flags = checks.auto_tag(q["data"], rt.searcher)
    patch = {k: v for k, v in tag.items() if v and not q["data"].get(k)}
    if patch:
        bank.update(qid, patch, "ai", "linked to the notes by content")
    q = bank.get(qid)
    key_flags = checks.key_check(q["data"], rt.searcher, rt.client, rt.model)
    bank.replace_flags(qid, ("tag", "key"), tag_flags + key_flags)


def create_with_checks(bank, data, by, note="created", rt=None):
    q = bank.create(data, by, note)
    run_local_checks(bank, q["id"])
    return bank.get(q["id"])


# ---------------------------------------------------------------- import (parsed rows are kept on disk between the preview and the commit)
def _dir(bank):
    d = Path(bank.path).parent / "imports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sweep(bank):
    for p in _dir(bank).glob("*.json"):
        if time.time() - p.stat().st_mtime > IMPORT_TTL:
            p.unlink(missing_ok=True)


def preview_import(bank, filename, data, mapping=None, import_id=None):
    _sweep(bank)
    if import_id:
        p = _dir(bank) / f"{import_id}.json"
        if not p.exists():
            raise BankError("That import has expired. Upload the file again.", 404)
        saved = json.loads(p.read_text(encoding="utf-8"))
        headers, rows, filename = saved["headers"], saved["rows"], saved["filename"]
    else:
        headers, rows = importer.read_table(filename, data)
        import_id = uuid.uuid4().hex[:16]
        (_dir(bank) / f"{import_id}.json").write_text(json.dumps({"headers": headers, "rows": rows, "filename": filename}), encoding="utf-8")
    mapping = mapping or importer.suggest_mapping(headers)
    return {"import_id": import_id, "filename": filename, "headers": headers, "rows": rows[:5], "n_rows": len(rows), "mapping": mapping,
            "fields": [{"field": f, "label": importer.LABEL[f]} for f in importer.FIELDS], **evaluate(bank, headers, rows, mapping)}


def evaluate(bank, headers, rows, mapping, limit=8):
    existing = [(q["id"], q["data"]) for q in bank.all()]
    problems, ready, dups, qs = [], 0, 0, []
    seen = []
    for i, r in enumerate(rows, 1):
        d, problem = importer.to_question(r, headers, mapping, {"status": "draft", "use": "exam_secure", "source": "imported"})
        if d is None:
            problems.append({"row": str(i), "problem": problem})
            continue
        near = checks.near_duplicates(d, existing + seen)
        seen.append((f"row {i}", d))
        if near:
            dups += 1
        ready += 1
        if len(qs) < limit:
            qs.append({"row": str(i), "lead_in": d["lead_in"], "options": " | ".join(o["text"] for o in d["options"]), "answer": d["answer"], "duplicate": f"{near[0][0]} ({round(near[0][1] * 100)}%)" if near else ""})
    return {"questions": qs, "problems": problems[:50], "duplicates": dups, "ready": ready}


def commit_import(bank, import_id, mapping, status, use, skip_duplicates, by, rt=None):
    p = _dir(bank) / f"{import_id}.json"
    if not p.exists():
        raise BankError("That import has expired. Upload the file again.", 404)
    saved = json.loads(p.read_text(encoding="utf-8"))
    headers, rows = saved["headers"], saved["rows"]
    if "lead_in" not in mapping or not any(f"option_{c}" in mapping for c in "ab"):
        raise BankError("Map at least the question and two options.")
    existing = [(q["id"], q["data"]) for q in bank.all()]
    created, skipped, problems, flagged = 0, 0, [], 0
    for i, r in enumerate(rows, 1):
        d, problem = importer.to_question(r, headers, mapping, {"status": status, "use": use, "source": "imported"})
        if d is None:
            problems.append({"row": str(i), "problem": problem})
            continue
        near = checks.near_duplicates(d, existing)
        if near and skip_duplicates and near[0][1] >= 0.9:
            skipped += 1
            continue
        q = bank.create(d, by, f"imported from {saved['filename']}, row {i}")
        existing.append((q["id"], q["data"]))
        flags = checks.local_checks(q["data"], q["id"], existing)
        if rt is not None:
            try:
                tag, tag_flags = checks.auto_tag(q["data"], rt.searcher)
                patch = {k: v for k, v in tag.items() if v and not q["data"].get(k)}
                if patch:
                    bank.update(q["id"], patch, "ai", "linked to the notes by content")
                flags += tag_flags
            except Exception:
                pass
        bank.replace_flags(q["id"], ("nbme", "duplicate", "tag"), flags)
        created += 1
        flagged += bool([f for f in flags if f["severity"] == "warn"])
    p.unlink(missing_ok=True)
    return {"created": created, "skipped_duplicates": skipped, "problems": problems[:50], "flagged": flagged}
