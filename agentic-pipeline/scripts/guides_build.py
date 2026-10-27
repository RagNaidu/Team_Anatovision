"""Dissection guides: extract -> read -> inventory -> class map -> chunks. Run from the repo root:

  .venv/bin/python -I scripts/guides_build.py            everything (the original zip and .pptx files are never modified)
  .venv/bin/python -I scripts/guides_build.py --no-extract

Writes: data/processed/guide_slides.jsonl, data/processed/guide_chunks.jsonl, data/dissection_guides_map.json,
        reports/dissection_guides_inventory.md.  The search index is rebuilt separately: .venv/bin/python -m src.retrieval.index
"""
import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingest import guides as G  # noqa: E402


def find_zip():
    zips = sorted(G.GUIDES_DIR.glob("*.zip"))
    named = [z for z in zips if "dissection" in z.name.lower()]
    return (named or zips or [None])[0], zips


def inventory(decks, entries, lectures, ltext, zip_path):
    L = []
    add = L.append
    kinds = {fn: [G.classify_slide(s) for s in sl] for fn, sl in decks.items()}
    total = Counter(k for ks in kinds.values() for k in ks)
    n_slides = sum(len(s) for s in decks.values())
    words = [s["n_words"] for sl in decks.values() for s in sl]
    pics = sum(s["n_pictures"] for sl in decks.values() for s in sl)
    notes = sum(bool(s["notes"]) for sl in decks.values() for s in sl)
    hidden = sum(s["hidden"] for sl in decks.values() for s in sl)
    diagrams = sum(s["n_diagrams"] for sl in decks.values() for s in sl)
    numbers = sorted(G.parse_name(f)[0] for f in decks)
    dup_numbers = [n for n, c in Counter(numbers).items() if c > 1]
    missing = [n for n in range(min(numbers), max(numbers) + 1) if n not in numbers]
    add(f"# Dissection guides: inventory\n\nGenerated {date.today().isoformat()} by `scripts/guides_build.py`. Read only: the zip and the .pptx files are untouched "
        f"(zip md5 {hashlib.md5(zip_path.read_bytes()).hexdigest()}).\n")
    add("## Summary\n")
    add(f"- Source: `{zip_path.relative_to(ROOT)}` ({zip_path.stat().st_size / 1e6:.0f} MB), extracted to `data/raw/dissection_guides/Dissection Guide (For Review)/`.")
    add(f"- **{len(decks)} files**, {n_slides} slides, class numbers {numbers[0]} to {numbers[-1]}.")
    add(f"- Words per slide (title, text boxes, tables): mean {statistics.mean(words):.0f}, median {statistics.median(words):.0f}, max {max(words)}; "
        f"{sum(words):,} words in total.")
    add(f"- Slide types: **{total['text']} text slides**, **{total['image-only']} image-only slides** (fewer than {G.SHORT_TEXT_WORDS} words and at least one picture), "
        f"{total['empty']} empty, {total['title']} title slides and {total['end']} \"End of Laboratory Session\" slides (the last two are not indexed).")
    add(f"- Embedded pictures: **{pics}** (every slide with a figure has its labels as separate text boxes with single letters A, B, C...; those letters are dropped, the figures themselves cannot be read as text).")
    add(f"- Speaker notes: **{'present on ' + str(notes) + ' slides' if notes else 'none in any file'}**. Hidden slides: {hidden}. SmartArt or charts (text not readable): {diagrams}.")
    add("- Slide titles: **no slide has a title placeholder**. Each slide is one lab step written as a short paragraph, with a footer (`PAS407 – Class N Dissection Guide – <title>`) and a page number, "
        "which are removed before indexing. The guides call the course PAS407; the lecture notes call it ANA407.")
    add(f"- Duplicates and odd files: class number(s) **{', '.join(map(str, dup_numbers)) or 'none'}** appear twice "
        f"({'; '.join(G.parse_name(f)[1] for f in decks if G.parse_name(f)[0] in dup_numbers)}); class numbers with no guide: {', '.join(map(str, missing)) or 'none'}. ")
    seen = defaultdict(list)
    for fn, sl in decks.items():
        for s in sl:
            t = G.slide_text(s).strip()
            if len(t) > 80:
                seen[hashlib.md5(t.encode()).hexdigest()].append((G.parse_name(fn)[0], s["n"]))
    dups = [v for v in seen.values() if len(v) > 1]
    add(f"  Slides whose text is identical to a slide in another place: {len(dups)}" + (" (" + "; ".join(", ".join(f"C{c} s{n}" for c, n in v) for v in dups[:6]) + ")" if dups else "") + ".")
    add("  Class 33 has two decks and Class 34 repeats \"Oronasal Cavities\" in its title: three decks on the same region. The inventory below treats them as three separate guides.\n")
    add("## Per file\n")
    add("| Class | Title | Slides | Words | Words/slide | Text | Image-only | Pictures | Notes |\n|---|---|---|---|---|---|---|---|---|")
    for fn in sorted(decks, key=lambda f: (G.parse_name(f)[0], f)):
        n, t = G.parse_name(fn)
        sl, ks = decks[fn], kinds[fn]
        w = sum(s["n_words"] for s in sl)
        add(f"| {n} | {t} | {len(sl)} | {w} | {w / len(sl):.0f} | {ks.count('text')} | {ks.count('image-only')} | {sum(s['n_pictures'] for s in sl)} | {sum(bool(s['notes']) for s in sl)} |")
    io = [(G.parse_name(fn)[0], s["n"]) for fn, sl in decks.items() for s, k in zip(sl, kinds[fn]) if k == "image-only"]
    add(f"\n### Image-only slides ({len(io)})\n")
    add(", ".join(f"C{c} s{n}" for c, n in sorted(io)) or "none")
    add("")
    return L, io


def map_section(entries, decks, lectures, ltext):
    L = []
    add = L.append
    add("\n## Class-to-lecture map (by content only)\n")
    add("File titles, lecture titles and class numbers are ignored (the client says lecture names may be wrong but the content is right). For each guide: "
        "embeddings of its slides against every lecture's sections give the 3 best candidate lectures; `openai/gpt-oss-120b` then judges, seeing only the guide's text and the "
        "candidates' headings and text under anonymous names, which candidate(s) cover what the guide dissects, with the key terms as evidence. \"None\" leaves the guide unmatched. "
        "Result: `data/dissection_guides_map.json` (an entry with `\"locked\": true` is kept as it is).\n")
    add("| Class | Guide (file title) | Matched lecture (by content) | Also | Confidence | Evidence (terms in both) |\n|---|---|---|---|---|---|")
    for e in entries:
        add(f"| {e['class_number']} | {e['title']} | {e['matched_lecture'] or '(none: unmatched)'} | {e['also_lecture'] or ''} | **{e['confidence']}** | {', '.join(e.get('evidence', [])[:6])} |")
    weak = [e for e in entries if e["confidence"] in ("low", "unmatched")]
    add(f"\n### Low-confidence and unmatched guides ({len(weak)})\n")
    for e in weak:
        add(f"- **{e['display_name']}** ({e['confidence']}): {e.get('reason', '')} Closest by embedding: " + "; ".join(f"{c['lecture']} ({c['embedding_score']})" for c in e["candidates"]) + ".")
    add("\nA guide matched to no lecture is **unmatched**: it can be granted on its own in the instructor Access screen as \"Dissection Guide, Class N\"; otherwise only instructors and students who may open every lecture see it. "
        "A guide matched to a lecture follows that lecture's grant (two lectures: either).\n")
    add("### Lectures and the guides that point at them\n")
    by = {}
    for e in entries:
        for lec in (e["matched_lecture"], e["also_lecture"]):
            if lec:
                by.setdefault(lec, []).append(e["display_name"])
    for lec in sorted(lectures.values()):
        add(f"- {lec}: " + ("; ".join(by.get(lec, [])) or "no guide"))
    add("\n### Checks you asked for\n")
    for n in (2, 4, 25, 26, 27, 28, 31, 33):
        for e in entries:
            if e["class_number"] == n:
                add(f"- **{e['display_name']}** → {e['matched_lecture'] or 'unmatched'}{' + ' + e['also_lecture'] if e['also_lecture'] else ''} ({e['confidence']}). {e.get('reason', '')}")
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-extract", action="store_true")
    ap.add_argument("--title-map", action="store_true", help="old title-based map (not the default)")
    args = ap.parse_args()
    zip_path, zips = find_zip()
    if zip_path is None:
        sys.exit("No dissection-guide zip found in data/raw/dissection_guides/")
    if len(zips) > 1:
        print("several zips found:", [z.name for z in zips], "-> using", zip_path.name)
    if not args.no_extract:
        G.extract_zip(zip_path, G.GUIDES_DIR)
    deck_dir = next(p for p in G.GUIDES_DIR.iterdir() if p.is_dir())
    decks = {f.name: G.read_deck(f) for f in sorted(deck_dir.glob("*.pptx"))}
    lectures, ltext = G.load_lectures()
    old = list(G.map_by_file().values())
    if args.title_map:
        entries = G.build_map(decks, lectures, ltext, keep=old)           # the older title + content method
    else:
        from src.ingest import guide_map
        entries = guide_map.build_content_map(decks, keep=old)
    rows = []
    for fn, sl in decks.items():
        for s in sl:
            rows.append({"file": fn, "class_number": G.parse_name(fn)[0], "kind": G.classify_slide(s), **s})
    G.write_jsonl(G.SLIDES_PATH, rows)
    chunks = G.guide_chunks(decks, entries)
    G.write_jsonl(G.CHUNKS_PATH, chunks)
    G.MAP_PATH.write_text(json.dumps({"generated": date.today().isoformat(), "zip": zip_path.name, "guides": entries}, indent=2, ensure_ascii=False), encoding="utf-8")
    inv, io = inventory(decks, entries, lectures, ltext, zip_path)
    report = "\n".join(inv + map_section(entries, decks, lectures, ltext)) + "\n"
    G.INVENTORY_PATH.write_text(report, encoding="utf-8")
    print(f"{len(decks)} guides, {sum(map(len, decks.values()))} slides, {len(chunks)} chunks, {len(io)} image-only slides")
    print("confidence:", Counter(e["confidence"] for e in entries))


if __name__ == "__main__":
    main()
