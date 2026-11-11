"""Question handling that happens before and around the search: follow-ups, list questions, off-topic check.

  recent_turns(messages)          the last 2-3 turns (question + short answer) for follow-up context
  rewrite_query(...)              "what about the inferior one?" -> a self-contained search query (small, cheap model)
  is_list_question(q)             "what are the boundaries of ...", "list ...", "name all ..." -> retrieve more passages
  is_anatomy_question(...)        only used when nothing was found: anatomy topic missing from the notes, or not anatomy?

The history is context for understanding a follow-up. It is never a source: citations still come only from the passages
retrieved for the current question.
"""
import os
import re

from src import llm, ttlcache
from src.modes import qa
MAX_TURNS = 3
THINK_ROOM = 400       # extra tokens for models that write reasoning before the answer (GLM); the reply is still one line
ANSWER_CHARS = 280
LIST_K = 12            # passages retrieved for a list/contents question (otherwise 5)

LIST_RE = re.compile(
    r"^\s*(list|name|enumerate|give me (?:a |the )?list|what are all)\b"
    r"|\b(?:list|name|enumerate) (?:all|the|every)\b"
    r"|\b(?:boundar(?:y|ies)|borders?|contents?|walls?|branches|tributaries|relations|attachments|divisions|"
    r"components|parts|layers|tributary)\s+(?:of|in)\b"
    r"|\bwhat(?:'s| is| are) (?:in|inside|contained in)\b"
    r"|\ball (?:of )?the\b", re.I)

REWRITE_SYSTEM = (
    "You turn a student's follow-up question into ONE self-contained search query for a search over anatomy lecture notes. "
    "Use the earlier turns only to fill in what the follow-up refers to (for example 'the inferior one', 'its contents', "
    "'and the other nerve?'). Output ONLY the query: one line, under 30 words, no quotes, no explanation. If the question is "
    "already self-contained, output it unchanged. Never answer the question.")
PROC_RE = re.compile(
    r"\bhow (?:do|can|should|would|to|did) (?:i|we|you|one)?\b|\bhow to\b|\bsteps?\b|\bprocedure\b|\bwhat (?:do|should) i do\b|"
    r"\b(?:reflect|incis\w+|cut|cutting|remove|removing|expose|exposing|dissect\w*|detach|transect|section|open|split|saw|"
    r"identify|find|locate|clean|cleaning)\s+(?:the|a|an|your|it|them|this|that)\b|\bwhere (?:do|should) i (?:cut|start|begin|make)\b", re.I)
PROC_K = 8             # passages retrieved for a "how do I ..." question (steps often span several slides)
ANATOMY_SYSTEM = ("Answer with exactly one word, YES or NO. Is the message a question about human anatomy, physiology, "
                  "dissection or an anatomy lab (clinical anatomy counts)?")


SCOPE_SYSTEM = ("Answer with exactly one word: ANATOMY, CLINICAL or OTHER. ANATOMY = a question about human anatomy, physiology, "
                "dissection or an anatomy lab (what an injury to a structure causes counts), or a bare anatomical term or structure name "
                "such as 'tegmen tympani'. CLINICAL = a request to DO something "
                "clinically: treatment, medication or dosing, how to diagnose, work up or manage a condition. OTHER = anything "
                "else (a drug or product name on its own, non-medical topics, small talk).")


CLINICAL_RE = re.compile(r"\b(?:treat|cure|medicat|dose|dosing|diagnos|prescrib|heal|therap|manage)\w*", re.I)


EXPLAIN_RE = re.compile(
    r"\bexplain\b|\bsimplif\w*|\b(?:in|using)\s+(?:simple|simpler|plain|easy|easier|everyday|layman'?s?)\s+(?:words?|terms?|language|english)\b|"
    r"\b(?:more\s+)?simpl(?:y|er)\b|\bwhat\s+(?:does|do)\s+(?:this|that|it|these|those)\s+mean\b|\bwhat(?:'s| is)\s+(?:this|that)\s+(?:saying|about)\b|"
    r"\bbreak\s+(?:this|it|that)\s+down\b|\bin\s+(?:a\s+)?nutshell\b|\beli5\b|\bput\s+(?:this|it|that)\s+(?:simply|in)\b", re.I)
EXPLAIN_FRAME = 200      # characters at the start and the end of a message that carry the student's own words (the middle may be pasted guide text)


LAB_INTENT_RE = re.compile(r"\bhow (?:do|can|should|would|did) (?:i|we)\b|\bhow to\b|\bwhere (?:do|should|can) (?:i|we)\b|\bwhat (?:do|should) i do\b|"
                           r"\b(?:steps?|procedure)\b|\bwhich station\b|\bstation \d+\b", re.I)


def own_words(question):
    """The student's own framing of a message that may contain pasted text: the part before the first colon or line break, and the last line."""
    q = (question or "").strip()
    head = re.split(r"[:\n]", q, maxsplit=1)[0][:EXPLAIN_FRAME]
    tail = q.rsplit("\n", 1)[-1][-EXPLAIN_FRAME:] if "\n" in q else ""
    return f"{head} {tail}"


def is_explain_question(question):
    """'Explain this more simply: <pasted guide steps>', 'what does this mean', 'in simple words': the student wants the CONCEPT in plain language,
    not the lab steps. Only the student's own framing counts (the start and end of the message), so pasted text cannot trigger or hide it."""
    q = (question or "").strip()
    frame = q if len(q) <= 2 * EXPLAIN_FRAME else q[:EXPLAIN_FRAME] + " " + q[-EXPLAIN_FRAME:]
    return bool(EXPLAIN_RE.search(frame)) and not CLINICAL_RE.search(frame)


def is_procedural_question(question):
    """'How do I reflect the skin over the thigh?', 'what are the steps ...', 'where do I cut ...': the student wants the lab steps.
    A question about treating or diagnosing something is never a lab-step question, and neither is a request to EXPLAIN something simply,
    even when the pasted text is full of lab verbs ('identify the ...', 'reflect the ...')."""
    q = question or ""
    if is_explain_question(q) and not LAB_INTENT_RE.search(own_words(q)):
        return False
    return bool(PROC_RE.search(q)) and not CLINICAL_RE.search(q)


def is_list_question(question):
    return bool(LIST_RE.search(question or ""))


def short_answer(text, limit=ANSWER_CHARS):
    """An earlier answer, cut down for context: no [citations], no closing line, at most `limit` characters."""
    text = re.sub(r"\[[^\[\]]*\]", "", text or "")
    text = text.replace(qa.BRIEF_CLOSING, "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + " ..."


def recent_turns(messages, n=MAX_TURNS):
    """messages: the chat so far [{"role": "user", "text"} | {"role": "assistant", "result": {...}}].
    -> up to n of the latest ANSWERED turns, oldest first: [{"question", "answer"}]."""
    turns, question = [], None
    for m in messages:
        if m["role"] == "user":
            question = m["text"]
        elif question is not None and m.get("result", {}).get("status") == "answered":
            turns.append({"question": question, "answer": short_answer(m["result"]["answer_text"])})
            question = None
        else:
            question = None
    return turns[-n:]




def fallback_query(question, history):
    """If the rewrite is unavailable: the previous question followed by the follow-up (the retrieval still sees both)."""
    return f"{history[-1]['question']} {question}"[:300] if history else question


_REWRITE_CACHE = ttlcache.TTLCache()


def rewrite_query(client, question, history, model=None):
    """-> (query, usage, how). how = 'rewritten' | 'unchanged' | 'fallback' (the model call failed or gave nonsense)."""
    if not history:
        return question, {"input_tokens": 0, "output_tokens": 0}, "unchanged"
    turns = "\n".join(f"Student asked: {t['question']}\nAnswer given: {t['answer']}" for t in history)
    user = f"<earlier_turns>\n{turns}\n</earlier_turns>\n<follow_up>{question}</follow_up>"
    cache_key = ttlcache.key_of(model, REWRITE_SYSTEM, user)
    cached = _REWRITE_CACHE.get(cache_key)
    try:
        if cached is not None:                          # the same follow-up in the same chat a moment ago: same rewrite, no model call
            query, usage = cached, {"input_tokens": 0, "output_tokens": 0}
        else:
            res = llm.complete(client, REWRITE_SYSTEM, [{"role": "user", "content": user}], 120 + THINK_ROOM, model)
            query = llm.clean_text(res.text)
            usage = res.usage
            if query and "\n" not in query and len(query) <= 240:
                _REWRITE_CACHE.put(cache_key, query)
    except Exception:                                  # any failure: search with both questions instead
        return fallback_query(question, history), {"input_tokens": 0, "output_tokens": 0}, "fallback"
    if not query or "\n" in query or len(query) > 240:
        return fallback_query(question, history), usage, "fallback"
    return query, usage, ("unchanged" if query.lower() == question.lower() else "rewritten")


def is_anatomy_question(client, question, model=None):
    """-> (bool, usage). Defaults to True (treat it as an anatomy question) if the check fails."""
    try:
        res = llm.complete(client, ANATOMY_SYSTEM, [{"role": "user", "content": question}], 5 + THINK_ROOM, model)
        return not llm.clean_text(res.text).upper().startswith("NO"), res.usage
    except Exception:
        return True, {"input_tokens": 0, "output_tokens": 0}


def scope_check(client, question, model=None):
    """-> (label, usage, sure). label: 'anatomy' | 'clinical_advice' | 'not_anatomy'. `sure` is False when the check failed
    or gave an unreadable reply: the label is then 'anatomy' (as is_anatomy_question defaults), but the web fallback, which
    must only run for a clear anatomy question, treats an unsure result as 'do not search'."""
    try:
        res = llm.complete(client, SCOPE_SYSTEM, [{"role": "user", "content": question}], 5 + THINK_ROOM, model)
        word = llm.clean_text(res.text).upper().split()[0].strip(".,:;") if llm.clean_text(res.text) else ""
    except Exception:
        return "anatomy", {"input_tokens": 0, "output_tokens": 0}, False
    label = {"ANATOMY": "anatomy", "CLINICAL": "clinical_advice", "OTHER": "not_anatomy",
             "YES": "anatomy", "NO": "not_anatomy"}.get(word)
    return (label or "anatomy"), res.usage, label is not None


COVERAGE_SYSTEM = ("You check whether some passages answer a student's question. Reply with ONE JSON object: "
                   '{"covered": true|false, "missing": ["each part of the question the passages do not answer"]}. '
                   "Split the question into its parts (for example 'boundaries' and 'contents'). covered is true only if the passages state "
                   "an answer for EVERY part; a passage that only mentions the structure in passing does not answer a part. "
                   "Name each missing part in a few words.")
COVERAGE_SCHEMA = {"type": "object", "properties": {"covered": {"type": "boolean"}, "missing": {"type": "array", "items": {"type": "string"}}},
                   "required": ["covered", "missing"], "additionalProperties": False}


def coverage_check(client, question, passages, model=None):
    """Does the retrieved text answer every part of the question? -> (covered, missing_parts, usage, sure).
    sure is False when the call failed: the caller then treats the text as covering the question (no extra fetch)."""
    body = "\n\n".join(f"PASSAGE {i}:\n{p[:1100]}" for i, p in enumerate(passages, 1))
    try:
        data, usage = llm.complete_json(client, COVERAGE_SYSTEM, [{"role": "user", "content": f"QUESTION: {question}\n\n{body}"}],
                                        400 + 3 * THINK_ROOM, COVERAGE_SCHEMA, model)
    except Exception:
        return True, [], {"input_tokens": 0, "output_tokens": 0}, False
    missing = [m.strip() for m in data.get("missing", []) if m.strip()]
    return (bool(data.get("covered")) and not missing), missing, usage, True
