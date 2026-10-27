"""Map dissection guides to lectures by CONTENT ONLY (file titles and class numbers are ignored; the client says titles may be wrong).

1. Embed every guide slide and every lecture section (bge-small). For each guide, a lecture's score is how well the lecture's sections
   cover the guide's slides (mean over slides of the best section similarity). The 3 best lectures are the candidates.
2. gpt-oss-120b judges, seeing only the guide's text and the three candidates' headings and text under anonymous names (no titles,
   no numbers): which candidate(s), if any, cover what the guide dissects, with the key terms as evidence and a confidence.
   "None" leaves the guide unmatched.
Results are cached in data/processed/guide_map_cache.json, so a rerun costs nothing. Entries marked "locked": true are kept as they are.
"""
import hashlib
import json
import os
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

from src import llm
from src.ingest import guides as G

CACHE_PATH = G.ROOT / "data" / "processed" / "guide_map_cache.json"
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "openai/gpt-oss-120b")
TOP = 3
GUIDE_CHARS = 3500
LECTURE_CHARS = 4200
DIGEST_VERSION = 3

SYSTEM = ("You match a dissection-lab guide to the lecture notes that cover the same anatomy. You get the GUIDE (the text of its slides) and "
          "up to three CANDIDATE lectures named A, B, C, shown by their section headings and an excerpt. Names and titles are hidden on purpose: "
          "decide only from the content. A candidate matches when its notes cover a substantial part of the structures and the region the guide has the "
          "student dissect (it need not cover every step; sharing only a few words is not enough). Pick the best match and, only if the guide clearly spans two lectures, a second. "
          "If no candidate covers the guide's region (for example the guide is about the heart and none of the candidates is), answer none. "
          "Be strict: a candidate from a different body region is NOT a match.\n"
          'Reply with ONE JSON object: {"matches": ["A"], "none": false, "confidence": "high"|"medium"|"low", '
          '"key_terms": ["up to 8 structures that appear in BOTH the guide and the matched lecture"], "reason": "one sentence"}. '
          'If none: {"matches": [], "none": true, "confidence": "high", "key_terms": [], "reason": "..."}.')
SCHEMA = {"type": "object", "properties": {"matches": {"type": "array", "items": {"type": "string", "enum": ["A", "B", "C"]}},
                                            "none": {"type": "boolean"}, "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                                            "key_terms": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}},
          "required": ["matches", "none", "confidence", "key_terms", "reason"], "additionalProperties": False}


def lecture_sections(path=None):
    out = defaultdict(list)
    titles = {}
    for line in Path(path or G.SECTIONS_PATH).read_text(encoding="utf-8").splitlines():
        if line.strip():
            s = json.loads(line)
            titles[s["lecture_id"]] = s["lecture_title"]
            heading = s["breadcrumb"].split(" > ", 1)[-1] if " > " in s["breadcrumb"] else s["breadcrumb"]
            out[s["lecture_id"]].append({"heading": heading, "text": s["text_clean"]})
    return out, titles


def embed(model, texts):
    return model.encode(texts, batch_size=32, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)


def candidates(model, guide_slides, lectures, top=TOP):
    """guide_slides: {file: [slide text]}, lectures: {id: [section dict]}. -> {file: [(lecture_id, score)] best first}."""
    lec_ids = list(lectures)
    lec_vecs = {lid: embed(model, [f"{s['heading']}\n{s['text']}" for s in lectures[lid]]) for lid in lec_ids}
    out = {}
    for fn, texts in guide_slides.items():
        g = embed(model, texts)
        scores = [(lid, float(np.mean((g @ lec_vecs[lid].T).max(axis=1)))) for lid in lec_ids]
        out[fn] = sorted(scores, key=lambda t: -t[1])[:top]
    return out


def lecture_digest(sections, chars=LECTURE_CHARS):
    """Every section's heading and its first words, so a long lecture is represented from start to end (not only its first pages)."""
    per = max(120, chars // max(1, len(sections)))
    lines = [f"- {s['heading'].split(' > ')[-1]}: {re.sub(chr(10) + '|' + chr(32) + '{2,}', ' ', s['text'])[:per]}" for s in sections]
    return "\n".join(lines)[:chars]


def _cache():
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def judge(client, fn, guide_text, cand_ids, lectures, cache, variant=0):
    """-> the judge's answer for one guide (cached). Candidates are shown rotated by a hash of the file name, to spread position bias."""
    key = hashlib.sha1((f"v{DIGEST_VERSION}|{variant}|" + fn + "|" + "|".join(cand_ids) + "|" + guide_text[:200]).encode()).hexdigest()
    if key in cache:
        return cache[key]
    rot = (int(hashlib.md5(fn.encode()).hexdigest(), 16) + variant) % len(cand_ids)
    order = cand_ids[rot:] + cand_ids[:rot]
    names = dict(zip("ABC", order))
    user = f"GUIDE:\n{guide_text[:GUIDE_CHARS]}\n\n" + "\n\n".join(f"CANDIDATE {n} (section headings with their first words):\n{lecture_digest(lectures[lid])}" for n, lid in names.items())
    data = None
    for attempt in (1, 2):                                   # one retry only
        try:
            data, _ = llm.complete_json(client, SYSTEM, [{"role": "user", "content": user}], 4000, SCHEMA, JUDGE_MODEL)
            break
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"[:200]
    if data is None:
        return {"error": err}
    data["matched_ids"] = [names[m] for m in data["matches"] if m in names]
    cache[key] = data
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    return data


CONFLICT_SYSTEM = ("Several dissection guides were matched to the same lecture. You get the LECTURE (its section headings with their first words) "
                   "and the guides A, B, ... (their slide text). Decide, from content only, which guides' regions and structures this lecture actually "
                   "covers. A guide about a different body region than the lecture is NOT covered, even if a few organs are mentioned in both. "
                   'Reply with ONE JSON object: {"covered": ["A"], "reason": "one sentence"} (covered may list several letters or none).')
CONFLICT_SCHEMA = {"type": "object", "properties": {"covered": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}},
                   "required": ["covered", "reason"], "additionalProperties": False}
RANK = {"high": 3, "medium": 2, "low": 1}


def merge_runs(runs, emb_rank):
    """Two judge runs (different candidate order) -> (ids, confidence, note). Both must agree for 'high'."""
    good = [r for r in runs if "error" not in r]
    if not good:
        return [], "unmatched", "the judge failed"
    sets = [r.get("matched_ids", []) if not r.get("none") else [] for r in good]
    if all(not x for x in sets):
        return [], "unmatched", ""
    agreed = [i for i in sets[0] if all(i in x for x in sets[1:])]
    conf = min(RANK[r["confidence"]] for r in good)
    if agreed:
        same = all(set(x) == set(agreed) for x in sets) and len(good) == len(runs)
        c = conf if same else min(conf, 2)
        return agreed[:2], {3: "high", 2: "medium", 1: "low"}[c], "" if same else "the two judge runs differed on a second lecture"
    union = sorted({i for x in sets for i in x}, key=lambda i: emb_rank.get(i, 9))
    return union[:1], "low", "the two judge runs disagreed"


def resolve_conflicts(client, entries, texts, lectures, titles, cache):
    """A lecture claimed (as main lecture) by two or more guides: a content judge says which guides it really covers; the others are
    left unmatched (or keep their second lecture). This is what settles Class 27 vs Class 28 and the ANA407 Class 28 notes file."""
    by = defaultdict(list)
    for e in entries:
        if e["matched_lecture_id"] and not e["locked"]:
            by[e["matched_lecture_id"]].append(e)
    for lid, group in by.items():
        if len(group) < 2:
            continue
        key = hashlib.sha1((f"conflict{DIGEST_VERSION}|{lid}|" + "|".join(sorted(e["file"] for e in group))).encode()).hexdigest()
        if key not in cache:
            letters = dict(zip("ABCDEFG", group))
            user = f"LECTURE:\n{lecture_digest(lectures[lid])}\n\n" + "\n\n".join(f"GUIDE {n}:\n{chr(10).join(texts[e['file']])[:2200]}" for n, e in letters.items())
            for _ in (1, 2):
                try:
                    data, _u = llm.complete_json(client, CONFLICT_SYSTEM, [{"role": "user", "content": user}], 4000, CONFLICT_SCHEMA, JUDGE_MODEL)
                    cache[key] = {"covered": [n for n in data["covered"] if n in letters], "reason": data["reason"], "letters": {n: e["file"] for n, e in letters.items()}}
                    break
                except Exception:
                    pass
            else:
                continue
            CACHE_PATH.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
        res = cache[key]
        covered = {res["letters"][n] for n in res["covered"]}
        if not covered:                                    # inconclusive: drop nobody
            continue
        for e in group:
            if e["file"] in covered:
                continue
            e["note"] = f"another guide fits {titles[lid]} better: {res['reason']}"
            if e["also_lecture_id"]:                       # keep its second lecture as the main one
                e["matched_lecture_id"], e["matched_lecture"] = e["also_lecture_id"], e["also_lecture"]
                e["also_lecture_id"] = e["also_lecture"] = ""
                e["confidence"] = "low"
            else:
                e.update(matched_lecture_id="", matched_lecture="", confidence="unmatched", evidence=[])
                e["reason"] = f"The only candidate, {titles[lid]}, does not cover this guide ({res['reason']})"
    return entries


def build_content_map(decks, keep=None, model=None, client=None):
    """decks {file: slides} -> map entries (same shape as guides.build_map, plus evidence). Locked entries in `keep` are untouched."""
    keep = {e["file"]: e for e in (keep or []) if e.get("locked")}
    lectures, titles = lecture_sections()
    if model is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("BAAI/bge-small-en-v1.5")
    client = client or llm.make_client()
    def spread(slides, chars=GUIDE_CHARS):
        """The whole deck, start to end: each slide's first words (a long guide must not be judged from its first pages only)."""
        per = max(100, chars // max(1, len(slides)))
        return [t[:per] for t in slides]

    texts = {fn: [t for t in (G.slide_text(s) for s in sl if G.slide_role(s, G.clean_lines(s)) == "content") if t.strip()] for fn, sl in decks.items()}
    cands = candidates(model, texts, lectures)
    cache = _cache()
    numbers = defaultdict(int)
    for fn in decks:
        numbers[G.parse_name(fn)[0]] += 1
    entries = []
    for fn in sorted(decks, key=lambda f: (G.parse_name(f)[0] or 0, f)):
        if fn in keep:
            entries.append(keep[fn])
            continue
        number, title = G.parse_name(fn)
        cand_ids = [lid for lid, _ in cands[fn]]
        runs = [judge(client, fn, "\n".join(spread(texts[fn])), cand_ids, lectures, cache, variant=v) for v in (0, 1)]
        emb_rank = {lid: k for k, lid in enumerate(cand_ids)}
        ids, conf, note = merge_runs(runs, emb_rank)
        ok = [r for r in runs if "error" not in r]
        j = {"key_terms": [t for t in dict.fromkeys(t for r in ok for t in r.get("key_terms", []) if any(r2.get("key_terms") and t in r2["key_terms"] for r2 in ok))] or (ok[0].get("key_terms", []) if ok else []),
             "reason": "; ".join(dict.fromkeys(r.get("reason", "") for r in ok)) if ok else runs[0].get("error", "")}
        if not ok:
            j["error"] = runs[0].get("error", "")
        entries.append({
            "class_number": number, "title": title, "display_name": G.display_name(number, title),
            "class_label": f"Class {number}" if numbers[number] == 1 else f"Class {number} ({title})",
            "file": fn, "n_slides": len(decks[fn]),
            "matched_lecture_id": ids[0] if ids and conf != "unmatched" else "", "matched_lecture": titles[ids[0]] if ids and conf != "unmatched" else "",
            "also_lecture_id": ids[1] if len(ids) > 1 and conf != "unmatched" else "", "also_lecture": titles[ids[1]] if len(ids) > 1 and conf != "unmatched" else "",
            "method": "content only: embeddings (top 3) + gpt-oss-120b judge" + (" [judge failed twice]" if "error" in j else ""),
            "confidence": conf, "evidence": j.get("key_terms", []), "reason": j.get("reason", j.get("error", "")),
            "score": round(cands[fn][0][1], 2),
            "candidates": [{"lecture": titles[lid], "embedding_score": round(sc, 3)} for lid, sc in cands[fn]],
            "note": note, "locked": False})
    return resolve_conflicts(client, entries, texts, lectures, titles, cache)
