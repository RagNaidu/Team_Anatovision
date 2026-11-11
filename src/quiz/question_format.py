"""The shape of a quiz question, in ONE place.

Dr. Inglis will send sample questions. When they arrive, change the values below (and the wording of ITEM_RULES) and bump
items.QUIZ_VERSION so older saved items are not reused. Nothing else needs to change: items.py (the local checks), generate.py (the writer's
prompt) and the labels shown to students all read this file.
"""
import re

N_OPTIONS = 4                       # options per question
IDS = "ABCDE"                       # option ids (the first N_OPTIONS are used)
MAX_STEM = 700                      # characters of the (optional) stem
MAX_OPTION_WORDS = 14               # words per option
MIN_SPAN_CHARS = 20                 # a supporting span copied from the evidence: at least this long ...
MIN_SPAN_WORDS = 4                  # ... and this many words
LEAD_START = re.compile(r"^(which|what|where|how many|how)\b", re.I)           # the lead-in is ONE closed question starting like this
BANNED_OPTIONS = re.compile(r"\b(none of the above|all of the above|both [a-e] and [a-e]|a and b|b and c)\b", re.I)
VAGUE = re.compile(r"\b(usually|often|frequently|generally|typically|commonly|may|might|could be|is associated with|is important|is useful for|sometimes)\b", re.I)
ABSOLUTE = re.compile(r"\b(always|never|only|all|none|every|completely|entirely)\b", re.I)
NEGATIVE = re.compile(r"\b(except|not true|which is false|least likely|incorrect)\b|\bNOT\b")

# What a student is told about where a question's facts come from
WEB_LABEL = "Not from course notes"                 # on every question built from the web
WEB_SOURCE_NAME = "Wikipedia"                       # the only approved web source
WEB_LICENSE = "CC BY-SA 4.0"                        # Wikipedia's licence, shown beside the source

# The writer's item rules (the NBME-style paragraph of the drafting prompt)
ITEM_RULES = (
    "Item rules (NBME): test one important point from the primary passage; the lead-in is ONE closed question (start with Which/What/Where/How) that a "
    "knowledgeable student could answer with the options covered; exactly {n_options} options, all answers of the SAME KIND to the lead-in (all structures, or all "
    "locations, or all functions: never a mixture of, say, a muscle, a space and a bony site), similar length and wording, all plausible; the key not "
    "longer or more complete than the others; no word of the stem repeated only in the key; no \"none/all of the above\", no negative stem (EXCEPT, NOT), "
    "no always/never/only/all in options, no vague words (usually, often, may, associated with). The stem may be empty or a short context sentence "
    "drawn from the passages: invent no clinical story, patient or number. Options must be short (at most {max_option_words} words).")


def item_rules():
    return ITEM_RULES.format(n_options=N_OPTIONS, max_option_words=MAX_OPTION_WORDS)


def web_license(raw):
    """'Wikipedia, CC BY-SA 4.0' -> 'CC BY-SA 4.0'."""
    return re.sub(r"^Wikipedia,\s*", "", raw or "") or WEB_LICENSE
