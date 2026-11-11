"""Parse OpenStax Anatomy and Physiology 2e (CNXML) into section records.

Reads  data/raw/open_text/collections/*.collection.xml   (book structure: unit > chapter > module)
       data/raw/open_text/modules/m*/index.cnxml          (module text)
Writes data/processed/openstax_sections.jsonl

One record per section that has text of its own: a module (e.g. 14.1 Sensory Perception),
or a <section> inside one (e.g. Audition (Hearing)). section_path is the chain
[chapter, module, section, ...]. Review/exercise sections, interactive-link notes and
the preface are left out; module glossaries become a "Key Terms" record.

License: CC BY-NC-SA 4.0 (see data/raw/open_text/ATTRIBUTION.md). Standard library only.
Run:  python -I src/ingest/openstax.py   (from the repo root)
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "open_text"
OUT_PATH = ROOT / "data" / "processed" / "openstax_sections.jsonl"
COLLECTION = RAW_DIR / "collections" / "anatomy-and-physiology-2e.collection.xml"

BASE_URL = "https://openstax.org/books/anatomy-and-physiology-2e/pages/"
SOURCE_TYPE = "open_text"
PRIORITY = 3

C = "{http://cnx.rice.edu/cnxml}"
COL = "{http://cnx.rice.edu/collxml}"
MD = "{http://cnx.rice.edu/mdml}"
MATH = "{http://www.w3.org/1998/Math/MathML}"

SKIP_SECTION_CLASSES = {"multiple-choice", "free-response", "interactive-exercise",
                        "references", "contrib-auth", "sr-contrib-auth"}
SUPER = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")
SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


ID_KINDS = {}  # element id -> tag, for the module being parsed (to label empty cross-references)


def local(e):
    return e.tag.split("}")[-1]


def squash(text):
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip()


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# ----------------------------------------------------------------------------
# CNXML -> plain text
# ----------------------------------------------------------------------------

def inline(e):
    """Text of an element with inline markup flattened; nested lists/figures/tables skipped."""
    out = [e.text or ""]
    for ch in e:
        name = local(ch)
        if name in ("list", "figure", "table", "note", "media", "exercise"):
            pass
        elif name == "newline":
            out.append(" ")
        elif name in ("sup", "sub"):
            t = squash(inline(ch))
            if name == "sup" and re.fullmatch(r"[0-9+\-]+", t):
                out.append(t.translate(SUPER))
            elif name == "sub" and re.fullmatch(r"[0-9]+", t):
                out.append(t.translate(SUB))
            elif t:
                out.append(("^(%s)" if name == "sup" else "_(%s)") % t)
        elif name == "link" and not squash("".join(ch.itertext())):
            # cross-reference whose number ("Figure 14.12") the OpenStax renderer fills in
            kind = ID_KINDS.get(ch.get("target-id"), "reference")
            out.append(f"[{kind if kind in ('figure', 'table') else 'reference'}]")
        elif ch.tag.startswith(MATH):
            out.append(re.sub(r"\s+", "", "".join(ch.itertext())))
        else:
            out.append(inline(ch))
        out.append(ch.tail or "")
    return "".join(out)


def render_list(lst, depth=0):
    lines, n = [], 0
    enumerated = lst.get("list-type") == "enumerated"
    for item in lst.findall(C + "item"):
        n += 1
        marker = f"{n}." if enumerated else "-"
        text = squash(inline(item))
        if text:
            lines.append("  " * depth + f"{marker} {text}")
        for sub in item.findall(C + "list"):
            lines += render_list(sub, depth + 1)
    return lines


def render_table(tbl):
    lines = []
    cap = tbl.find(C + "title")
    if cap is not None and squash("".join(cap.itertext())):
        lines.append("Table: " + squash("".join(cap.itertext())))
    for row in tbl.iter(C + "row"):
        cells = [squash("".join(c.itertext())) for c in row.findall(C + "entry")]
        if any(cells):
            lines.append(" | ".join(cells))
    return lines


def blocks(e):
    """Text blocks directly inside e (not inside child <section>s)."""
    out = []
    for ch in e:
        name = local(ch)
        if name == "para":
            t = squash(inline(ch))
            if t:
                out.append(t)
            for sub in ch.findall(C + "list"):
                out += render_list(sub)
        elif name == "list":
            out += render_list(ch)
        elif name == "table":
            out += render_table(ch)
        elif name == "figure":
            cap = ch.find(C + "caption")
            t = squash(inline(cap)) if cap is not None else ""
            if t:
                out.append("Figure: " + t)
        elif name == "equation":
            t = squash("".join(ch.itertext()))
            if t:
                out.append(t)
        elif name == "note":
            if "interactive" in (ch.get("class") or ""):
                continue  # "Link to Learning": pointers to external sites, no content
            title = ch.find(C + "title")
            head = squash("".join(title.itertext())) if title is not None else ""
            body = blocks(ch)
            if body:
                out.append(f"[{head}]" if head else "[Note]")
                out += body
    return out


def glossary_lines(root):
    lines = []
    for g in root.iter(C + "glossary"):
        for d in g.findall(C + "definition"):
            term, meaning = d.find(C + "term"), d.find(C + "meaning")
            if term is not None and meaning is not None:
                lines.append(f"{squash(inline(term))}: {squash(inline(meaning))}")
    return lines


# ----------------------------------------------------------------------------
# book structure
# ----------------------------------------------------------------------------

def book_modules():
    """Yield (unit, chapter_number, chapter_title, index_in_chapter, module_id) in book order."""
    root = ET.parse(COLLECTION).getroot().find(COL + "content")
    chapter_no = 0
    for unit in root.findall(COL + "subcollection"):
        unit_title = unit.find(MD + "title").text.strip()
        for chap in unit.find(COL + "content").findall(COL + "subcollection"):
            chapter_no += 1
            title = chap.find(MD + "title").text.strip()
            for i, mod in enumerate(chap.find(COL + "content").findall(COL + "module")):
                yield unit_title, chapter_no, title, i, mod.get("document")


def module_page_slug(chapter_no, index, title, doc_class):
    if doc_class == "introduction":
        return f"{chapter_no}-introduction"
    return f"{chapter_no}-{index}-{slug(title)}"


def parse_module(mid, unit, chapter_no, chapter, index, stats):
    root = ET.parse(RAW_DIR / "modules" / mid / "index.cnxml").getroot()
    ID_KINDS.clear()
    ID_KINDS.update({e.get("id"): local(e) for e in root.iter() if e.get("id")})
    title = squash(inline(root.find(C + "title")))
    intro = root.get("class") == "introduction"
    number = None if intro else f"{chapter_no}.{index}"
    url = BASE_URL + module_page_slug(chapter_no, index, title, root.get("class"))
    base = {"chapter": chapter, "chapter_number": chapter_no, "unit": unit,
            "section_number": number, "module_id": mid, "source_type": SOURCE_TYPE,
            "priority": PRIORITY, "source_url": url}
    recs = []

    def add(path, text_blocks):
        text = "\n\n".join(text_blocks).strip()
        if text:
            recs.append({**base, "section_title": path[-1], "section_path": path, "text": text})

    def walk(e, path):
        add(path, blocks(e))
        for sec in e.findall(C + "section"):
            if sec.get("class") in SKIP_SECTION_CLASSES:
                stats["skipped_sections"] += 1
                continue
            t = sec.find(C + "title")
            name = squash("".join(t.itertext())) if t is not None else None
            if name is None:
                add(path, blocks(sec))  # untitled section: text belongs to its parent
                continue
            walk(sec, path + [name])

    walk(root.find(C + "content"), [chapter, title])
    gloss = glossary_lines(root)
    if gloss:
        add([chapter, title, "Key Terms"], gloss)
    return recs


def main():
    stats = {"skipped_sections": 0}
    records, chapters, modules = [], set(), 0
    for unit, chapter_no, chapter, index, mid in book_modules():
        modules += 1
        chapters.add(chapter_no)
        records += parse_module(mid, unit, chapter_no, chapter, index, stats)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    report(records, len(chapters), modules, stats)


def words(text):
    return len(re.findall(r"\w+", text))


def report(records, n_chapters, n_modules, stats):
    total = sum(words(r["text"]) for r in records)
    sizes = sorted(len(r["text"]) for r in records)
    print(f"Wrote {len(records)} sections -> {OUT_PATH.relative_to(ROOT)}")
    print(f"Chapters: {n_chapters}   Modules (numbered sections + intros): {n_modules}")
    print(f"Sections (records): {len(records)}   Total words: {total:,}")
    print(f"Section size in chars: min {sizes[0]}, median {sizes[len(sizes) // 2]}, max {sizes[-1]}")
    print(f"Skipped question/review/reference sections: {stats['skipped_sections']}")
    hearing = [r for r in records if r["chapter_number"] == 14]
    picks = [next(r for r in hearing if r["section_title"] == name)
             for name in ("Audition (Hearing)", "Equilibrium (Balance)", "Sensory Modalities")]
    print(f"\n3 sample records from Chapter 14 'The Somatic Nervous System' ({len(hearing)} sections; hearing is in 14.1):")
    for r in picks:
        shown = dict(r)
        shown["text"] = r["text"][:500] + f" […truncated for display; {words(r['text'])} words in full]"
        print(json.dumps(shown, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
