"""The cadaver's body type, and how it is allowed to change an answer.

Two spellings reach the code:
  * Ask (chat): "<more|average|less> fat, <more|average|less> muscle, <large|average|small> build" (docs/api_contract.md);
  * Guide:      lean | average | more_fat | more_muscular | not_sure (saved per guide in the student's guide history).
`describe()` turns either into plain words for the model ("more body fat"), or "" when there is nothing to adapt to (average, not sure,
nothing chosen). Only LAB answers (the ordered-steps answer, a guide station's note, a guide check) use it; a concept answer ignores it.
"""
import re

GUIDE_CHOICES = ("lean", "average", "more_fat", "more_muscular", "not_sure")
_GUIDE_WORDS = {"lean": "lean (less body fat)", "more_fat": "more body fat", "more_muscular": "more muscular (more muscle bulk)"}
ASK_RE = re.compile(r"^(more|average|less) fat, (more|average|less) muscle, (large|average|small) build$")
TIP_LABEL = "General tip, not from your notes"

BODY_RULE = f"""Cadaver body type: <session> gives it (for example "more body fat"). This is a LAB answer, so adapt the guidance to it, using only what the sources \\
say. After the steps add, at most: (1) ONE line starting "For this body type:" that points to the step or slide where a source mentions fat, superficial fascia, \\
muscle bulk or depth, says how that applies to this body type, and cites it; write it ONLY if a source really mentions one of those. (2) Up to TWO short lines, each \\
starting exactly "{TIP_LABEL}:", giving only the usual direction: more body fat = more fat and thicker superficial fascia to clear before structures appear, and \\
structures may lie deeper; more muscular = bulkier muscles, and structures may lie deeper between them; lean = less fat to clear, and structures may lie nearer the \\
surface. A general tip has no citation. Never state a clinical consequence, a measurement, a new step, cut or landmark, or anything a source contradicts. If no source \\
mentions fat, fascia, muscle or depth, give only the general tips. For a body type that is average or not given, add none of these lines."""


def describe(value):
    """-> plain words for the model, or "" (nothing to adapt to)."""
    v = (value or "").strip()
    if v in _GUIDE_WORDS:
        return _GUIDE_WORDS[v]
    m = ASK_RE.match(v)
    if not m:
        return ""
    fat, muscle, build = m.groups()
    parts = [f"{fat} body fat" if fat != "average" else "", f"{muscle} muscle" if muscle != "average" else "", f"{build} build" if build != "average" else ""]
    return ", ".join(p for p in parts if p)


def is_active(value):
    return bool(describe(value))
