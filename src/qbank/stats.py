"""Item statistics from real quiz attempts. Computed on demand; flags only, nothing is ever retired automatically."""
import math

MIN_FOR_STATS = 10         # below this, only the counts are shown
MIN_FOR_FLAGS = 20         # a negative discrimination or an extreme difficulty is only flagged with at least this many attempts
EASY, HARD = 0.95, 0.20


def point_biserial(correct, rest):
    """Correlation between getting this item right (0/1) and the score on the rest of the quiz."""
    n = len(correct)
    if n < 3:
        return None
    mc, mr = sum(correct) / n, sum(rest) / n
    sc = math.sqrt(sum((c - mc) ** 2 for c in correct) / n)
    sr = math.sqrt(sum((r - mr) ** 2 for r in rest) / n)
    if sc == 0 or sr == 0:
        return None
    return sum((c - mc) * (r - mr) for c, r in zip(correct, rest)) / (n * sc * sr)


def owner_of(item_id, by_item):
    """The bank question an item id belongs to: 'bank:<qid>:v<n>' items, or an AI item linked through quiz_item_id."""
    if item_id.startswith("bank:"):
        return item_id.split(":")[1]
    return by_item.get(item_id)


def compute(attempts, quiz_item, by_item):
    """-> {qid: {"n", "p_correct", "discrimination", "distractors": [{"text", "picks", "correct"}], "flags": [...]}}.
    quiz_item(item_id) returns the frozen quiz item (for its options and key); by_item maps an AI quiz-item id to its bank id."""
    rec = {}
    for a in attempts:
        total = a["score"]
        for k, iid in enumerate(a["item_ids"]):
            qid = owner_of(iid, by_item)
            if not qid:
                continue
            it = quiz_item(iid)
            if it is None:
                continue
            sel = a["selections"].get(k) or []
            ok = sorted(sel) == sorted(it["answer_ids"])
            r = rec.setdefault(qid, {"correct": [], "rest": [], "picks": {}})
            r["correct"].append(int(ok))
            r["rest"].append(total - int(ok))
            for o in it["options"]:
                row = r["picks"].setdefault(o["text"], {"text": o["text"], "picks": 0, "correct": o["id"] in it["answer_ids"]})
                row["picks"] += o["id"] in sel
    out = {}
    for qid, r in rec.items():
        n = len(r["correct"])
        p = sum(r["correct"]) / n
        disc = point_biserial(r["correct"], r["rest"]) if n >= MIN_FOR_STATS else None
        flags = []
        if n >= MIN_FOR_FLAGS:
            if disc is not None and disc < 0:
                flags.append({"kind": "stats", "code": "negative_discrimination", "severity": "warn", "message": f"Students who do well on the rest of the quiz miss this more often (discrimination {disc:.2f}, {n} attempts). Check the key and the wording."})
            if p >= EASY:
                flags.append({"kind": "stats", "code": "too_easy", "severity": "info", "message": f"{round(p * 100)}% answered correctly ({n} attempts): almost everyone gets it."})
            if p <= HARD:
                flags.append({"kind": "stats", "code": "too_hard", "severity": "warn", "message": f"Only {round(p * 100)}% answered correctly ({n} attempts). Check the key and the wording."})
        out[qid] = {"n": n, "p_correct": round(p, 3), "discrimination": None if disc is None else round(disc, 3), "distractors": list(r["picks"].values()), "flags": flags,
                    "enough": n >= MIN_FOR_STATS}
    return out
