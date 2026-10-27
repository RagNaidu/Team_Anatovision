"""What a STUDENT may see: a separate, smaller data structure built from the full (instructor-side) result.

The full result of `service.ask` carries fact-check text, verified-fix records, retrieval scores, token counts, cost, the
model name and the real pipeline events. None of that belongs in a student session, so the student views never receive
it: `build()` copies across only the fields listed here, and the student screens render nothing else.

Student answer (build):
  status, reason, notice, answer_text, units, citations, n_unmatched, sources, fixes, built,
  reviewing, check_before_relying, corrected, access_lectures, list_note
Guide (guide_state / guide_turn / guide_passages): the same idea for the walkthrough.

What replaces the instructor detail:
  a line the fact-check withheld     -> NEUTRAL_REVIEW, one sentence, outside any quoted note text
  a line the fact-check doubts       -> a marker "check_before_relying" (label CHECK_LABEL) on the sentence and the answer
  a line Dr. Inglis corrected        -> "Dr. Inglis corrected this line" and the corrected wording
No reason, no severity, no confidence, no AI wording, no scores, no cost, no model.

`leaks(obj)` lists forbidden strings found anywhere in a structure; the tests use it on everything built for a student.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from src import citations as cit
from src import trust
from src.modes import qa
from src.modes.guide import NO_CONSEQUENCE

NEUTRAL_REVIEW = qa.NEUTRAL_REVIEW                      # "Dr. Inglis is reviewing this line. Check with him before relying on it."
REVIEW_LABEL = "Being reviewed"
CHECK_LABEL = "Check before relying on this"
CHECK_SENTENCE = "Check before relying on this line."
DEFAULT_FIXER = "Dr. Inglis"

# Sentences of a model-written answer that talk about the fact-check are replaced by NEUTRAL_REVIEW.
LEAK_RE = re.compile(r"under review|fact-?check|flagged (?:for|by)|pending Dr\. Inglis|general anatomy knowledge|"
                     r"AI[- ]generated|standard statement|withheld|Dr\. Inglis decides|second check|\bverifier\b", re.I)
MARK_RE = re.compile(r"\s*\[(?:LINE UNDER REVIEW U\d+|flagged for review D\d+|LINE CORRECTED V\d+)\]")
DOUBTFUL_RE = cit.DOUBTFUL_RE
VERIFIED_RE = re.compile(r"\s*\[Verified by ([^\],]*)(?:,[^\]]*)?\]")

# Strings that must never appear anywhere in what a student session is given (used by tests and by leaks()).
FORBIDDEN = (r"under review", r"fact-?check", r"flagged", r"pending Dr", r"Dr\. Inglis decides", r"general anatomy knowledge",
             r"AI[- ]generated", r"\bseverity\b", r"\bconfidence\b", r"second check", r"verifier", r"standard statement",
             r"withheld", r"LINE UNDER REVIEW", r"\bcosine\b", r"retrieval score", r"hybrid", r"\btokens?\b", r"\bclaude-",
             r"\$\d", r"reciprocal", r"BM25", r"\bscore\b", r"sonnet|haiku|opus")
_FORBIDDEN_RE = re.compile("|".join(FORBIDDEN), re.I)

PASSAGE_NOTE = {"reviewing": NEUTRAL_REVIEW, "check": CHECK_SENTENCE}


def leaks(obj):
    """Every forbidden string found in the text of `obj` (dicts, lists, strings; keys included). [] = clean."""
    found = []

    def walk(x):
        if isinstance(x, str):
            found.extend(m.group(0) for m in _FORBIDDEN_RE.finditer(x))
        elif isinstance(x, dict):
            for k, v in x.items():
                walk(str(k))
                walk(v)
        elif isinstance(x, (list, tuple, set)):
            for v in x:
                walk(v)

    walk(obj)
    return found


def corrected_sentence(by=""):
    return f"{(by or DEFAULT_FIXER).strip()} corrected this line."


# ----------------------------------------------------------------------------
# text
# ----------------------------------------------------------------------------

def scrub_text(text):
    """Sentences that mention the fact-check become NEUTRAL_REVIEW (once). A sentence that says a line is being reviewed is
    replaced WHOLE by the neutral sentence, so nothing the model wrote about that line (its claim, a paraphrase) survives.
    -> (text, replaced?)."""
    out, replaced = [], False
    for line in text.splitlines():
        sentences = cit.split_sentences(line) or ([line.strip()] if line.strip() else [])
        kept = []
        for s in sentences:
            if cit.REVIEWING_RE.search(s) or LEAK_RE.search(s):
                replaced = True
                if NEUTRAL_REVIEW not in kept:
                    kept.append(NEUTRAL_REVIEW)
            elif kept and kept[-1] == NEUTRAL_REVIEW and s.lower().startswith("check with him"):
                continue                                   # the second half of the neutral sentence
            else:
                kept.append(s)
        out.append(" ".join(kept))
    return "\n".join(out), replaced


def clean_passage(text, fixes_by_marker=None):
    """A notes passage as the model saw it -> (plain text, marks). The fact-check markers are removed from the quoted text;
    a corrected line shows its corrected wording. marks: subset of reviewing / check / corrected, in order of appearance."""
    fixes_by_marker = fixes_by_marker or {}
    marks = []

    def swap(m):
        tag = m.group(0).strip()
        if tag.startswith("[LINE UNDER REVIEW"):
            kind, new = "reviewing", ""
        elif tag.startswith("[flagged for review"):
            kind, new = "check", ""
        else:
            kind = "corrected"
            fix = fixes_by_marker.get(tag.strip("[]").split()[-1])
            new = " " + fix["correction"] if fix and fix.get("correction") else ""
        if kind not in marks:
            marks.append(kind)
        return new

    text = MARK_RE.sub(swap, text)
    text = re.sub(r"[ \t]+([.,;:])", r"\1", text)
    lines = [l for l in text.splitlines() if re.search(r"\w", l)]
    return "\n".join(lines), marks


def clean_item(text):
    """One card line of the Guide -> {"text", "mark"} or None. Review wording is removed and shown as a mark instead."""
    mark = None
    if DOUBTFUL_RE.search(text):
        text, mark = DOUBTFUL_RE.sub("", text), "check"
    if VERIFIED_RE.search(text):
        text, mark = VERIFIED_RE.sub("", text), "corrected"
    if MARK_RE.search(text):
        text, mark = MARK_RE.sub("", text), "reviewing"
    text, replaced = scrub_text(text.strip())
    if replaced:
        mark = "reviewing"
    return {"text": text, "mark": mark} if re.search(r"\w", text) else None


def clean_line(text):
    """A plain string with the same cleaning as clean_item (for lines that are not list items)."""
    if not text:
        return text
    item = clean_item(text)
    return item["text"] if item else ""


# ----------------------------------------------------------------------------
# the Q&A answer
# ----------------------------------------------------------------------------

def split_path(breadcrumb):
    """'Lecture 16b - Middle Ear > III. Middle Ear > Walls' -> ('Lecture 16b · Middle Ear', 'III. Middle Ear › Walls')."""
    parts = [p.strip() for p in breadcrumb.split(" > ") if p.strip()]
    rest = []
    for p in parts[1:]:
        if not rest or rest[-1] != p:
            rest.append(p)
    return (parts[0] if parts else "").replace(" - ", " · ", 1), " › ".join(rest)


def dedupe_crumb(breadcrumb):
    """'A > B > B > C' -> 'A > B > C' (a heading repeated by the notes' outline is said once)."""
    out = []
    for p in breadcrumb.split(" > "):
        if not out or out[-1].strip() != p.strip():
            out.append(p)
    return " > ".join(out)


def path_short(lecture, crumb, source_type):
    """The short passage name used under a chip: 'Lecture 08 · The Femoral Triangle'."""
    if source_type == "open_text":
        return "OpenStax A&P 2e" + (f" · {crumb.split(' › ')[-1]}" if crumb else "")
    code = lecture.split(" - ")[0].strip()
    last = crumb.split(" › ")[-1] if crumb else lecture.split(" - ", 1)[-1]
    return f"{code} · {last}"


def short_label(source_type, lecture, section_number="", cite=""):
    """A short chip label: 'Notes · L16b', 'Notes · ANA407', 'OpenStax · §14.1', 'Guide · C17', 'Web · NLM MeSH'."""
    if source_type == "dissection_guide":
        m = re.search(r"Class (\d+)", cite)
        return "Guide · " + (f"C{m.group(1)}" if m else "guide")
    if source_type == "web":
        return "Web · " + (lecture or "web")
    if source_type == "open_text":
        return f"OpenStax · §{section_number}" if section_number else "OpenStax"
    code = lecture.split(" - ")[0].split(" Class ")[0].strip()
    m = re.match(r"Lecture\s+(\S+)$", code)
    return "Notes · " + (f"L{m.group(1)}" if m else code)


def _source(i, c, fixes_by_marker):
    """One retrieved passage as a student may see it: no scores, no markers inside the quoted text."""
    text, marks = (clean_passage(c["text"], fixes_by_marker) if c["source_type"] == "notes" else (c["text"], []))
    notes = [PASSAGE_NOTE[m] for m in marks if m in PASSAGE_NOTE]
    for m in c.get("marks", []):
        if m["kind"] == "verified" and m["id"] in fixes_by_marker:
            notes.append(corrected_sentence(fixes_by_marker[m["id"]]["by"]))
    title, crumb = split_path(c["breadcrumb"])
    if c["source_type"] == "web":
        title, crumb = c.get("title") or title, c.get("site") or c["lecture"]
    elif c["source_type"] == "dissection_guide":
        title, crumb = "Dissection guide", re.sub(r"^Dissection Guide,\s*", "", c["cite"])
    return {"index": i, "source_type": c["source_type"], "breadcrumb": dedupe_crumb(c["breadcrumb"]), "title": title, "crumb": crumb,
            "path_short": (f'{c.get("site") or c["lecture"]} · {title}' if c["source_type"] == "web"
                           else crumb if c["source_type"] == "dissection_guide"
                           else path_short(c["lecture"], crumb, c["source_type"])),
            "short": short_label(c["source_type"], c["lecture"], c.get("section_number", ""), c["cite"]), "lecture": c["lecture"],
            "site": c.get("site", ""), "retrieved": c.get("retrieved", ""), "license": c.get("license", ""),
            "cite": c["cite"], "text": text, "marks": marks, "notes": notes, "section_number": c.get("section_number", ""),
            "source_url": c.get("source_url", ""), "uploaded": c.get("uploaded", ""),
            "updated": (c.get("uploaded") or trust.notes_updated(c["lecture"])) if c["source_type"] == "notes" else ""}


def _fix(f):
    return {"marker": f.get("marker", ""), "by": f["by"], "date": f["date"], "correction": f["correction"],
            "breadcrumb": f["breadcrumb"], "lecture": f["lecture"], "label": corrected_sentence(f["by"])}


STATUS_KIND = {"review": ("reviewing", REVIEW_LABEL), "doubtful": ("check", CHECK_LABEL)}


def _collapse_neutral(text):
    n = re.escape(NEUTRAL_REVIEW)
    return re.sub(rf"{n}(?:\s+{n})+", NEUTRAL_REVIEW, text)


def _unit(u, fixes):
    text, replaced = scrub_text(u["text"])
    status = []
    for s in u["status"]:
        if s["kind"] in STATUS_KIND:
            kind, label = STATUS_KIND[s["kind"]]
            status.append({"kind": kind, "label": label})
        elif s["kind"] == "verified":
            by = next((f["by"] for f in fixes if s["label"] == f"Verified by {f['by']}, {f['date']}"), "")
            status.append({"kind": "corrected", "label": corrected_sentence(by).rstrip(".")})
    if replaced and not any(s["kind"] == "reviewing" for s in status):
        status.append({"kind": "reviewing", "label": REVIEW_LABEL})
    kinds = {s["kind"] for s in status}
    return {"line": u.get("line"), "text": text, "chips": list(u["chips"]), "support": {n: [list(sp) for sp in spans] for n, spans in u.get("support", {}).items()},
            "status": status, "reviewing": "reviewing" in kinds,
            "check_before_relying": "check" in kinds, "corrected": "corrected" in kinds}


BOOK_URL = "https://openstax.org/details/books/anatomy-and-physiology-2e"       # the book's contents page: the fallback link
URL_CHECK = Path(__file__).resolve().parents[1] / "data" / "processed" / "openstax_url_check.json"


@lru_cache(maxsize=1)
def verified_openstax_urls():
    """Section URLs that scripts/verify_openstax_urls.py found really exist. Anything not in this set links to the contents page."""
    try:
        return frozenset(json.loads(URL_CHECK.read_text(encoding="utf-8"))["ok"])
    except (OSError, ValueError, KeyError):
        return frozenset()


def lecture_label(lecture):
    return lecture.replace(" - ", ", ", 1)


def source_entry(src):
    """One line of the 'Sources' list under an answer: {"label", "url"}. url is "" for notes and guides (they open in the side panel)."""
    t = src["source_type"]
    if t == "open_text":
        what = f"section {src['section_number']}" if src.get("section_number") else (src.get("crumb") or "textbook")
        url = src.get("source_url", "")
        return {"label": f"OpenStax Anatomy & Physiology 2e, {what}", "url": url if url in verified_openstax_urls() else BOOK_URL}
    if t == "web":
        title = re.sub(r"^MeSH:\s*", "", src.get("title", ""))
        return {"label": f'{src.get("site") or "Web"}, “{title}”', "url": src.get("source_url", "")}
    if t == "dissection_guide":
        return {"label": src["cite"], "url": ""}
    section = (src.get("crumb") or "").split(" › ")[-1]
    topic = src["lecture"].split(" - ", 1)[-1]
    tail = f", {section}" if section and section != topic else ""
    return {"label": f"Dr. Inglis's lecture notes: {lecture_label(src['lecture'])}{tail}", "url": ""}


def _blocks(units):
    """The answer as display blocks, one per line of the answer (a heading, a bullet, a paragraph, a step).
    Markers (source numbers) sit at the end of a block, and a run of consecutive blocks that cite exactly the same sources shows them
    only on the last block of the run, so the same marker never repeats on consecutive lines."""
    by_line, order = {}, []
    for k, u in enumerate(units):
        key = u.get("line", k)
        if key not in by_line:
            by_line[key] = {"units": [], "chips": [], "status": [], "first_unit": k}
            order.append(key)
        b = by_line[key]
        b["units"].append(k)
        b["chips"] += [n for n in u["chips"] if n not in b["chips"]]
        b["status"] += [x for x in u["status"] if x["kind"] in ("reviewing", "check", "corrected") and x not in b["status"]]
    blocks = []
    for key in order:
        b = by_line[key]
        text = " ".join(units[k]["text"] for k in b["units"] if units[k]["text"]).strip()
        if not text or text == qa.BRIEF_CLOSING:
            continue
        blocks.append({"text": text, "markers": sorted(b["chips"]), "status": b["status"], "unit": b["first_unit"],
                       "note": text == qa.LIST_NOTE})
    for k, b in enumerate(blocks):
        nxt = blocks[k + 1]["markers"] if k + 1 < len(blocks) else None
        if b["markers"] and nxt == b["markers"]:
            b["markers"] = []
    return blocks


def build(raw):
    """The student-safe answer from the full result of service.ask. Nothing outside this function's output reaches a student."""
    fixes_raw = list(raw.get("verified_fix_used", []))
    fixes_by_marker = {f["marker"]: f for f in raw.get("verified_marks", fixes_raw) if f.get("marker")}
    fixes = [_fix(f) for f in fixes_raw]
    sources = [_source(i, c, fixes_by_marker) for i, c in enumerate(raw.get("retrieved_chunks", []))]
    chunks_for_parse = sources

    status = raw["status"]
    units, citations, n_unmatched = [], [], 0
    if status in ("answered", "access_limited") and raw.get("answer_text"):
        parsed = cit.parse_answer(raw["answer_text"], chunks_for_parse,
                                  [{"by": f["by"], "date": f["date"]} for f in fixes])
        units, first_neutral = [], None
        for u in (_unit(u, fixes) for u in parsed["units"]):
            u["text"] = _collapse_neutral(u["text"])
            if u["text"] == NEUTRAL_REVIEW and first_neutral is not None:       # one review sentence per answer
                first_neutral["chips"] += [n for n in u["chips"] if n not in first_neutral["chips"]]
                continue
            if u["text"] == NEUTRAL_REVIEW:
                first_neutral = u
            units.append(u)
        for c in parsed["citations"]:
            label = c["cite"]
            if c["kind"] == "verified" and c["fix"] is not None:
                label = fixes[c["fix"]]["label"]
            support = [{"sentence": scrub_text(DOUBTFUL_RE.sub("", x["sentence"]).strip())[0], "spans": x["spans"],
                        "lines": x["lines"]} for x in c["support"]]
            short = ("Corrected" if c["kind"] == "verified" else sources[c["chunk"]]["short"] if c["chunk"] is not None else "Not found")
            citations.append({"n": c["n"], "cite": label, "short": short, "kind": c["kind"], "matched": c["matched"],
                              "chunk": c["chunk"], "fix": c["fix"], "support": support})
        n_unmatched = parsed["n_unmatched"]
        answer_text = "\n".join(u["text"] for u in units if u["text"])
    else:
        answer_text, _ = scrub_text(raw.get("answer_text", ""))

    blocks = _blocks(units) if units else []
    used = []
    for c in citations:
        if c["chunk"] is not None and c["chunk"] not in used:
            used.append(c["chunk"])
    cited_fix = [fixes[c["fix"]] for c in citations if c["fix"] is not None]
    built = {"notes": [sources[k]["breadcrumb"] for k in used if sources[k]["source_type"] == "notes"],
             "guides": [f'{sources[k]["title"]}: {sources[k]["crumb"]}' for k in used if sources[k]["source_type"] == "dissection_guide"],
             "web": [f'{sources[k]["title"]} ({sources[k]["site"]})' for k in used if sources[k]["source_type"] == "web"],
             "textbook": [sources[k]["breadcrumb"] for k in used if sources[k]["source_type"] == "open_text"],
             "corrected": [{"by": f["by"], "breadcrumb": f["breadcrumb"]} for f in cited_fix]}
    notes_used = [sources[k] for k in used if sources[k]["source_type"] == "notes"]
    trust_line = {"notes": bool(notes_used), "guides": any(sources[k]["source_type"] == "dissection_guide" for k in used), "textbook": any(sources[k]["source_type"] == "open_text" for k in used),
                  "web": any(sources[k]["source_type"] == "web" for k in used),
                  "updated": max((x["updated"] for x in notes_used if x["updated"]), default="")}
    doubtful_hit = any(f["kind"] == "doubtful" for f in raw.get("flags_hit", []))
    review_hit = any(f["kind"] == "under_review" for f in raw.get("flags_hit", []))
    sources_list, cite_unit = [], {}
    for c in citations:
        if not c["matched"]:
            continue
        if c["kind"] == "verified" and c["fix"] is not None:
            f = fixes[c["fix"]]
            entry = {"label": f"Dr. Inglis, verified correction ({f['date']})", "url": ""}
        elif c["chunk"] is not None:
            entry = source_entry(sources[c["chunk"]])
        else:
            continue
        sources_list.append({"n": c["n"], "chunk": c["chunk"], "fix": c["fix"], **entry})
        for k, u in enumerate(units):
            if c["n"] in u["chips"]:
                cite_unit[c["n"]] = k
                break
    types = {sources[c["chunk"]]["source_type"] for c in citations if c["matched"] and c["chunk"] is not None}
    names = [n for t, n in (("open_text", "OpenStax"),) if t in types]
    names += list(dict.fromkeys(sources[c["chunk"]]["site"] for c in citations
                                if c["matched"] and c["chunk"] is not None and sources[c["chunk"]]["source_type"] == "web"))
    own = bool(types & {"notes", "dissection_guide"}) or any(c["kind"] == "verified" and c["matched"] for c in citations)
    footer = ""
    if names and not own and status in ("answered", "access_limited"):
        footer = f"Based on {' and '.join([', '.join(names[:-1]), names[-1]] if len(names) > 1 else names)}, not Dr. Inglis's notes."
    return {"status": status, "reason": raw.get("reason", ""), "notice": raw.get("access_notice", ""),
            "blocks": blocks, "sources_list": sources_list, "cite_unit": cite_unit, "footer": footer,
            "answer_text": answer_text, "units": units, "citations": citations, "n_unmatched": n_unmatched,
            "sources": sources if status == "answered" or status == "access_limited" else [], "fixes": fixes, "built": built,
            "reviewing": review_hit or any(u["reviewing"] for u in units),
            "check_before_relying": doubtful_hit or any(u["check_before_relying"] for u in units),
            "corrected": bool(cited_fix), "access_lectures": list(raw.get("access_lectures", [])),
            "list_note": bool(raw.get("list_note_added")), "trust": trust_line, "used": used,
            "web": bool(raw.get("web")), "web_label": raw.get("web_label", "") if raw.get("web") else "",
            "term": raw.get("mode") == "term"}


def built_lines(built):
    """The short, plain 'How this answer was built' text for a student."""
    lines = []
    if built["notes"]:
        lines.append(("Course notes used", built["notes"]))
    if built["textbook"]:
        lines.append(("Textbook passages used (OpenStax, not course notes)", built["textbook"]))
    if built.get("guides"):
        lines.append(("Dissection guide slides used", built["guides"]))
    if built.get("web"):
        lines.append(("Web pages used (not course notes)", built["web"]))
    if not lines:
        lines.append(("Passages used", []))
    return lines, [corrected_sentence(f["by"]) for f in built["corrected"]]


# ----------------------------------------------------------------------------
# the Guide
# ----------------------------------------------------------------------------

CARD_LISTS = ("identify_these", "what_you_should_see", "landmarks_relations", "variation_if_stated")


def _norm_words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def dedupe_card(card):
    """Each fact once. Within the card lists (should-see first, then landmarks, then identify), an item is dropped when an earlier
    item already says it: identical wording, or all of its content words appear in an earlier, longer item."""
    seen, out = [], {k: [] for k in card}
    for key in ("what_you_should_see", "landmarks_relations", "identify_these", "variation_if_stated"):
        for item in card.get(key, []):
            words = _norm_words(item["text"])
            if key != "variation_if_stated" and any(item["text"].strip().lower() == t.strip().lower()
                                                    or (key != "identify_these" and words and words <= w and len(w) > len(words))
                                                    for t, w in seen):
                continue
            seen.append((item["text"], words))
            out[key].append(item)
    return out


def guide_state(s):
    """GuideSession.state() -> the same shape with only what a student may see (no fact-check meta, no cache counts)."""
    out = {k: s[k] for k in ("lecture", "banner", "stage", "current", "total", "done", "progress", "stations",
                              "body_type", "empty", "needs_recheck", "can_advance", "finished")}
    out["stations"] = [{"n": x["n"], "name": x["name"], "status": x["status"]} for x in s["stations"]]
    card, meta = s["card"], s["meta"]
    out["card"] = None if card is None else dedupe_card({k: [i for i in (clean_item(t) for t in card[k]) if i] for k in CARD_LISTS})
    out["meta"] = None if meta is None else {"reviewing": bool(meta["review"]), "check": bool(meta["doubtful"]),
                                              "corrected": bool(meta["verified"]),
                                              "corrected_by": next((f["by"] for f in meta["verified"]), "")}
    out["check"] = None if s["check"] is None else {"pending": s["check"]["pending"],
                                                    "lines": [clean_line(l) for l in s["check"]["lines"]]}
    return out


def guide_turn(turn):
    """One Guide turn -> {"detail": ...} with the judged-description result cleaned. Cost, tokens, events, CLI lines dropped."""
    d = turn.get("detail")
    if not d:
        return {"detail": None}
    clean = {"station": d.get("station"), "verdict": d["verdict"]}
    if d["verdict"] == "error":
        return {"detail": clean}
    clean["feedback"] = scrub_text(d.get("feedback") or "")[0]
    clean["should_see"] = clean_line(d.get("should_see") or "")
    clean["consequence"] = "" if (d.get("consequence") or "") == NO_CONSEQUENCE else clean_line(d.get("consequence") or "")
    return {"detail": clean}


def guide_passages(passages):
    """GuideSession.passages(n) -> [{"breadcrumb", "text", "notes"}] without markers inside the quoted text."""
    out = []
    for p in passages:
        text, marks = clean_passage(p["text"], p.get("fixes"))
        notes = [PASSAGE_NOTE[m] for m in marks if m in PASSAGE_NOTE]
        if "corrected" in marks:
            notes.append(corrected_sentence(next((f["by"] for f in (p.get("fixes") or {}).values()), "")))
        out.append({"breadcrumb": dedupe_crumb(p["breadcrumb"]), "text": text, "notes": notes})
    return out


def guide_built(passages):
    """Plain 'how was this built' for a Guide station: which notes passages, and whether a correction applies."""
    corrected = [corrected_sentence(f["by"]) for p in passages for f in (p.get("fixes") or {}).values()]
    return {"notes": [dedupe_crumb(p["breadcrumb"]) for p in passages], "textbook": [], "corrected": [{"by": f["by"], "breadcrumb": p["breadcrumb"]}
            for p in passages for f in (p.get("fixes") or {}).values()]}, corrected


def slide_guide_state(st):
    """SlideGuideSession.state() -> what a student may see: station names, steps, slide numbers, progress. Nothing else."""
    out = {k: st[k] for k in ("guide", "class_label", "usable", "no_text", "total", "current", "done", "progress", "can_next", "can_back",
                              "finished")}
    out["stations"] = [{"n": x["n"], "title": scrub_text(x["title"])[0], "slides": list(x["slides"]), "status": x["status"]} for x in st["stations"]]
    cur = st["station"]
    out["station"] = None if cur is None else {"n": cur["n"], "title": scrub_text(cur["title"])[0], "steps": [scrub_text(t)[0] for t in cur["steps"]],
                                               "slides": list(cur["slides"]), "image_only": cur["image_only"], "cite": cur["cite"],
                                               "text": scrub_text(cur["text"])[0]}
    return out


def slide_guide_turn(turn):
    """One judged description -> {"detail": {"station", "verdict", "feedback"}} (no tokens, cost or events)."""
    d = turn.get("detail")
    if not d:
        return {"detail": None}
    return {"detail": {"station": d["station"], "verdict": d["verdict"], "feedback": scrub_text(d.get("feedback") or "")[0]}}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, default=str)
