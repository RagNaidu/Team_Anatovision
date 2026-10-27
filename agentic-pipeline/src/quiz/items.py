"""The quiz item: its schema, the checks a draft must pass before any model verifies it, and freezing (shuffle, ids, evidence copies).

A frozen item (PRIVATE: it holds the key, the explanation and the evidence; the student view is `public_view`):
  {"item_id", "selection_mode": "single",           # a later "multiple" mode uses the same answer_ids list
   "stem", "lead_in", "options": [{"id": "A", "text"}...], "answer_ids": ["C"],
   "explanation", "key_support": [{"source_id", "span"}], "explanation_support": [...],
   "alternatives": {"A": {"why_wrong", "support": [...]}, ...},        # one per option that is not a key
   "objective", "evidence": {source_id: {"id", "tier", "label", "url", "text", "kind"}},    # frozen copies of what was cited
   "tiers": ["course"], "checks": {...}, "review": {"status": "unreviewed"}, "created"}

Local checks (before any model is asked) follow the NBME writing rules in reports/quiz_item_writing_checklist.md, and refuse a
citation unless its source id was supplied and its span really occurs in that source's usable text.
"""
import hashlib
import random
import re
import time

QUIZ_VERSION = 4            # bump when the checks or the item format change: older saved items are then not reused
N_OPTIONS = 4
IDS = "ABCDE"
MIN_SPAN_CHARS = 20
MIN_SPAN_WORDS = 4
MAX_STEM = 700
MAX_OPTION_WORDS = 14
VAGUE = re.compile(r"\b(usually|often|frequently|generally|typically|commonly|may|might|could be|is associated with|is important|is useful for|sometimes)\b", re.I)
ABSOLUTE = re.compile(r"\b(always|never|only|all|none|every|completely|entirely)\b", re.I)
BANNED_OPTIONS = re.compile(r"\b(none of the above|all of the above|both [a-e] and [a-e]|a and b|b and c)\b", re.I)
NEGATIVE = re.compile(r"\b(except|not true|which is false|least likely|incorrect)\b|\bNOT\b")
LEAD_START = re.compile(r"^(which|what|where|how many|how)\b", re.I)
ABSENCE = re.compile(r"\b(not (?:mentioned|described|stated|listed|discussed|named|given|included)|no mention|does not (?:appear|list|mention|state|describe)|"
                     r"is not (?:part of|in) the passage|absent from|nothing (?:is|in the passage) (?:said|stated))\b", re.I)
MASKS = ("LINE UNDER REVIEW", "LINE CORRECTED", "flagged for review")


def norm(text):
    text = (text or "").lower().replace("’", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def words(text):
    return re.findall(r"[a-z0-9]+", norm(text))


def squash(text):
    """Lower-case words only: punctuation, hyphens, quotes and spacing differences do not matter, the words and their order do."""
    return re.sub(r"[^a-z0-9]+", " ", norm(text)).strip()


BULLET = re.compile(r"^\s*(?:[-*\u2022o]\s+)+")


def outline_lines(text):
    """[(depth, squashed line)] of an outline-style passage (notes are bulleted outlines: indentation is the hierarchy)."""
    out = []
    for raw in text.splitlines():
        body = BULLET.sub("", raw)
        if squash(body):
            out.append(((len(raw) - len(raw.lstrip(" "))) // 2, squash(body)))
    return out


def outline_path_in(text, span):
    """True if the span is a set of whole LINES of ONE outline entry: its first line is a heading (or any line) of the passage, and every
    following span line occurs, in order, inside that first line's subtree (deeper, before the outline returns to the first line's level).
    Lines of the entry may be skipped, but a heading can never be joined to a fact that belongs to a different heading."""
    segs = [squash(BULLET.sub("", ln)) for ln in span.splitlines()]
    segs = [x for x in segs if x]
    lines = outline_lines(text)
    if len(segs) < 2 or len(segs) > 6 or not lines or len(squash(" ".join(segs))) < MIN_SPAN_CHARS or sum(len(x.split()) for x in segs) < MIN_SPAN_WORDS:
        return False

    def same(ln, seg):
        return ln == seg or (len(seg) >= 6 and seg in ln)

    for i, (root, ln) in enumerate(lines):
        if not same(ln, segs[0]):
            continue
        k = 1
        for d, other in lines[i + 1:]:
            if d <= root:
                break                                           # the entry ended
            if same(other, segs[k]):
                k += 1
                if k == len(segs):
                    return True
    return False


def span_in(text, span):
    """True if the span really occurs in the source text: its words in order without gaps, or (for outline notes) an outline path of its lines.
    It must also be long enough to mean something."""
    s = squash(span)
    if len(s) >= MIN_SPAN_CHARS and len(s.split()) >= MIN_SPAN_WORDS and f" {s} " in f" {squash(text)} ":
        return True
    return "\n" in (span or "").strip() and outline_path_in(text, span.strip())


def check_support(label, support, evidence, problems):
    """Every citation: the source id is one that was supplied, the span occurs in its usable text, no masked-line marker."""
    if not isinstance(support, list) or not support:
        problems.append(f"{label}: no supporting span")
        return
    for sp in support:
        if not isinstance(sp, dict) or sp.get("source_id") not in evidence:
            problems.append(f"{label}: unknown source id {sp.get('source_id') if isinstance(sp, dict) else sp!r}")
        elif any(m.lower() in norm(sp.get("span", "")) for m in MASKS) or not span_in(evidence[sp["source_id"]]["text"], sp.get("span", "")):
            problems.append(f"{label}: span not found in {sp['source_id']}")


def repair_span_sources(d, evidence):
    """A model sometimes attaches a correct verbatim span to the wrong passage id when several passages are supplied. If a span is not in the
    passage it names but occurs verbatim in EXACTLY ONE other supplied passage, the id is corrected. A span found nowhere is left alone (it will
    be rejected); nothing is ever invented or paraphrased. Returns how many ids were corrected."""
    fixed = 0
    parts = []
    if isinstance(d, dict):
        parts += [d.get("key_support"), d.get("explanation_support")]
        parts += [a.get("support") for a in d.get("alternatives") or [] if isinstance(a, dict)]
    for part in parts:
        for sp in part or []:
            if not isinstance(sp, dict) or not sp.get("span"):
                continue
            named = evidence.get(sp.get("source_id"))
            if named is not None and span_in(named["text"], sp["span"]):
                continue
            where = [pid for pid, p in evidence.items() if span_in(p["text"], sp["span"])]
            if len(where) == 1:
                sp["source_id"] = where[0]
                fixed += 1
    return fixed


def same_point(a, b):
    """Two items that test the same fact: their KEY citations overlap heavily in the same source passage, however the questions are worded."""
    for x in a.get("key_support", []):
        for y in b.get("key_support", []):
            if x["source_id"] == y["source_id"]:
                wx, wy = set(squash(x["span"]).split()), set(squash(y["span"]).split())
                if wx and wy and len(wx & wy) / len(wx | wy) >= 0.5:
                    return True
    return False


def item_hash(stem, lead_in, option_texts, key_text):
    raw = "|".join([norm(stem), norm(lead_in), *sorted(norm(t) for t in option_texts), "key:" + norm(key_text)])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def validate_draft(d, evidence):
    """-> list of problems (empty = the draft may go on to the independent solvers). evidence: {source_id: passage}."""
    p = []
    if not isinstance(d, dict):
        return ["not an object"]
    stem, lead = (d.get("stem") or "").strip(), (d.get("lead_in") or "").strip()
    opts = d.get("options")
    if not lead or not lead.endswith("?") or not LEAD_START.match(lead):
        p.append("lead-in must be one closed question starting Which/What/Where/How and ending with ?")
    if lead.count("?") != 1:
        p.append("lead-in must contain exactly one question")
    if len(stem) > MAX_STEM:
        p.append("stem too long")
    if NEGATIVE.search(stem + " " + lead):
        p.append("negative phrasing (NBME flaw)")
    if VAGUE.search(stem + " " + lead):
        p.append("vague term in the stem or lead-in")
    if not isinstance(opts, list) or len(opts) != N_OPTIONS or not all(isinstance(o, str) and o.strip() for o in opts):
        return p + [f"need exactly {N_OPTIONS} non-empty options"]
    texts = [o.strip() for o in opts]
    if len({norm(t) for t in texts}) != N_OPTIONS:
        p.append("duplicate options")
    k = d.get("key_index")
    if not isinstance(k, int) or isinstance(k, bool) or not 0 <= k < N_OPTIONS:
        return p + ["key_index must be 0-3"]
    for t in texts:
        if len(t.split()) > MAX_OPTION_WORDS:
            p.append("option too long")
            break
    for t in texts:
        if BANNED_OPTIONS.search(t):
            p.append("'none/all of the above' style option")
        if ABSOLUTE.search(t) or VAGUE.search(t):
            p.append(f"absolute or vague term in option: {t[:40]}")
    lens = sorted(len(t) for i, t in enumerate(texts) if i != k)
    if lens and len(texts[k]) > 1.5 * lens[len(lens) // 2] + 8:
        p.append("the key is noticeably longer than the other options (NBME flaw)")
    stem_words = {w for w in words(stem + " " + lead) if len(w) >= 6}
    key_words = {w for w in words(texts[k]) if len(w) >= 6}
    others = set().union(*[{w for w in words(t) if len(w) >= 6} for i, t in enumerate(texts) if i != k])
    if key_words & stem_words and not (key_words & stem_words) <= others:
        p.append("clang clue: the word(s) " + ", ".join(sorted((key_words & stem_words) - others)) + " appear in the stem and in the correct option only; "
                 "reword the lead-in so it does not use them (or give the other options the same word)")
    kw = set(words(texts[k]))
    shared = [len(kw & set(words(t))) for i, t in enumerate(texts) if i != k]
    own = [sum(len(set(words(t)) & set(words(u))) for j, u in enumerate(texts) if j != i) for i, t in enumerate(texts)]
    if len(kw) > 1 and own[k] == max(own) and own.count(max(own)) == 1 and max(own) >= 3 and all(s >= 1 for s in shared):
        p.append("the key shares the most words with the other options (convergence)")
    if not (d.get("explanation") or "").strip():
        p.append("no explanation")
    check_support("key", d.get("key_support"), evidence, p)
    check_support("explanation", d.get("explanation_support"), evidence, p)
    alts = d.get("alternatives")
    want = {i for i in range(N_OPTIONS) if i != k}
    got = {a.get("index") for a in alts if isinstance(a, dict)} if isinstance(alts, list) else set()
    if got != want or (isinstance(alts, list) and len(alts) != len(want)):
        p.append("every alternative needs exactly one reason it fails")
    else:
        for a in alts:
            if not (a.get("why_wrong") or "").strip():
                p.append(f"alternative {a['index']}: empty reason")
            elif ABSENCE.search(a["why_wrong"]):
                p.append(f"alternative {a['index']}: the reason rests on the passages not mentioning something; cite a span that STATES the true fact instead")
            check_support(f"alternative {a['index']}", a.get("support"), evidence, p)
    return p


def freeze(d, evidence, rng=None, scope=None, tiers=None):
    """A validated draft -> the frozen private item: options shuffled, ids assigned, keys and mappings fixed, evidence copied."""
    rng = rng or random.SystemRandom()
    order = list(range(N_OPTIONS))
    rng.shuffle(order)
    ids = {old: IDS[new] for new, old in enumerate(order)}
    options = [{"id": IDS[new], "text": d["options"][old].strip()} for new, old in enumerate(order)]
    key_id = ids[d["key_index"]]
    cited = {sp["source_id"] for part in (d["key_support"], d["explanation_support"], *[a["support"] for a in d["alternatives"]]) for sp in part}
    ev = {sid: dict(evidence[sid]) for sid in cited}
    return {"item_id": item_hash(d["stem"], d["lead_in"], [o["text"] for o in options], d["options"][d["key_index"]]),
            "selection_mode": "single", "stem": d["stem"].strip(), "lead_in": d["lead_in"].strip(), "options": options,
            "answer_ids": [key_id], "explanation": d["explanation"].strip(),
            "key_support": [dict(s) for s in d["key_support"]], "explanation_support": [dict(s) for s in d["explanation_support"]],
            "alternatives": {ids[a["index"]]: {"why_wrong": a["why_wrong"].strip(), "support": [dict(s) for s in a["support"]]} for a in d["alternatives"]},
            "objective": (d.get("objective") or "").strip(), "evidence": ev,
            "tiers": sorted(tiers or {e["tier"] for e in ev.values()}), "scope": scope or {}, "checks": {},
            "review": {"status": "unreviewed"}, "created": time.time(), "version": QUIZ_VERSION}


def public_view(item):
    """What a student may see BEFORE submitting: the question and the options. No key, no explanation, no evidence, no source."""
    return {"stem": item["stem"], "lead_in": item["lead_in"], "selection_mode": item["selection_mode"],
            "options": [{"id": o["id"], "text": o["text"]} for o in item["options"]]}


def score(item, selected):
    """Single or multiple answer: correct only when the selected set equals the key set. -> bool"""
    return sorted(selected or []) == sorted(item["answer_ids"])
