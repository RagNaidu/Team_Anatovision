"""Turn the citations inside an answer into numbered chips, and check each one against what was really retrieved.

No Streamlit here, so it can be tested. The honest part is `match`: a citation is "matched" only when it equals the
cite of a chunk that was actually retrieved for THIS question (or the exact verified-fix citation of a fix used).
Anything else is returned with matched=False and the UI shows it in red as "citation not found in retrieved sources".

parse_answer(answer, chunks, fixes) -> {"units": [...], "citations": [...], "n_unmatched": int}
  unit      {"text": sentence text without the [cites], "chips": [n, ...], "status": [{"kind", "label"}], "sentences": [...], "line": n}
  citation  {"n", "cite", "kind": notes|openstax|verified, "matched", "chunk": index|None, "fix": index|None,
             "sentences": [...], "support": [{"sentence", "spans": [(a, b), ...], "lines": [text, ...]}]}

Numbering is per distinct PASSAGE: the same retrieved passage (or the same verified fix) always has the same number
within one answer, numbers run 1, 2, 3 in order of first use, and two different passages never share a number even if
their cite strings are identical. When several retrieved passages carry the cite the answer used, each sentence is
matched to the passage whose lines best support it. `support` says which line(s) of the passage back each sentence.
"""
import html
import re

from src import sources as src_kinds
from src import verified

BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")
BARE_OPENSTAX_RE = re.compile(r"OpenStax A&P 2e\s*§\s*\d+(?:\.\d+)*")
UNDER_REVIEW_RE = re.compile(r"\bunder review\b", re.I)
REVIEWING_RE = re.compile(r"Dr\. Inglis is reviewing this line", re.I)
DOUBTFUL_RE = re.compile(r"\s*\(\s*flagged for review,? see fact-check\s*\)", re.I)
ABBREVIATIONS = ("dr", "e.g", "i.e", "vs", "cf", "fig", "approx", "st", "mr", "mrs", "no", "etc", "ca", "al")
MARKER_RE = re.compile(r"\[LINE UNDER REVIEW U\d+\]|\[flagged for review D\d+\]|\[LINE CORRECTED V\d+\]")
STOP = set("a an and are as at be been by can do does for from has have how in into is it its of on or that the their "
           "there these this those to was were what when where which who with also than then such may most more other "
           "some each both via per not but if all any one two".split())


def squash(text):
    return re.sub(r"\s+", " ", text).strip()


def norm_cite(text):
    text = re.sub(r"\^\(([^)]*)\)", r"\1", text)           # 4^(th) -> 4th, as qa.plain does
    return squash(text).lower()


def classify(content):
    """'verified' | 'guide' | 'web' | 'openstax' | 'notes' | None (not a citation, e.g. '[1]' or '[sic]')."""
    c = content.strip()
    if c.lower().startswith("verified by"):
        return "verified"
    if re.match(r"dissection guide\b", c, re.I):
        return "guide"
    if re.match(r"web:", c, re.I):
        return "web"
    if "openstax" in c.lower():
        return "openstax"
    if " > " in c or re.match(r"(Lecture\s+\d|ANA407)", c):
        return "notes"
    return None


def split_sentences(line):
    """Sentences of one line. A run of [cites] right after the full stop stays with the sentence before it."""
    out, start, i, n, depth = [], 0, 0, len(line), 0
    while i < n:
        ch = line[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth = max(0, depth - 1)
        if depth == 0 and ch in ".!?" and (i + 1 == n or line[i + 1] in " \t[)\"'"):
            word = re.search(r"([A-Za-z.]+)$", line[start:i])
            if ch == "." and word and word.group(1).lower().rstrip(".") in ABBREVIATIONS:
                i += 1
                continue
            j = i + 1
            while True:                                        # absorb "[cite] [cite]" and ")" after the stop
                m = re.match(r"\s*(\[[^\[\]]*\]|\))", line[j:])
                if not m:
                    break
                j += m.end()
            out.append(line[start:j].strip())
            start, i = j, j
            continue
        i += 1
    rest = line[start:].strip()
    if rest:
        out.append(rest)
    return [s for s in out if s]


def find_citations(sentence):
    """-> (text without citations, [(cite, kind), ...] in order)."""
    found, spans = [], []
    for m in BRACKET_RE.finditer(sentence):
        kind = classify(m.group(1))
        if kind:
            found.append((squash(m.group(1)), kind))
            spans.append(m.span())
    text = sentence
    for a, b in reversed(spans):
        text = text[:a] + text[b:]
    for m in list(BARE_OPENSTAX_RE.finditer(text)):         # OpenStax cited without brackets
        found.append((squash(m.group(0)), "openstax"))
    text = BARE_OPENSTAX_RE.sub("", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"\(\s*\)", "", text)
    return squash(text), found


def match_fix(cite, fixes):
    target = norm_cite(cite)
    for k, fix in enumerate(fixes):
        if norm_cite(verified.citation(fix)) == target:
            return k
    return None


def match_chunks(cite, kind, chunks):
    """Indexes of every retrieved chunk this cite can mean. Exact (normalised) equality only: no fuzzy matching."""
    target = norm_cite(cite)
    out = []
    for k, ch in enumerate(chunks):
        wanted = {norm_cite(ch.get("cite", "")), norm_cite(ch.get("breadcrumb", ""))}
        if kind != src_kinds.kind_of(ch):
            continue
        if target in wanted:
            out.append(k)
    return out


def match(cite, kind, chunks, fixes):
    """-> (chunk index | None, fix index | None): the first candidate (see parse_answer for the sentence-aware choice)."""
    if kind == "verified":
        return None, match_fix(cite, fixes)
    cands = match_chunks(cite, kind, chunks)
    return (cands[0] if cands else None), None


def choose_chunk(cands, chunks, sentence):
    """Among chunks sharing a cite, the one whose lines best support `sentence` (the first if none does)."""
    best, best_score = cands[0], -1.0
    for k in cands:
        score = evidence(chunks[k].get("text", ""), sentence)[0]
        if score > best_score:
            best, best_score = k, score
    return best


def parse_answer(answer, chunks, fixes=()):
    """Chips for every citation in `answer`. chunks: retrieved chunk dicts (with cite, breadcrumb, source_type, text)."""
    fixes = list(fixes)
    units, citations, by_key = [], [], {}

    def number(cite, kind, sentence):
        ck = fk = None
        if kind == "verified":
            fk = match_fix(cite, fixes)
        else:
            cands = match_chunks(cite, kind, chunks)
            ck = choose_chunk(cands, chunks, sentence) if cands else None
        key = ("fix", fk) if fk is not None else ("chunk", ck) if ck is not None else ("missing", kind, norm_cite(cite))
        if key not in by_key:
            citations.append({"n": len(citations) + 1, "cite": cite, "kind": kind, "matched": ck is not None or fk is not None,
                              "chunk": ck, "fix": fk, "sentences": [], "support": []})
            by_key[key] = citations[-1]
        entry = by_key[key]
        entry["sentences"].append(sentence)
        if ck is not None:
            spans = best_spans(chunks[ck].get("text", ""), sentence, max_spans=1)      # ONE supporting line, not three
            entry["support"].append({"sentence": sentence, "spans": spans,
                                     "lines": [squash(chunks[ck]["text"][a:b]) for a, b in spans]})
        return entry["n"]

    def unit_support(chips, sentence):
        """{chip number: [span]} - the one line of each cited passage that supports THIS sentence (for the Sources pane)."""
        out = {}
        for n in chips:
            entry = citations[n - 1]
            if entry["chunk"] is not None:
                out[n] = best_spans(chunks[entry["chunk"]].get("text", ""), sentence, max_spans=1)
        return out

    for line_no, line in enumerate(answer.splitlines()):
        if not line.strip():
            continue
        first_unit = len(units)
        pending = []                                          # sentences of this line not yet shown
        for sentence in split_sentences(line):
            text, found = find_citations(sentence)
            if found and not re.search(r"\w", text):             # a citation standing alone belongs to the sentence before
                text = pending[-1] if pending else ""
                chips = [number(c, k, text) for c, k in found]
                units.append(_unit(" ".join(pending), chips, [text], citations, found, unit_support(chips, text)))
                pending = []
                continue
            pending.append(text)
            if not found:
                continue
            chips = [number(c, k, text) for c, k in found]
            units.append(_unit(" ".join(pending), chips, [text], citations, found, unit_support(chips, text)))
            pending = []
        rest = squash(" ".join(pending))
        if rest:
            tail = _unit(rest, [], [rest], citations, [])
            if not tail["text"] and units and tail["status"]:      # a lone "(flagged for review)" after a cited sentence
                units[-1]["status"] += tail["status"]
            else:
                units.append(tail)
        for u in units[first_unit:]:
            u["line"] = line_no                               # which line of the answer (a bullet, a paragraph) the sentence is in
    return {"units": units, "citations": citations, "n_unmatched": sum(not c["matched"] for c in citations)}


def _unit(text, chips, sentences, citations, found, support=None):
    status = []
    if UNDER_REVIEW_RE.search(text) or REVIEWING_RE.search(text):
        status.append({"kind": "review", "label": "under review"})
    if DOUBTFUL_RE.search(text):
        text = squash(DOUBTFUL_RE.sub("", text))
        status.append({"kind": "doubtful", "label": "flagged for review"})
    for c, k in found:
        if k == "verified":
            status.append({"kind": "verified", "label": c})
    return {"text": text, "chips": chips, "status": status, "sentences": sentences, "support": support or {}}


# ----------------------------------------------------------------------------
# the passage shown in the Sources pane
# ----------------------------------------------------------------------------

def content_words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 2}


def passage_pieces(text):
    """Sentence-sized pieces of a passage with their character spans (lines first, then sentences)."""
    pieces = []
    for m in re.finditer(r"[^\n]+", text):
        line, base = m.group(0), m.start()
        start = 0
        for s in re.finditer(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])", line):
            pieces.append((base + start, base + s.start()))
            start = s.end()
        pieces.append((base + start, base + len(line)))
    return [(a, b) for a, b in pieces if text[a:b].strip()]


def evidence(passage, sentence, min_shared=3, min_ratio=0.5):
    """-> (best score, [(score, start, end), ...]) for the pieces of the passage that share enough words with the sentence."""
    want = content_words(sentence)
    scored = []
    for a, b in passage_pieces(passage):
        have = content_words(MARKER_RE.sub(" ", passage[a:b]))     # the withheld-line markers are not evidence
        if not have or not want:
            continue
        shared = len(want & have)
        ratio = shared / min(len(want), len(have))
        if shared >= min_shared and ratio >= min_ratio:
            scored.append((shared * ratio, a, b))
    scored.sort(reverse=True)
    return (scored[0][0] if scored else 0.0), scored


def best_spans(passage, sentence, min_shared=3, min_ratio=0.5, max_spans=3):
    """Character spans of the passage that the answer sentence was (probably) built from; [] when none matches."""
    _, scored = evidence(passage, sentence, min_shared, min_ratio)
    return sorted((a, b) for _, a, b in scored[:max_spans])


def passage_html(text, spans=(), fixes_by_marker=None):
    """HTML (escaped) for a retrieved passage. Fact-check markers become status chips, spans become <mark>."""
    fixes_by_marker = fixes_by_marker or {}
    out, pos = [], 0
    pieces = [(m.start(), m.end(), m.group(0)) for m in MARKER_RE.finditer(text)]

    def plain(a, b):
        seg, cur = [], a
        for sa, sb in sorted(s for s in spans if s[1] > a and s[0] < b):
            sa, sb = max(sa, a), min(sb, b)
            seg += [html.escape(text[cur:sa]), "<mark>", html.escape(text[sa:sb]), "</mark>"]
            cur = sb
        seg.append(html.escape(text[cur:b]))
        return "".join(seg)

    for a, b, marker in pieces:
        out.append(plain(pos, a))
        if marker.startswith("[LINE UNDER REVIEW"):
            out.append('<span class="chip chip-review">line under review: withheld</span>')
        elif marker.startswith("[flagged for review"):
            out.append('<span class="chip chip-flag">flagged for review</span>')
        else:
            fix = fixes_by_marker.get(marker.strip("[]").split()[-1])
            label = html.escape(fix["correction"]) if fix else "corrected line"
            out.append(f'<span class="chip chip-verified">corrected: {label}</span>')
        pos = b
    out.append(plain(pos, len(text)))
    return _lines("".join(out))


def _lines(html_text):
    """The passage as one <div> per line: indentation becomes a level (2 spaces = 1) and '- ' becomes a bullet, so every line
    is laid out the same way (no markdown list rendering, no uneven gaps)."""
    rows = []
    for raw in html_text.split("\n"):
        if not re.sub(r"<[^>]+>", "", raw).strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        body = raw.lstrip(" ")
        bullet = body.startswith("- ")
        if bullet:
            body = body[2:]
        rows.append(f'<div class="pl pl-{min(indent // 2, 4)}{" pl-b" if bullet else ""}">{body}</div>')
    return "".join(rows)



# ----------------------------------------------------------------------------
# repair: a citation that matches no retrieved passage is never shown to a student
# ----------------------------------------------------------------------------

def _parts(text):
    return [norm_cite(p) for p in text.split(" > ")]


def closest_chunk(cite, kind, chunks):
    """The one retrieved passage a non-matching citation clearly means, or None. 'Clearly' = same lecture (or same
    OpenStax text) and the same last heading; if that points at passages with different cites, it is not clear."""
    t = _parts(cite)
    found = {}
    for ch in chunks:
        if kind != src_kinds.kind_of(ch):
            continue
        for label in (ch.get("cite", ""), ch.get("breadcrumb", "")):
            c = _parts(label)
            if c and t[-1] == c[-1] and (kind == "openstax" or t[0] == c[0]):
                found[norm_cite(ch["cite"])] = ch["cite"]
    return next(iter(found.values())) if len(found) == 1 else None


def repair_citations(answer, chunks, fixes=()):
    """-> (new answer, {"repaired": [(old, new)], "dropped": [old], "removed": [claim text]}).
    Notes/OpenStax citations that match no retrieved chunk are rewritten to the clearly matching cite, or dropped; a
    sentence left with no citation because of a drop is removed (a claim must not stay without its source).
    Citations that already match, verified-fix citations, and sentences that never had a citation are left alone."""
    fixes = list(fixes)
    report = {"repaired": [], "dropped": [], "removed": []}
    lines_out = []
    for line in answer.splitlines():
        merged = []
        for s in split_sentences(line):
            if merged and not re.search(r"\w", BRACKET_RE.sub("", s)):      # a lone "[cite]" belongs to the sentence before
                merged[-1] += " " + s
            else:
                merged.append(s)
        kept = []
        for s in merged:
            lost = False

            def fix_one(m):
                nonlocal lost
                kind = classify(m.group(1))
                if kind in (None, "verified") or match_chunks(m.group(1), kind, chunks):
                    return m.group(0)
                new = closest_chunk(m.group(1), kind, chunks)
                if new:
                    report["repaired"].append((squash(m.group(1)), new))
                    return f"[{new}]"
                report["dropped"].append(squash(m.group(1)))
                lost = True
                return ""
            s2 = BRACKET_RE.sub(fix_one, s)
            s2 = re.sub(r"\s+([.,;:])", r"\1", re.sub(r"[ \t]{2,}", " ", s2)).strip()
            if lost and not any(classify(m.group(1)) for m in BRACKET_RE.finditer(s2)):
                report["removed"].append(squash(BRACKET_RE.sub("", s)))
                continue
            kept.append(s2)
        if kept:
            lines_out.append(" ".join(kept))
        elif not merged:
            lines_out.append("")
    return "\n".join(lines_out), report
