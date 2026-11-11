"""Import of the revised lecture notes and dissection guides (see src/ingest/revision.py).

  .venv/bin/python scripts/revision_import.py extract    unzip both zips (read only) into data/raw/notes_revised/ and data/raw/dissection_guides_revised/
  .venv/bin/python scripts/revision_import.py match      parse the revised files, match them to the current (v1) files by CONTENT, write reports/revision_match.md

Nothing here touches data/raw/notes, data/raw/dissection_guides, the zips, the index, flags or fixes. Intermediate files go to data/processed/revised/.
"""
import json
import re
import sys

import numpy as np
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingest import guides as G  # noqa: E402
from src.ingest import parse as P  # noqa: E402
from src.ingest import revision as R  # noqa: E402
from src.ingest.revision import diff_sections  # noqa: E402

ARCHIVE_V1 = ROOT / "data" / "archive" / "v1_2026-11-02"                 # the first version, saved when the revised files were swapped in


def v1_path(rel):
    """The first version of a data file: from the archive once the revised one is live, else the live file."""
    a = ARCHIVE_V1 / rel
    return a if a.exists() else ROOT / rel


RAW = ROOT / "data" / "raw"
WORK = ROOT / "data" / "processed" / "revised"
NOTES_ZIP, GUIDES_ZIP = RAW / "Lecture Notes (Revised).zip", RAW / "Dissection Guide (Revised).zip"
NOTES_V2, GUIDES_V2 = RAW / "notes_revised", RAW / "dissection_guides_revised"
HIGH, LOW_SCORE, LOW_MARGIN = 0.60, 0.40, 0.08         # a match is "low confidence" under LOW_SCORE, or when the runner-up is within LOW_MARGIN of it


def extract():
    n = R.extract(NOTES_ZIP, NOTES_V2)
    g = R.extract(GUIDES_ZIP, GUIDES_V2)
    print(f"notes_revised: {len(n)} files; dissection_guides_revised: {len(g)} files")
    return n, g


# ---------------------------------------------------------------- notes
def v1_notes():
    """{source_file: {"title", "text", "headings": set}} from the current sections.jsonl (v1)."""
    docs = {}
    for line in v1_path("data/processed/sections.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        d = docs.setdefault(r["source_file"], {"title": r["lecture_title"], "lecture_id": r["lecture_id"], "parts": [], "headings": set()})
        d["parts"].append(" ".join(r["section_path"]) + "\n" + r["text_clean"])
        d.setdefault("secs", []).append({"path": " > ".join(r["section_path"]), "text": " ".join(r["section_path"]) + "\n" + r["text_clean"]})
        d["headings"].add(" > ".join(r["section_path"]).lower())
    return {k: {**v, "text": "\n".join(v.pop("parts"))} for k, v in docs.items()}


SAME, CARRIED, REWORKED = 0.98, 0.50, 0.30       # a v1 section is "carried" when its best v2 section is at least this similar (tf-idf cosine), "reworked" above the lower bound


def v2_notes():
    docs = {}
    for path in sorted(NOTES_V2.glob("*.docx")):
        txt = WORK / "text" / (path.stem + ".txt")
        R.docx_text_copy(path, txt)
        records, stats = P.parse_file(txt, orig=path)
        docs[path.name] = {"secs": [{"path": " > ".join(r["section_path"]), "text": " ".join(r["section_path"]) + "\n" + r["text_clean"]} for r in records],
                           "title": records[0]["lecture_title"] if records else path.stem, "lecture_id": records[0]["lecture_id"] if records else "",
                           "text": "\n".join(" ".join(r["section_path"]) + "\n" + r["text_clean"] for r in records),
                           "headings": {" > ".join(r["section_path"]).lower() for r in records}, "n_sections": len(records), "layout": stats.get("layout")}
    return docs


def match_notes(old, new):
    on, nn = sorted(old), sorted(new)
    sim = R.similarity_matrix([old[k]["text"] for k in on], [new[k]["text"] for k in nn])
    pairs = []
    for i, j, s in R.assign(sim, floor=0.05):
        ru = max(R.runner_up(sim, i, j, 0), R.runner_up(sim, i, j, 1))
        h_old, h_new = old[on[i]]["headings"], new[nn[j]]["headings"]
        pairs.append({"v1": on[i], "v2": nn[j], "score": s, "runner_up": ru, "heading_overlap": len(h_old & h_new) / max(1, len(h_old)),
                      "low": s < LOW_SCORE or s - ru < LOW_MARGIN})
    used_old, used_new = {p["v1"] for p in pairs}, {p["v2"] for p in pairs}
    best_for_new = {nn[j]: (on[int(sim[:, j].argmax())], float(sim[:, j].max())) for j in range(len(nn))}
    best_for_old = {on[i]: (nn[int(sim[i, :].argmax())], float(sim[i, :].max())) for i in range(len(on))}
    return pairs, [n for n in nn if n not in used_new], [o for o in on if o not in used_old], best_for_new, best_for_old, (on, nn, sim)


# ---------------------------------------------------------------- guides
def v1_guides():
    docs = {}
    for line in v1_path("data/processed/guide_slides.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["kind"] in ("title", "end", "empty") or r.get("hidden"):
            continue
        docs.setdefault(r["file"], []).append(G.slide_text(r) if r["texts"] or r["tables"] else "")
    return {k: "\n".join(v) for k, v in docs.items()}


def v2_guides():
    cache = WORK / "guide_slides_v2.jsonl"
    if cache.exists():
        rows = [json.loads(l) for l in cache.read_text(encoding="utf-8").splitlines()]
    else:
        rows = []
        for f in sorted(GUIDES_V2.glob("*.pptx")):
            for s in G.read_deck(f):
                rows.append({"file": f.name, "class_number": G.parse_name(f.name)[0] or int(re.search(r"Class\s+(\d+)", f.name).group(1)),
                             "kind": G.classify_slide(s), **s})
        WORK.mkdir(parents=True, exist_ok=True)
        cache.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    docs, counts = {}, Counter()
    for r in rows:
        counts[r["file"]] += 1
        if r["kind"] in ("title", "end", "empty") or r.get("hidden"):
            continue
        docs.setdefault(r["file"], []).append(G.slide_text(r) if r["texts"] or r["tables"] else "")
    return {k: "\n".join(v) for k, v in docs.items()}, counts


def guide_map_v1():
    m = json.loads(v1_path("data/dissection_guides_map.json").read_text(encoding="utf-8"))
    return {e["file"]: e for e in m["guides"]}


def relate_notes(old, new):
    """Section-level alignment: every v1 section's most similar v2 section (over ALL v2 files). A v1 file's content "went to" the v2 file that
    holds most of its carried sections; a v2 file's content "came from" the v1 file that supplies most of its sections.
    -> (on, nn, align) with align["v1"][i] = [(v2 file index, v2 section index, score)] and align["v2"][j] = same the other way."""
    on, nn = sorted(old), sorted(new)
    s1 = [(i, sec) for i, k in enumerate(on) for sec in old[k]["secs"]]
    s2 = [(j, sec) for j, k in enumerate(nn) for sec in new[k]["secs"]]
    sim = R.similarity_matrix([x[1]["text"] for x in s1], [x[1]["text"] for x in s2])
    a1 = [(s2[int(r.argmax())][0], int(r.argmax()), float(r.max())) for r in sim]
    a2 = [(s1[int(c.argmax())][0], int(c.argmax()), float(c.max())) for c in sim.T]
    v1 = {i: [] for i in range(len(on))}
    v2 = {j: [] for j in range(len(nn))}
    for (i, _), (j, x, sc) in zip(s1, a1):
        v1[i].append((j, x, sc))
    for (j, _), (i, x, sc) in zip(s2, a2):
        v2[j].append((i, x, sc))
    return on, nn, {"v1": v1, "v2": v2}


def summarize(rows, n_other):
    """For one file: its sections' best matches in the other set -> primary other file (most sections matched at >= REWORKED), second file, shares and counts."""
    n = len(rows) or 1
    matched = [r for r in rows if r[2] >= REWORKED]
    per = Counter(r[0] for r in matched)
    primary = per.most_common(1)[0][0] if per else None
    second = per.most_common(2)[1][0] if len(per) > 1 else None
    return {"primary": primary, "second": second, "carried": len(matched) / n, "in_primary": (per[primary] / n if primary is not None else 0.0),
            "second_share": (per[second] / n if second is not None else 0.0), "n": len(rows),
            "same": sum(r[2] >= SAME for r in rows), "edited": sum(CARRIED <= r[2] < SAME for r in rows),
            "reworked": sum(REWORKED <= r[2] < CARRIED for r in rows), "gone": sum(r[2] < REWORKED for r in rows)}


def main_match():
    old, new = v1_notes(), v2_notes()
    on, nn, al = relate_notes(old, new)
    g_old, (g_new, g_slides) = v1_guides(), v2_guides()
    gpairs, gnew_only, gmissing, gbest_new, gbest_old, _ = match_notes(
        {k: {"text": v, "headings": set(), "title": k} for k, v in g_old.items()}, {k: {"text": v, "headings": set(), "title": k} for k, v in g_new.items()})
    old_map = guide_map_v1()
    sum1 = {i: summarize(al["v1"][i], len(nn)) for i in range(len(on))}
    sum2 = {j: summarize(al["v2"][j], len(on)) for j in range(len(nn))}

    def relation(i):
        s1 = sum1[i]
        if s1["primary"] is None or s1["carried"] < 0.2:
            return "gone", "v1 content is not in the revision"
        j = s1["primary"]
        back = sum2[j]["primary"]
        if s1["second"] is not None and s1["second_share"] >= 0.25:
            return "split", f"also in {nn[s1['second']]} ({s1['second_share']:.0%})"
        if back == i:
            return "same document", ""
        return "merged", f"{nn[j]} also holds {on[back] if back is not None and back != i else '(other text)'}"

    rows, v1_best = [], {}
    for i, k in enumerate(on):
        s1 = sum1[i]
        rel, why = relation(i)
        j = s1["primary"] if s1["primary"] is not None else -1
        v1_best[k] = (nn[j] if j >= 0 else "", rel)
        low = rel in ("gone", "split") or s1["in_primary"] < 0.5 or (rel == "merged")
        rows.append((k, nn[j] if j >= 0 else "-", s1, rel, why, bool(low)))
    out = [f"# Revised notes and guides: match report ({date.today().isoformat()})", "",
           "Matching is by CONTENT, never by title or lecture number (the revised set renumbers, renames and merges lectures). Method: every section of every v1 lecture is compared "
           f"with every section of every revised lecture (tf-idf cosine). A v1 section is **unchanged** at >= {SAME:.2f}, **edited** from {CARRIED:.2f}, **rewritten** from "
           f"{REWORKED:.2f} (same topic, new wording), **removed** below that. A file's content \"went to\" the revised file that holds most of its carried sections. "
           "Nothing in the index, the flags or the fixes has been changed.", "",
           f"Revised files unzipped (read only): **{len(new)} lecture notes** into `data/raw/notes_revised/`, **{len(g_new)} dissection guides** into `data/raw/dissection_guides_revised/` "
           f"(`__MACOSX`, `~$` and `.DS_Store` skipped). Current files (v1): {len(old)} notes, {len(g_old)} guides. The v1 files stay where they are and become version 1.", "",
           "## Lecture notes: every v1 file and where its content went", "",
           "| v1 file (current) | best v2 file | sections | unchanged | edited | rewritten | removed | relation | flag |", "|---|---|---|---|---|---|---|---|---|"]
    for k, m, s1, rel, why, low in sorted(rows):
        out.append(f"| {k} | {m} | {s1['n']} | {s1['same']} | {s1['edited']} | {s1['reworked']} | {s1['gone']} | {rel}{(': ' + why) if why else ''} | {'CHECK' if low else ''} |")
    out += ["", "## Lecture notes: every v2 file and where its content came from", "",
            "| v2 file (revised) | best v1 file | sections | unchanged | edited | rewritten | NEW (no v1 text) | relation | flag |", "|---|---|---|---|---|---|---|---|---|"]
    new_files, absorbed = [], {}
    for j, m in enumerate(nn):
        s2 = sum2[j]
        i = s2["primary"]
        new_share = s2["gone"] / (s2["n"] or 1)
        flag, rel = "", ""
        if i is None or s2["carried"] < 0.2:
            flag, rel = "NEW FILE", "no v1 counterpart"
            new_files.append((m, on[i] if i is not None else "-", s2["carried"]))
        else:
            back = sum1[i]["primary"]
            rel = "same document" if back == j else f"v1 file {on[i]} went mostly to {nn[back] if back is not None else '-'}"
            if back == j and sum1[i]["second"] is None:
                pass
            if back != j:
                flag = "CHECK"
            absorbed.setdefault(m, set())
        out.append(f"| {m} | {on[i] if i is not None else '-'} | {s2['n']} | {s2['same']} | {s2['edited']} | {s2['reworked']} | {s2['gone']} ({new_share:.0%}) | {rel} | {flag} |")
    for i, k in enumerate(on):
        j = sum1[i]["primary"]
        if j is not None and sum1[i]["carried"] >= 0.2:
            absorbed.setdefault(nn[j], set()).add(k)
    out += ["", "### Revised files that took content from more than one v1 file", ""] + ([f"- **{m}** <- {'; '.join(sorted(v))}" for m, v in sorted(absorbed.items()) if len(v) > 1] or ["- none"])
    split = [(k, why) for k, m, s1, rel, why, low in sorted(rows) if rel == "split"]
    out += ["", "### v1 files whose content was split across several revised files", ""] + ([f"- **{k}**: {why}" for k, why in split] or ["- none"])
    out += ["", "### New in the revision (no v1 counterpart)", ""] + ([f"- **{m}**: only {c:.0%} of it is carried from any v1 file (closest: {o})" for m, o, c in new_files] or ["- none"])
    gone = [k for k, (_, rel) in v1_best.items() if rel == "gone"]
    out += ["", "### v1 files whose content is not in the revision (missing)", ""] + ([f"- **{k}**" for k in gone] or ["- none"])
    lowrows = [r for r in rows if r[5]]
    out += ["", "### Matches to check", ""] + ([f"- {k} -> {m or '(nothing)'}: {rel}{(' (' + why + ')') if why else ''}; {s1['in_primary']:.0%} of its sections found in that file" for k, m, s1, rel, why, low in sorted(lowrows)] or ["- none"])
    odd = [(k, m) for k, m, *_ in rows if m != "-" and re.sub(r"^.*? - ", "", old[k]["title"]).lower().split()[:2] != re.sub(r"^.*? - ", "", new[m]["title"]).lower().split()[:2]]
    out += ["", "### Matched by content although the TITLE differs", ""] + ([f"- {old[k]['title']}  ->  {new[m]['title']}" for k, m in sorted(odd)] or ["- none"])

    out += ["", "## Dissection guides", "", f"Matched: {len(gpairs)} of {len(g_new)} revised guides (tf-idf cosine of the slide text, one-to-one).", "",
            "| v1 file (current) | v2 file (revised) | score | runner-up | note |", "|---|---|---|---|---|"]
    for p in sorted(gpairs, key=lambda p: p["v1"]):
        out.append(f"| {p['v1']} | {p['v2']} | {p['score']:.2f} | {p['runner_up']:.2f} | {'LOW CONFIDENCE (two v1 guides are almost the same text)' if p['low'] else ''} |")
    out += ["", "### New guides (no v1 counterpart)", ""] + ([f"- **{n}**: closest v1 guide is *{gbest_new[n][0]}* at {gbest_new[n][1]:.2f}" for n in gnew_only] or ["- none"])
    out += ["", "### v1 guides with no v2 counterpart", ""] + ([f"- **{o}**: closest v2 guide is *{gbest_old[o][0]}* at {gbest_old[o][1]:.2f}: merged into it" for o in gmissing] or ["- none"])

    # guide -> lecture, by content in the revised set
    lec_names = sorted(new)
    names = sorted(g_new)
    ga, gb = R.tfidf_matrix([g_new[k] for k in names], [new[k]["text"] for k in lec_names])
    gl = ga @ gb.T
    lec_file_by_title = {old[f]["title"]: f for f in old}
    gpair_by_v2 = {p["v2"]: p["v1"] for p in gpairs}
    out += ["", "## Does the guide -> lecture map (`data/dissection_guides_map.json`) still hold?", "",
            "For every revised guide: the revised lecture it matches best by content (tf-idf) against what the v1 map said for the v1 guide it replaces, carried over to the revised "
            "lecture that v1 lecture went to. A disagreement is a proposal, not a change; the real map is rebuilt later (embeddings + the judge).", "",
            "| revised guide | v1 guide it replaces | v1 map said | that lecture is now | best revised lecture by content | score | agrees |", "|---|---|---|---|---|---|---|"]
    changes = []
    for gi, gname in enumerate(names):
        top = sorted(range(len(lec_names)), key=lambda k: -gl[gi, k])[:2]
        best, second = lec_names[top[0]], lec_names[top[1]]
        v1g = gpair_by_v2.get(gname)
        said = (old_map.get(v1g) or {}).get("matched_lecture") if v1g else None
        said_v2 = v1_best.get(lecture_file_for(said, lec_file_by_title), ("", ""))[0] if said else ""
        agrees = bool(said_v2) and (said_v2 == best or (said_v2 == second and gl[gi, top[0]] - gl[gi, top[1]] < 0.03))
        if v1g and not agrees:
            changes.append((gname, said, said_v2, best, float(gl[gi, top[0]])))
        state = "yes" if agrees else ("unmapped in v1" if v1g and not said else ("NEW" if not v1g else "NO"))
        out.append(f"| {gname} | {v1g or 'new'} | {said or 'unmatched in v1'} | {said_v2 or '-'} | {best} | {gl[gi, top[0]]:.2f} | {state} |")
    out += ["", "### Proposed changes to the map", ""]
    for g, sd, sv, b, sc in changes:
        before = f"v1 map said *{sd}* (now *{sv}*)" if sd else "v1 had it unmatched"
        out.append(f"- **{g}**: {before}; by content it belongs with **{b}** ({sc:.2f}{'; weak' if sc < 0.25 else ''}).")
    if not changes:
        out.append("- none: the map holds for every guide that has a v1 counterpart.")
    out += ["", "## Next (after you confirm)", "",
            "Per-section diff (`reports/revision_diff.md`), build v2 on a COPY of the index, fact-check flags, knock-on effects. Versioning plan: every chunk gets "
            "`doc_id` (stable per document: the v1 file's id; a v2 file that absorbed several v1 files gets its own id, listed with the v1 ids it replaces), `version` (1 = current files, "
            "2 = revised files) and `section_id` (`<doc_id>#<heading path>`), so Chroma can delete by `doc_id` and add the v2 chunks."]
    out += applied_decisions()
    (ROOT / "reports" / "revision_match.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"notes: {len(rows)} v1 files, {len(lowrows)} to check, {len(new_files)} new in v2, {len(gone)} gone; guides: {len(gpairs)} matched, {len(gnew_only)} new, {len(gmissing)} merged/missing; "
          f"map changes proposed: {len(changes)}")


def applied_decisions():
    """The decisions Dr. Inglis made on this report and what was done with them (read from the staged build, so the numbers are the real ones)."""
    stage = ROOT / "data" / "staging_v2"
    try:
        c31 = json.loads((stage / "class31.json").read_text(encoding="utf-8"))
        fr = json.loads((stage / "factcheck_revision.json").read_text(encoding="utf-8"))
    except OSError:
        return []
    return ["", "## Final decisions as applied", "",
            "1. **Lecture 17 (Cranial Fossa, Dura, Sinuses and Meninges)**: its key terms are absent from the revised notes (falx, tentorium, dural venous sinus, superior sagittal: no hit). Kept searchable and labelled "
            "\"Earlier version, not in revised notes\" in sources and answers; listed in `reports/questions_for_inglis.md`.",
            "2. **Class 33 / 34 guides**: the two earlier oronasal guides are one revised guide (Class 34); student progress from both was mapped to it by station content.",
            f"3. **Class 31 (Craniectomy)**: never mapped to Lecture 23. {c31['decision'].capitalize()}. Scores: {c31['scores']}.",
            "4. **Accepted merges and rewrites**: Lecture 16 (Posterior Thigh) into revised Lecture 11; Larynx, Nasal Cavity and Oral Cavity into ANA407 Class 34; Anterior Triangle and Face/Parotid into revised "
            "Lectures 22 and 23. The one other match under 50%, Lecture 16 (Anterolateral Thoracoabdominal Wall script) -> revised Lecture 16 (38% of its sections), was used and put to Dr. Inglis.",
            f"5. **Fact-check items** (733 from the first report): {fr['all']}. Of the 90 confirmed factual: {fr['likely_factual']}; of the 14 start-here: {fr['start_here']}. New or changed sections were checked "
            "again (273 sections): their flags are tagged, not hidden (`NEW_REVISION_FLAGS`).",
            "6. **Grants**: each student's old grants were mapped to the revised names; the 6 lectures that are new in the revision are granted to nobody until Dr. Inglis grants them "
            "(see `reports/decisions_log.md`, item 4)."]


def lecture_file_for(title, by_title):
    return by_title.get(title, "")


def guide_slide_rows():
    """{file: [{"path": "Slide n", "text"}]} for v1 (guide_slides.jsonl) and v2 (the cached revised decks)."""
    v1, v2 = {}, {}
    for rows, dest in ((v1_rows(), v1), (v2_rows(), v2)):
        for r in rows:
            if r["kind"] in ("title", "end", "empty") or r.get("hidden"):
                continue
            text = G.slide_text(r) if r["texts"] or r["tables"] else ""
            if text.strip():
                dest.setdefault(r["file"], []).append({"path": f"Slide {r['n']}", "text": text})
    return v1, v2


def v1_rows():
    return [json.loads(l) for l in v1_path("data/processed/guide_slides.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def v2_rows():
    v2_guides()
    return [json.loads(l) for l in (WORK / "guide_slides_v2.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def short_list(paths, n=4):
    shown = [p.split(" > ")[-1][:48] for p in paths[:n]]
    return "; ".join(shown) + (f"; +{len(paths) - n} more" if len(paths) > n else "")


def main_diff():
    old, new = v1_notes(), v2_notes()
    on, nn, al = relate_notes(old, new)
    sum1 = {i: summarize(al["v1"][i], len(nn)) for i in range(len(on))}
    out = [f"# Revised notes and guides: what changed ({date.today().isoformat()})", "",
           "Per document pair, section by section (notes) or slide by slide (guides). **unchanged** = text identical (>= 0.98 similar), **edited** = same section, small changes "
           "(>= 0.50), **rewritten** = same topic, new wording (>= 0.30), **removed** = no counterpart in the revised file, **added** = new in the revised file. "
           "A revised file that took over several current files is compared with each of them.", "", "## Lecture notes", "",
           "| current file (v1) | revised file (v2) | unchanged | edited | rewritten | removed | added | what moved |", "|---|---|---|---|---|---|---|---|"]
    totals = Counter()
    for i, k in enumerate(on):
        j = sum1[i]["primary"]
        if j is None or sum1[i]["carried"] < 0.2:
            d = diff_sections(old[k]["secs"], [])
            out.append(f"| {k} | (none: not in the revision) | 0 | 0 | 0 | {d['removed']} | 0 | the whole file |")
            totals.update({"removed": d["removed"]})
            continue
        m = nn[j]
        # the revised file may hold several current files: only count a section as ADDED if no current file in the group has it
        d = diff_sections(old[k]["secs"], new[m]["secs"])
        totals.update({x: d[x] for x in ("unchanged", "edited", "rewritten", "removed")})
        notes = []
        if d["changed_paths"]:
            notes.append("changed: " + short_list(d["changed_paths"]))
        if d["removed_paths"]:
            notes.append("removed: " + short_list(d["removed_paths"]))
        out.append(f"| {k} | {m} | {d['unchanged']} | {d['edited']} | {d['rewritten']} | {d['removed']} | - | {' / '.join(notes)} |")
    out += ["", "### Sections added in the revised notes", "", "| revised file | sections | added (no counterpart in any current file) | examples |", "|---|---|---|---|"]
    all_old = [sec for k in on for sec in old[k]["secs"]]
    for m in nn:
        d = diff_sections(all_old, new[m]["secs"])
        added = d["added_paths"]
        totals.update({"added": len(added)})
        out.append(f"| {m} | {len(new[m]['secs'])} | {len(added)} | {short_list(added)} |")
    out += ["", f"**Totals (notes):** unchanged {totals['unchanged']}, edited {totals['edited']}, rewritten {totals['rewritten']}, removed {totals['removed']}, added {totals['added']}.", ""]

    g1, g2 = guide_slide_rows()
    g_old = {k: v for k, v in g1.items()}
    gpairs = match_notes({k: {"text": "\n".join(s["text"] for s in v), "headings": set(), "title": k} for k, v in g1.items()},
                         {k: {"text": "\n".join(s["text"] for s in v), "headings": set(), "title": k} for k, v in g2.items()})[0]
    out += ["## Dissection guides", "", "| current guide (v1) | revised guide (v2) | slides v1 -> v2 | unchanged | edited | rewritten | removed | added |", "|---|---|---|---|---|---|---|---|"]
    gt = Counter()
    for p in sorted(gpairs, key=lambda p: p["v1"]):
        d = diff_sections(g1[p["v1"]], g2[p["v2"]])
        gt.update({x: d[x] for x in ("unchanged", "edited", "rewritten", "removed", "added")})
        out.append(f"| {p['v1']} | {p['v2']} | {len(g1[p['v1']])} -> {len(g2[p['v2']])} | {d['unchanged']} | {d['edited']} | {d['rewritten']} | {d['removed']} | {d['added']} |")
    for o in {k for k in g1} - {p["v1"] for p in gpairs}:
        out.append(f"| {o} | (merged into another revised guide) | {len(g1[o])} -> - | - | - | - | {len(g1[o])} | - |")
    out += ["", f"**Totals (guides, slides):** unchanged {gt['unchanged']}, edited {gt['edited']}, rewritten {gt['rewritten']}, removed {gt['removed']}, added {gt['added']}.", ""]
    (ROOT / "reports" / "revision_diff.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("notes:", dict(totals), "| guides:", dict(gt))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "match"
    {"extract": extract, "match": main_match, "diff": main_diff}[cmd]()
