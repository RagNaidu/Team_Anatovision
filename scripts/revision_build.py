"""Build version 2 (the revised lecture notes and dissection guides) in a STAGING folder, data/staging_v2/, leaving every live file alone.

  .venv/bin/python scripts/revision_build.py notes      parse the revised notes (+ keep the one v1 lecture with no revised counterpart), write the staged sections.jsonl and revision_map.json
  .venv/bin/python scripts/revision_build.py guides     revised guides: slides, content-only map to the lectures (BullsAI judge), guide chunks
  .venv/bin/python scripts/revision_build.py index      the staged search index: unchanged chunks keep their embeddings, the rest are embedded; every chunk carries doc_id / version / section_id
  .venv/bin/python scripts/revision_build.py factcheck  re-home the fact-check items of the old notes in the revised notes (still there / moved / changed)
  .venv/bin/python scripts/revision_build.py all        notes, guides, factcheck, index
The swap into the live folders (with a backup) is scripts/revision_swap.py.
"""
import json
import re
import shutil
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import revision_import as RI  # noqa: E402

from src.ingest import guides as G  # noqa: E402
from src.ingest import parse as P  # noqa: E402
from src.ingest import revision as R  # noqa: E402
from src.ingest import stage as ST  # noqa: E402

STAGE = ROOT / "data" / "staging_v2"
KEEP_V1 = ("Lecture 17 - Cranial Fossa, Dura, Sinuses and Meninges",)         # no revised counterpart: kept searchable, labelled "Earlier version, not in revised notes"
ARCHIVE_NAMES = {}


def lecture_sort_key(title):
    m = re.match(r"Lecture\s+(\d+)\s*([a-z]?)", title, re.I)
    if m:
        return (0, int(m.group(1)), m.group(2).lower(), title)
    c = re.search(r"Class\s+(\d+)", title)
    return (1, int(c.group(1)) if c else 999, "", title)


def build_notes():
    """-> (records, revision_map). Writes stage/processed/sections.jsonl and stage/revision_map.json."""
    L = ST.layout(STAGE)
    L["sections"].parent.mkdir(parents=True, exist_ok=True)
    old, new = RI.v1_notes(), RI.v2_notes()
    on, nn, al = RI.relate_notes(old, new)
    sum1 = {i: RI.summarize(al["v1"][i], len(nn)) for i in range(len(on))}
    sum2 = {j: RI.summarize(al["v2"][j], len(on)) for j in range(len(nn))}
    v1_rows = {}                                                         # v1 file -> its records (to keep L17 and to resolve titles)
    for line in RI.v1_path("data/processed/sections.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        v1_rows.setdefault(r["source_file"], []).append(r)
    records = []
    for name in nn:
        path = RI.NOTES_V2 / name
        stem = R.v2_stem(name)
        txt = RI.WORK / "text" / f"{stem}.txt"
        R.docx_text_copy(path, txt)
        recs, _stats = P.parse_file(txt, orig=path)
        for r in recs:
            records.append(R.with_version(r, 2))
    kept = []
    for k, rows in v1_rows.items():
        if rows[0]["lecture_title"] in KEEP_V1:
            kept += [R.with_version(r, 1, superseded=True) for r in rows]
    records += kept
    records.sort(key=lambda r: (r["lecture_title"], r["order"]))                  # file order = alphabetical by title, like the first set (ANA407 classes first)
    L["sections"].write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
    shutil.copy(ROOT / "data" / "processed" / "openstax_sections.jsonl", L["openstax"])
    # the map of what became what (grants, flags, progress and citations use it)
    titles2 = {}
    for r in records:
        titles2[r["source_file"]] = (r["lecture_title"], r["lecture_id"], r["version"])
    rows = []
    for i, k in enumerate(on):
        s1 = sum1[i]
        j = s1["primary"]
        rel = "gone" if j is None or s1["carried"] < 0.2 else ("split" if s1["second"] is not None and s1["second_share"] >= 0.25 else
                                                                  "same document" if sum2[j]["primary"] == i else "merged")
        t1, id1 = old[k]["title"], old[k]["lecture_id"]
        v2 = titles2.get(nn[j]) if j is not None and rel != "gone" else None
        if rel == "gone":
            v2 = next((titles2[x] for x in titles2 if titles2[x][2] == 1 and titles2[x][0] == t1), None)      # kept as it was (version 1)
        rows.append({"v1_file": k, "v1_title": t1, "v1_lecture_id": id1, "v2_file": nn[j] if j is not None and rel != "gone" else (k if rel == "gone" else ""),
                     "v2_title": v2[0] if v2 else "", "v2_lecture_id": v2[1] if v2 else "", "relation": rel, "kept_as_v1": rel == "gone",
                     "found_in_primary": round(s1["in_primary"], 2)})
    rmap = {"generated": date.today().isoformat(), "notes": rows, "new_lectures": [r["lecture_title"] for r in records if r["version"] == 2
            and r["lecture_id"] not in {x["v2_lecture_id"] for x in rows}]}
    rmap["new_lectures"] = sorted(set(rmap["new_lectures"]))
    (STAGE / "revision_map.json").write_text(json.dumps(rmap, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"sections: {len(records)} ({sum(r['version'] == 2 for r in records)} revised, {len(kept)} kept from v1); lectures: {len({r['lecture_id'] for r in records})}")
    return records, rmap


def class31_decision(decks):
    """Class 31 (Craniectomy and Brain) is NOT mapped to Lecture 23. It is scored against the earlier-version Lecture 17 and the revised Lecture 24 (and every other
    lecture, as a control) and mapped only if clearly strong: tf-idf >= 0.30 and at least 0.10 above the next lecture. -> (lecture title or "", report dict)"""
    import numpy as np
    new = RI.v2_notes()
    old = RI.v1_notes()
    texts = {R.v2_stem(k): d["text"] for k, d in new.items()}
    for k, d in old.items():
        if d["title"] in KEEP_V1:
            texts[d["title"] + " (earlier version)"] = d["text"]
    names = list(texts)
    fn = next(f for f in decks if "Class 31" in f)
    guide = "\n".join(G.slide_text(x) for x in decks[fn] if G.slide_text(x).strip())
    a, b = R.tfidf_matrix([guide], [texts[n] for n in names])
    sim = (a @ b.T)[0]
    order = np.argsort(-sim)
    top, second = float(sim[order[0]]), float(sim[order[1]])
    rep = {"file": fn, "scores": {names[j]: round(float(sim[j]), 2) for j in order[:5]},
           "lecture_24": round(float(sim[names.index(next(n for n in names if n.startswith("Lecture 24")))]), 2),
           "lecture_17_earlier": round(float(sim[names.index(next(n for n in names if n.endswith("(earlier version)")))]), 2)}
    best = names[order[0]]
    strong = top >= 0.30 and top - second >= 0.10 and not best.startswith("Lecture 23")
    rep["decision"] = (f"mapped to {best} (score {top:.2f}, next {second:.2f})" if strong else f"left unmapped (best {best} at {top:.2f}, next {second:.2f}: not clearly strong)")
    return (best.replace(" (earlier version)", "") if strong else ""), rep


def build_guides():
    from src.ingest import guide_map
    L = ST.layout(STAGE)
    rows = RI.v2_rows()
    decks = {}
    for r in rows:
        decks.setdefault(r["file"], []).append(r)
    lecture, rep31 = class31_decision(decks)
    with ST.use(STAGE):
        entries = guide_map.build_content_map(decks, keep=[])
        lectures, titles = guide_map.lecture_sections()
        by_title = {t: i for i, t in titles.items()}
        for e in entries:
            if "Class 31" in e["file"]:
                e.update(matched_lecture=lecture, matched_lecture_id=by_title.get(lecture, ""), also_lecture="", also_lecture_id="",
                         confidence="high" if lecture else "unmatched", locked=True,
                         note="Class 31 is never mapped to Lecture 23 (Dr. Inglis). " + rep31["decision"],
                         evidence=[f"slide text vs the earlier-version Lecture 17: tf-idf {rep31['lecture_17_earlier']}", f"vs revised Lecture 24: {rep31['lecture_24']}"],
                         reason=rep31["decision"])
            if e["matched_lecture"].startswith("Lecture 23") and "Class 31" in e["file"]:
                raise SystemExit("Class 31 must not be mapped to Lecture 23")
        chunks = G.guide_chunks(decks, entries)
    L["slides"].write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    G.write_jsonl(L["gchunks"], chunks)
    L["map"].write_text(json.dumps({"generated": date.today().isoformat(), "zip": "Dissection Guide (Revised).zip", "guides": entries}, indent=2, ensure_ascii=False), encoding="utf-8")
    (STAGE / "class31.json").write_text(json.dumps(rep31, indent=2), encoding="utf-8")
    print(f"guides: {len(decks)}, slides {len(rows)}, chunks {len(chunks)}; confidence {dict(Counter(e['confidence'] for e in entries))}; Class 31: {rep31['decision']}")
    return entries


def guide_pairs():
    """Which revised guide each current guide became (by slide text), with labels, for grants and student progress. Appended to stage/revision_map.json."""
    import numpy as np
    g1, g2 = RI.v1_guides(), RI.v2_guides()[0]
    names1, names2 = sorted(g1), sorted(g2)
    sim = R.similarity_matrix([g1[k] for k in names1], [g2[k] for k in names2])
    v1_map = G.map_by_file(RI.v1_path("data/dissection_guides_map.json"))
    v2_map = {e["file"]: e for e in json.loads(ST.layout(STAGE)["map"].read_text(encoding="utf-8"))["guides"]}
    rows = []
    for i, k in enumerate(names1):
        j = int(sim[i].argmax())
        e1, e2 = v1_map.get(k), v2_map[names2[j]]
        rows.append({"v1_file": k, "v1_label": G.guide_label(e1) if e1 else "", "v1_display": e1["display_name"] if e1 else "", "v2_file": names2[j],
                     "v2_label": G.guide_label(e2), "v2_display": e2["display_name"], "similarity": round(float(sim[i, j]), 2),
                     "merged": sum(int(sim[x].argmax()) == j for x in range(len(names1))) > 1})
    path = STAGE / "revision_map.json"
    rmap = json.loads(path.read_text(encoding="utf-8"))
    rmap["guides"] = rows
    path.write_text(json.dumps(rmap, indent=2, ensure_ascii=False), encoding="utf-8")
    print("guide pairs:", len(rows), "| merged:", [(r["v1_display"], "->", r["v2_display"]) for r in rows if r["merged"]])


def carry_over_map(min_similarity=0.95):
    """A revised guide whose slide text is almost the same as a current guide keeps that guide's lecture when the content judge left it unmatched or low (the judge sees
    two guides competing for one lecture, e.g. Class 2 and 3 for Lecture 2). The earlier lecture is translated to its revised title. Regenerates the guide chunks."""
    L = ST.layout(STAGE)
    rmap = json.loads((STAGE / "revision_map.json").read_text(encoding="utf-8"))
    pairs = {p["v2_file"]: p for p in rmap["guides"] if not p["merged"]}
    v1_map = G.map_by_file(RI.v1_path("data/dissection_guides_map.json"))
    title_to_v2 = {n["v1_title"]: n["v2_title"] for n in rmap["notes"] if n["v2_title"]}
    mp = json.loads(L["map"].read_text(encoding="utf-8"))
    titles = {}
    for line in L["sections"].read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        titles[r["lecture_title"]] = r["lecture_id"]
    changed = []
    for e in mp["guides"]:
        p = pairs.get(e["file"])
        old = v1_map.get(p["v1_file"]) if p else None
        if p and old and old["matched_lecture"] and p["similarity"] >= min_similarity and e["confidence"] in ("unmatched", "low") and not e.get("locked"):
            new_title = title_to_v2.get(old["matched_lecture"], old["matched_lecture"])
            if new_title in titles:
                e.update(matched_lecture=new_title, matched_lecture_id=titles[new_title], confidence="medium",
                         note=f"kept from the earlier map: the guide text is {p['similarity']:.2f} the same and the earlier map said {old['matched_lecture']}",
                         evidence=[f"slide text {p['similarity']:.2f} the same as the earlier guide, which was matched to {old['matched_lecture']}"])
                changed.append((e["display_name"], new_title))
    L["map"].write_text(json.dumps(mp, indent=2, ensure_ascii=False), encoding="utf-8")
    rows = RI.v2_rows()
    decks = {}
    for r in rows:
        decks.setdefault(r["file"], []).append(r)
    with ST.use(STAGE):
        chunks = G.guide_chunks(decks, mp["guides"])
    for c in chunks:
        c["doc_id"], c["version"], c["section_id"] = c["id"].rsplit("-s", 1)[0], 2, c["id"]
    G.write_jsonl(L["gchunks"], chunks)
    print("map entries carried over:", changed, "| chunks:", len(chunks))


def build_index():
    """The staged index: the live index is only READ. Chunks whose text did not change keep their stored embedding; Chroma is rebuilt in the stage."""
    import chromadb
    L = ST.layout(STAGE)
    # version metadata on the guide chunks
    chunks_g = [json.loads(l) for l in L["gchunks"].read_text(encoding="utf-8").splitlines() if l.strip()]
    for c in chunks_g:
        c["doc_id"] = c["id"].rsplit("-s", 1)[0]
        c["version"] = 2
        c["section_id"] = c["id"]
    G.write_jsonl(L["gchunks"], chunks_g)
    live_chunks = [json.loads(l) for l in (ROOT / "data" / "index" / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    live_col = chromadb.PersistentClient(path=str(ROOT / "data" / "index" / "chroma")).get_collection("anatovision")
    got = live_col.get(ids=[c["id"] for c in live_chunks], include=["embeddings"])
    vec_of = dict(zip(got["ids"], got["embeddings"]))                      # get() does not keep the requested order: pair by id
    stored = {f"{c['breadcrumb']}\n{c['text']}": list(map(float, vec_of[c["id"]])) for c in live_chunks if c["id"] in vec_of}
    with ST.use(STAGE):
        from src.retrieval import index
        chunks = index.build_chunks()
        todo = [c for c in chunks if c["embed_text"] not in stored]
        vectors = {}
        if todo:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(index.EMBED_MODEL)
            enc = model.encode([c["embed_text"] for c in todo], batch_size=32, normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True)
            vectors = {c["id"]: [float(x) for x in v] for c, v in zip(todo, enc)}
        shutil.rmtree(L["index"], ignore_errors=True)
        L["index"].mkdir(parents=True)
        with index.CHUNKS_PATH.open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps({k: v for k, v in c.items() if k != "embed_text"}, ensure_ascii=False) + "\n")
        col = chromadb.PersistentClient(path=str(index.CHROMA_DIR)).create_collection(index.COLLECTION, configuration={"hnsw": {"space": "cosine"}})
        for i in range(0, len(chunks), 500):
            batch = chunks[i:i + 500]
            col.add(ids=[c["id"] for c in batch], embeddings=[vectors.get(c["id"]) or stored[c["embed_text"]] for c in batch],
                    documents=[c["text"] for c in batch], metadatas=[index.metadata_of(c) for c in batch])
        kinds = Counter(c["source_type"] for c in chunks)
        print(f"index: {len(chunks)} chunks {dict(kinds)}; embeddings reused {len(chunks) - len(todo)}, embedded {len(todo)}; chroma {col.count()}")


def factcheck_remap():
    """Re-home every fact-check item of the old notes: still in the revised text (same place / moved) or changed (quote gone). Writes the staged report."""
    L = ST.layout(STAGE)
    report = json.loads((ROOT / "reports" / "factcheck_all.json").read_text(encoding="utf-8"))
    rmap = json.loads((STAGE / "revision_map.json").read_text(encoding="utf-8"))
    recs = [json.loads(l) for l in L["sections"].read_text(encoding="utf-8").splitlines() if l.strip()]
    by_doc = {}
    for r in recs:
        by_doc.setdefault(r["lecture_title"], []).append(r)
    docs = [(t, [(r["section_path"], r["text"] + "\n" + r["text_clean"]) for r in rs]) for t, rs in by_doc.items()]
    target = {}
    for n in rmap["notes"]:
        target[n["v1_title"]] = n["v2_title"] or n["v1_title"]
    counts = Counter()
    for issue in report["issues"]:
        old = {"lecture": issue["lecture"], "breadcrumb": issue["breadcrumb"]}
        first = target.get(issue["lecture"])
        ordered = sorted(docs, key=lambda d: 0 if d[0] == first else 1)
        hit = R.find_quote(issue["claim_quote"], ordered)
        if hit:
            title, idx = hit
            rec = by_doc[title][idx]
            moved = (title != issue["lecture"]) or (rec["breadcrumb"] != issue["breadcrumb"])
            if moved:
                issue.update(lecture=rec["lecture_title"], lecture_id=rec["lecture_id"], section_path=rec["section_path"], breadcrumb=rec["breadcrumb"],
                             source_file=rec["source_file"], order=rec["order"])
            issue["revision"] = {"status": "moved" if moved else "unchanged", "old_lecture": old["lecture"], "old_breadcrumb": old["breadcrumb"]}
        else:
            texts = [r["text_clean"] for r in by_doc.get(first, [])] if first else []
            new_text = R.best_sentence(issue["claim_quote"], texts)
            where = next((r["breadcrumb"] for r in by_doc.get(first, []) if new_text and new_text in r["text_clean"]), "")
            issue["revision"] = {"status": "changed", "old_lecture": old["lecture"], "old_breadcrumb": old["breadcrumb"], "new_lecture": first or "",
                                 "new_text": new_text, "new_breadcrumb": where}
        counts[(issue["tier"], issue["revision"]["status"])] += 1
    report["revision"] = {"generated": date.today().isoformat(), "note": "claim locations re-homed in the revised notes; status changed = the quoted line is no longer there"}
    L["factcheck"].parent.mkdir(parents=True, exist_ok=True)
    L["factcheck"].write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    # the 90 confirmed-factual and the 14 start-here items of the OLD report
    from src import review
    old_items = review.queue(report={"issues": json.loads((ROOT / "reports" / "factcheck_all.json").read_text(encoding="utf-8"))["issues"]}, state={})
    start = {i["key"] for i in review.start_here(old_items)}
    new_status = {review.flag_key({**i, "lecture": i["revision"]["old_lecture"], "breadcrumb": i["revision"]["old_breadcrumb"]}): i["revision"]["status"] for i in report["issues"]}
    out = {"likely_factual": Counter(v for (t, v) in [(k[0], k[1]) for k in counts.elements()] if False)}
    lf = Counter(i["revision"]["status"] for i in report["issues"] if i["tier"] == "likely_factual")
    sh = Counter(new_status[k] for k in start if k in new_status)
    allc = Counter(i["revision"]["status"] for i in report["issues"])
    (STAGE / "factcheck_revision.json").write_text(json.dumps({"likely_factual": lf, "start_here": sh, "all": allc, "by_tier": {f"{t}|{s_}": n for (t, s_), n in counts.items()}}, indent=2), encoding="utf-8")
    print(f"fact-check items: {dict(allc)} | confirmed factual (90): {dict(lf)} | start-here ({len(start)}): {dict(sh)}")


def factcheck_changed_sections(workers=6):
    """The fact-checker (the same prompts and second check as src/audit/factcheck.py, BullsAI) on the sections that are NEW or CHANGED in the revised notes only.
    Sections whose text is identical to a v1 section keep their old result (re-homed by factcheck_remap). Results are merged into the staged report."""
    import time
    from concurrent.futures import ThreadPoolExecutor
    from src import llm
    from src.audit import factcheck as FC
    L = ST.layout(STAGE)
    recs = [json.loads(l) for l in L["sections"].read_text(encoding="utf-8").splitlines() if l.strip()]
    v1_text = {R.squash(json.loads(l)["text_clean"]) for l in RI.v1_path("data/processed/sections.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    todo = [r for r in recs if r["version"] == 2 and R.squash(r["text_clean"]) not in v1_text and len(r["text_clean"]) > 40]
    print(f"fact-checking {len(todo)} new or changed sections of {sum(r['version'] == 2 for r in recs)} revised ones", flush=True)
    FC.CACHE_DIR = STAGE / "processed" / "audit_cache"
    FC.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    FC.REPORT_DIR = STAGE / "reports"
    model, effort = llm.default_model(), "medium"
    client = llm.make_client()
    retriever = FC.Retriever(FC.load_jsonl(ROOT / "data" / "processed" / "openstax_sections.jsonl"))
    ledger = {"fresh": {"input_tokens": 0, "output_tokens": 0, "calls": 0}, "cached": {"input_tokens": 0, "output_tokens": 0, "calls": 0}}
    results, dropped, t0 = [], [], time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        res = list(pool.map(lambda sec: FC.check_section(client, retriever, model, effort, sec, False), todo))
        jobs = [(i, r["note"]) for r in res for i in r["issues"] if i["type"] == "factual"]
        ver = list(pool.map(lambda j: FC.verify_issue(client, model, effort, j[0], j[1], False), jobs))
    for r in res:
        keep = []
        for i in r["issues"]:
            (dropped if i["type"] == "factual" and i["verification"]["verdict"] == "wrong" else keep).append(i)
        r["issues"] = keep
    results += res
    errors = sum(bool(r["error"]) for r in res)
    FC.write_reports("revised-sections", model, effort, results, ledger, dropped, len({r["lecture_title"] for r in recs}), len(todo), False)
    new = json.loads((STAGE / "reports" / "factcheck_revised-sections.json").read_text(encoding="utf-8"))
    report = json.loads(L["factcheck"].read_text(encoding="utf-8"))
    for i in new["issues"]:
        i["revision"] = {"status": "new_in_revision"}
    report["issues"] += new["issues"]
    report["revised_sections_checked"] = {"n": len(todo), "errors": errors, "model": model, "date": date.today().isoformat(), "kept": len(new["issues"])}
    L["factcheck"].write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"checked {len(todo)} sections in {time.time() - t0:.0f}s: {len(new['issues'])} items kept, {len(dropped)} dropped as wrong, {errors} errors; "
          f"by tier {dict(Counter(i['tier'] for i in new['issues']))}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("notes", "all"):
        build_notes()
    if cmd in ("guides", "all"):
        build_guides()
    if cmd in ("factcheck", "all"):
        factcheck_remap()
    if cmd == "carry-over":
        carry_over_map()
    if cmd == "guide-pairs":
        guide_pairs()
    if cmd == "factcheck-new":
        factcheck_changed_sections()
    if cmd in ("index", "all"):
        build_index()
