"""Keyword / term lookup: a bare term ("apex", "what is thenar?", "nerve supply") is not a full question, so the 0.68 relevance
rule (made for full questions) must not refuse it, and the student must not be asked "apex of what?".

decide(searcher, query, allowed_lectures) -> Decision
    use = "term"            answer with a term lookup: the places the term appears, grouped by section
          "normal"          not a bare term, or it appears in one place / is itself a section heading: the ordinary answer
          "term_if_missing" ordinary answer first; if that finds nothing, fall back to the term lookup (one matching place)
    hits, n_groups, words   the word-for-word matches (up to 6 sections), the number of matching sections, the key words

A bare term = 4 or fewer meaningful words, in the form of a term and not of a question ("what is X", "X", "define X"; not
"what are the walls of X"). It must appear word-for-word (all its words, plural or singular) in text the user may access
(notes, dissection guides, OpenStax). A term that appears nowhere gets use = "normal", so the ordinary refusal stands.
"""
from dataclasses import dataclass, field

from src import terms

MAX_WORDS = 4
MAX_GROUPS = 6
TERM_CLOSING = "Ask about a specific one for more detail."
BARE_OK = {"what", "whats", "is", "are", "the", "a", "an", "does", "please", "define"}


@dataclass
class Decision:
    use: str = "normal"
    hits: list = field(default_factory=list)
    n_groups: int = 0
    words: list = field(default_factory=list)
    why: str = ""


def is_bare(query):
    """True for the form of a term: every word is a meaningful word, filler ('define', 'meaning') or 'what is the'."""
    words = terms.meaningful_words(query)
    if not words or len(words) > MAX_WORDS:
        return False
    ok = set(words) | terms.FILLER | BARE_OK
    return all(t in ok for t in terms.tokens(query))


def _leaf_words(chunk):
    return terms.stems_of(terms.meaningful_words(chunk["breadcrumb"].split(" > ")[-1]))


def named_by_heading(words, chunks):
    """Exactly one matched section whose own heading contains the whole term (for example 'Sartorius', 'Femoral Triangle'): that is a question about
    that section, so it gets the ordinary answer."""
    want = set(terms.stems_of(words))
    named = [c for c in chunks if want <= set(_leaf_words(c))]
    return len({(c["lecture"], c["breadcrumb"]) for c in named}) == 1


def decide(searcher, query, allowed_lectures=None):
    words = terms.meaningful_words(query)
    keyword_groups = getattr(searcher, "keyword_groups", None)
    if not keyword_groups or not is_bare(query):
        return Decision("normal", words=words, why="not a bare term")
    found = keyword_groups(words, allowed_lectures, MAX_GROUPS)
    hits, n = found["hits"], found["n_groups"]
    n_course = found.get("n_course", n)
    if n == 0:
        return Decision("normal", words=words, why="the term appears nowhere the user may read")
    if n_course <= 1:       # one place in Dr. Inglis's material (or only the textbook): the ordinary answer is the better one
        return Decision("term_if_missing", hits, n, words, "the term appears in at most one place in the course material")
    if named_by_heading(words, found.get("all", [h.chunk for h in hits])):
        return Decision("normal", hits, n, words, "the term is the heading of one section")
    return Decision("term", hits, n, words, f"the term appears in {n_course} places in the course material")
