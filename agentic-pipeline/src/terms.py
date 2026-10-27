"""Small word helpers shared by the term lookup and the web fallback.

meaningful_words("What is the apex?") -> ["apex"]     (question words, filler and stopwords removed)
stem("trochanters") -> "trochanter"                   (a crude plural stripper, for matching only)
"""
import re

from src.retrieval.index import STOPWORDS

FILLER = set("""define definition meaning mean means explain tell describe give show term called call anatomy anatomical
structure structures please know find need info information about me us tell can could would should will""".split())


def tokens(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def stem(w):
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith("ses"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def meaningful_words(text):
    """The words of a question that carry its meaning, in order, without repeats."""
    out = []
    for t in tokens(text):
        if t in STOPWORDS or t in FILLER or len(t) < 2 or t in out:
            continue
        out.append(t)
    return out


def stems_of(words):
    return [stem(w) for w in words]


def stem_set(text):
    return {stem(t) for t in tokens(text)}
