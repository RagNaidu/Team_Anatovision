"""Where quiz facts come from. Source order: verified fixes > course material (notes + dissection guides) > OpenStax > the approved web.

  build_pool(request, ...) -> Pool(passages, anchors, events, error)
    request = {"mode": "materials" | "topic", "selected": [lecture titles / 'Dissection Guide, Class N'], "topic": str, "n": 5 | 10}

Rules enforced here, before any model sees a word:
  * access: a course passage is used only if the user may open its lecture or guide (the same rule as Searcher.access_filter), and
    in "materials" mode only if the student also selected it. Nothing outside the grant is ever read into a prompt.
  * withheld lines: sentences the fact-check CONFIRMED as errors, doubtful ones, and lines replaced by a verified fix are removed from the
    usable text (a fix's correction becomes its own top-tier passage). A fact that is under review can never be a key or an explanation.
  * insufficient evidence: fewer usable passages than the quiz needs triggers the existing controlled web lookup (Wikipedia first, then the
    approved sources); if that is not enough either, the pool carries an error and no quiz is built. Model memory is never a source.
Every passage: {"id", "tier": verified|course|openstax|web, "kind", "label", "url", "text", "lecture", "guide"}; `text` is the usable text and is
what spans are checked against.
"""
import random
import re
from dataclasses import dataclass, field

from src import sources as src_kinds
from src import terms
from src.modes import qa
from src.retrieval import search as search_mod

MAX_POOL = 80                 # passages kept from the permitted material for one request
BUNDLE_COMPARISONS = 3        # comparison passages given with the passage a question is about
BUNDLE_CHARS = 5200
MIN_PRIMARY_CHARS = 300
MIN_CHARS = 200
MAX_CHARS = 1800
ANCHOR_FACTOR = 3              # at most this many drafts per requested question (the bounded budget)
MARGIN = 1                    # the evidence must offer room for this many more questions than asked (some drafts will be rejected)
TOPIC_COSINE = 0.55           # floor for a topic hit; the topic's own words must ALSO appear in the passage (see on_topic)
TOPIC_SHARE = 0.6             # share of the topic's meaningful words (by stem) a passage must contain (all of them for 1-2 words)
TIER = {"notes": "course", "dissection_guide": "course", "open_text": "openstax", "web": "web"}
INSUFFICIENT = "There is not enough source text for this request to write {n} well-supported questions. Try a broader topic or more lectures."


@dataclass
class Pool:
    passages: list = field(default_factory=list)
    topic: str = ""
    events: list = field(default_factory=list)
    error: str = ""
    web_used: bool = False

    def candidates(self, count, rng=None, used=()):
        return candidates(self.passages, count, self.topic, rng, used)


def allowed_chunk(chunk, allowed, note_lectures=frozenset()):
    """May this user read this chunk? Mirrors Searcher.access_filter. allowed None = everything (instructor)."""
    if chunk["source_type"] in ("open_text", "web"):
        return True
    if allowed is None:
        return True
    allowed = set(allowed)
    if note_lectures and allowed >= set(note_lectures):
        return True
    return chunk["lecture"] in allowed or chunk.get("lecture2", "") in allowed or (bool(chunk.get("guide")) and chunk["guide"] in allowed)


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def usable_text(chunk, ctx):
    """The chunk's text without any line that is under review, doubtful or replaced by a fix, whitespace-tidied, cut at a sentence end."""
    text = chunk["text"]
    if chunk["source_type"] == "notes":
        text, _marks = qa.annotate_chunk(chunk, ctx, {"U": 0, "D": 0, "V": 0})
        kept = [s for s in sentences(text) if not any(m in s for m in ("LINE UNDER REVIEW", "LINE CORRECTED", "flagged for review"))]
        text = "\n".join(kept)
    text = "\n".join(re.sub(r"(?<=\S)[ \t]+", " ", ln).rstrip() for ln in text.splitlines()).strip("\n")       # tidy, but KEEP the outline indentation
    if len(text) > MAX_CHARS:
        cut = text[:MAX_CHARS]
        end = max(cut.rfind(". "), cut.rfind(".\n"))
        text = cut[:end + 1] if end > MAX_CHARS * 0.5 else cut.rsplit(" ", 1)[0]
    return text


def with_headings(chunk, body):
    """The notes are outlines whose SUBJECT is the heading (a muscle's own name is the heading, not a line of its text). Without it a passage
    reads '- Fusiform muscle ... - Flexes, adducts shoulder' and neither a writer, a solver nor a citation can say what it is about. The heading
    path is put in front as outline lines, the body nested under it, so an outline-path span like 'Coracobrachialis / Flexes, adducts shoulder' is exact."""
    path = [re.sub(r"[:\s]+$", "", h) for h in (chunk.get("section_path") or []) if h and h.strip()]
    if chunk["source_type"] != "notes" or not path:
        return body
    lines = [("  " * i) + h for i, h in enumerate(path)]
    pad = "  " * len(path)
    return "\n".join(lines + [pad + ln if ln.strip() else ln for ln in body.splitlines()])


def passage_of(chunk, ctx):
    text = usable_text(chunk, ctx)
    if len(text) < MIN_CHARS:
        return None
    text = with_headings(chunk, text)
    from src import student_view as sv
    t = chunk["source_type"]
    label = qa.cite_for(chunk)
    url = ""
    if t == "open_text":
        url = sv.source_entry({"source_type": "open_text", "section_number": chunk.get("section_number", ""), "crumb": chunk["breadcrumb"],
                               "source_url": chunk.get("source_url", "")})["url"]
    elif t == "web":
        url = chunk.get("source_url", "")
    return {"id": chunk["id"], "tier": TIER[t], "kind": t, "label": label, "url": url, "text": text, "lecture": chunk.get("lecture", ""),
            "guide": chunk.get("guide", ""), "lecture2": chunk.get("lecture2", ""),
            "section": " > ".join((chunk.get("section_path") or [])[:2])}


def fix_passages(ctx, allowed, selected=None, topic_words=()):
    """A verified fix's correction is a top-tier passage of its own (the original wording is never used)."""
    out = []
    for f in ctx.get("fixes", []):
        if f["decision"] == "notes_correct" or not f.get("correction"):
            continue
        if allowed is not None and f["lecture"] not in allowed:
            continue
        if selected is not None and f["lecture"] not in selected:
            continue
        if selected is None and topic_words and not set(terms.stems_of(topic_words)) & terms.stem_set(f["correction"]):
            continue
        text = f["correction"].strip()
        if len(text) >= 40:
            out.append({"id": f"fix:{f['id']}", "tier": "verified", "kind": "verified", "label": f"Verified by {f['by']}, {f['date']}", "url": "",
                        "text": text, "lecture": f["lecture"], "guide": "", "section": f["breadcrumb"]})
    return out


def web_passages(query, lookup):
    res = lookup(query)
    out = []
    for p in res.passages:
        if len(p["text"]) < MIN_CHARS // 2:
            continue
        out.append({"id": p["id"], "tier": "web", "kind": "web", "label": f"Web: {p['title']} ({p['site']})", "url": p["url"],
                    "text": p["text"][:MAX_CHARS], "lecture": "", "guide": "", "section": p["title"], "license": p.get("license", "")})
    return out


def capacity(p):
    """How many distinct testing points a passage can reasonably offer: a short one gives one, a longer one two, a long one three."""
    return 1 + (len(p["text"]) >= 450) + (len(p["text"]) >= 1000)


def enough(passages, n):
    return sum(capacity(p) for p in passages) >= n + MARGIN


STOP = set("the and for that with from this which are was were has have not its into their they them there these those been being also can may".split())


def content_stems(text):
    return {w for w in terms.stem_set(text) if len(w) >= 4 and w not in STOP}


def similarity(a, b):
    return len(a & b) / max(1, len(a | b))


def quality(p):
    """A rough fact density: longer passages with several sentences and some capitalised terms or numbers carry more testable points."""
    n = len(sentences(p["text"]))
    return min(len(p["text"]), 1500) / 1500 + 0.15 * min(n, 6) + 0.05 * min(len(re.findall(r"\b[A-Z][a-z]{3,}\b|\d", p["text"])), 10)


def order_primaries(passages, rng):
    """Passages in the order they should be tried as the point of a question: strong ones first, each next one different from those already
    chosen (maximal marginal relevance), so the questions cover distinct objectives and no weak passage is sampled over and over."""
    pool = [p for p in passages if len(p["text"]) >= MIN_PRIMARY_CHARS] or list(passages)
    stems = {p["id"]: content_stems(p["text"]) for p in pool}
    chosen, rest = [], list(pool)
    rng.shuffle(rest)                                    # ties and near-ties differ from one request to the next
    while rest:
        best = max(rest, key=lambda p: quality(p) - 0.9 * max((similarity(stems[p["id"]], stems[c["id"]]) for c in chosen), default=0.0))
        chosen.append(best)
        rest.remove(best)
    return chosen


def bundle_for(primary, passages):
    """The passage a question is about, plus the passages most related to it (from the same permitted pool): they carry the facts about the
    alternatives, so wrong options can be real, comparable items whose own facts are stated in the evidence."""
    me = content_stems(primary["text"])
    ranked = sorted((p for p in passages if p["id"] != primary["id"]), key=lambda p: -similarity(me, content_stems(p["text"])))
    out, size, sections = [primary], len(primary["text"]), {primary["section"]}
    for p in ranked:
        if len(out) > BUNDLE_COMPARISONS or size + len(p["text"]) > BUNDLE_CHARS:
            break
        if similarity(me, content_stems(p["text"])) <= 0.02 or p["section"] in sections:
            continue
        out.append(p)
        size += len(p["text"])
        sections.add(p["section"])
    return out


def candidates(passages, count, topic="", rng=None, used=()):
    """Candidate questions in the order to try them: every primary once (angle 0), then second and third angles on the passages long enough
    to carry them. Each candidate is {"passages": bundle (primary first), "primary": id, "angle", "topic"}. At most `count` are returned."""
    rng = rng or random.Random()
    used = set(used)
    primaries = order_primaries([p for p in passages if p["id"] not in used], rng) + order_primaries([p for p in passages if p["id"] in used], rng) \
        if any(p["id"] in used for p in passages) and any(p["id"] not in used for p in passages) else order_primaries(passages, rng)
    out = []
    for angle in range(3):
        for p in primaries:
            if angle < capacity(p):
                out.append({"passages": bundle_for(p, passages), "primary": p["id"], "angle": angle, "topic": topic})
    return out[:count]


def build_pool(request, searcher, allowed, ctx, rng=None, web_lookup=None, client=None, model=None, scope_check=None):
    rng = rng or random.Random()
    n = request["n"]
    pool = Pool()
    note_lectures = getattr(searcher, "note_lectures", frozenset())
    passages, seen = [], set()

    def add(p):
        if p and p["id"] not in seen:
            seen.add(p["id"])
            passages.append(p)

    mode = request["mode"]
    web_ok = True
    if mode == "materials":
        selected = set(request.get("selected") or [])
        usable_sel = selected if allowed is None else selected & set(allowed)
        if not usable_sel:
            pool.error = "Choose at least one lecture or guide that is open to you."
            return pool
        pool.events.append(f"Selected {len(usable_sel)} of your lectures or guides")
        for p in fix_passages(ctx, allowed, usable_sel):
            add(p)
        for c in searcher.chunks:                          # the WHOLE permitted lecture or guide, in document order
            if c["source_type"] == "notes" and c["lecture"] in usable_sel:
                pass
            elif c["source_type"] == "dissection_guide" and c.get("guide") in usable_sel:
                pass
            else:
                continue
            if allowed_chunk(c, allowed, note_lectures) and len(passages) < MAX_POOL:
                add(passage_of(c, ctx))
        topic_for_web = " ".join(re.sub(r"^(Lecture \d+[a-z]?|Dissection Guide, Class \d+)\s*[-:,]?\s*", "", t) for t in sorted(usable_sel)[:2])
    else:
        topic = (request.get("topic") or "").strip()
        if len(topic) < 3:
            pool.error = "Type an anatomy topic (at least a few letters)."
            return pool
        if scope_check:
            label, sure = scope_check(topic)
            if label != "anatomy":
                pool.error = "That is not an anatomy topic. Quizzes cover anatomy only."
                return pool
            web_ok = sure
        pool.events.append(f"Topic: {topic}")
        for p in fix_passages(ctx, allowed, None, terms.meaningful_words(topic)):
            add(p)
        res = searcher.search(topic, k=12, allowed_lectures=None if allowed is None else sorted(allowed))
        if res.found:
            hits = search_mod.drop_exercises(res.hits)
            tw = set(terms.stems_of(terms.meaningful_words(topic)))
            for tier_pass in ("course", "openstax"):
                for h in hits:
                    c = h.chunk
                    have = terms.stem_set(c["breadcrumb"] + " " + c["text"])
                    need_words = len(tw) if len(tw) <= 2 else -(-int(len(tw) * TOPIC_SHARE * 10) // 10)
                    on_topic = h.cosine >= TOPIC_COSINE and bool(tw) and len(tw & have) >= need_words
                    if TIER.get(c["source_type"]) == tier_pass and on_topic and allowed_chunk(c, allowed, note_lectures):
                        add(passage_of(c, ctx))
        else:
            pool.events.append("The notes, guides and textbook had nothing relevant")
        topic_for_web = topic
    if not enough(passages, n) and web_ok and web_lookup is not None:
        pool.events.append(f"Only {len(passages)} usable passage(s), not enough for {n} questions; asked the approved web sources (Wikipedia first)")
        for p in web_passages(topic_for_web, web_lookup):
            add(p)
            pool.web_used = True
    pool.passages = passages
    if not enough(passages, n):
        pool.error = INSUFFICIENT.format(n=n)
        return pool
    pool.topic = (request.get("topic") or "").strip()
    pool.events.append(f"{len(passages)} usable passages")
    return pool
