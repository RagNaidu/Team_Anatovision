"""Small shared files for the UI: settings (spending cap, defaults) and the question/usage log.

  data/settings.json       {"spending_cap_usd": 2.0, "default_brief": true}
  data/question_log.jsonl  one line per question or guide step: who, what, how it was answered, cost, and a `kind`:
                             chat_answer       a student's Q&A question
                             guide_step        a student's Guide description check
                             guide_peek        a student pressed "Show the notes" before describing (no model call)
                             professor_preview a question or Guide step a professor ran while previewing as a student
                             factcheck         a paid fact-check run by the professor
                           Preview and fact-check lines are never counted as student usage.
                           Questions the notes could not answer (answered_from_notes == false) show the gaps in the notes.
Both are plain local files. Student questions are stored here: see README for the privacy note.
"""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT / "data" / "settings.json"
QUESTION_LOG_PATH = ROOT / "data" / "question_log.jsonl"
DEFAULT_SETTINGS = {"spending_cap_usd": 2.0, "default_brief": True}


def load_settings():
    try:
        saved = json.loads(Path(SETTINGS_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {**DEFAULT_SETTINGS, **{k: v for k, v in saved.items() if k in DEFAULT_SETTINGS}}


def save_settings(**changes):
    settings = {**load_settings(), **{k: v for k, v in changes.items() if k in DEFAULT_SETTINGS}}
    if not (isinstance(settings["spending_cap_usd"], (int, float)) and settings["spending_cap_usd"] >= 0):
        raise ValueError("the spending cap must be a number of dollars, 0 or more")
    Path(SETTINGS_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(SETTINGS_PATH).write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return settings


def log_event(entry):
    """Append one line to the question log (never raises: logging must not break an answer)."""
    entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    try:
        Path(QUESTION_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        with Path(QUESTION_LOG_PATH).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_log():
    path = Path(QUESTION_LOG_PATH)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


KINDS = ("chat_answer", "guide_step", "guide_peek", "professor_preview", "factcheck")


def kind_of(entry):
    """The kind of a log line. Lines written before `kind` existed are classified from `mode`; a preview used to be logged
    with the user name 'preview'."""
    if entry.get("kind") in KINDS:
        return entry["kind"]
    if entry.get("mode") == "factcheck":
        return "factcheck"
    if entry.get("user") == "preview":
        return "professor_preview"
    return "guide_step" if entry.get("mode") == "guide" else "chat_answer"


def summary(entries=None):
    """-> counts and costs split by kind, so chat answers, Guide steps and professor previews are never mixed:
      chat       {questions, cost, top_lectures, unanswered, web (answers from the trusted web), term (term lookups)}   students' Q&A
      guide      {steps, cost}                                    students' Guide checks
      preview    {questions, guide_steps, cost}                   professor previews (not student usage)
      factcheck  {runs, cost}
      cost_total, cost_by_day (all kinds), cost_today helper keys
    """
    entries = read_log() if entries is None else entries
    by_kind = {k: [e for e in entries if kind_of(e) == k] for k in KINDS}
    cost = lambda es: sum(e.get("cost") or 0.0 for e in es)
    by_day = Counter()
    for e in entries:
        by_day[e["ts"][:10]] += e.get("cost") or 0.0
    by_day_kind = {}
    for e in entries:
        k = {"chat_answer": "Student chat", "guide_step": "Student Guide", "guide_peek": "Student Guide", "professor_preview": "Professor preview",
             "factcheck": "Fact-check"}[kind_of(e)]
        day = by_day_kind.setdefault(e["ts"][:10], {})
        day[k] = day.get(k, 0.0) + (e.get("cost") or 0.0)
    chat, preview = by_kind["chat_answer"], by_kind["professor_preview"]
    return {
        "chat": {"questions": len(chat), "cost": cost(chat),
                 "web": [e for e in chat if e.get("web")], "term": sum(e.get("answer_mode") == "term" for e in chat),
                 "top_lectures": Counter(lec for e in chat for lec in e.get("lectures", [])).most_common(10),
                 "unanswered": [e for e in chat if not e.get("answered_from_notes")]},
        "guide": {"steps": len(by_kind["guide_step"]), "cost": cost(by_kind["guide_step"]), "peeks": len(by_kind["guide_peek"])},
        "preview": {"questions": sum(e.get("mode") == "qa" for e in preview),
                    "guide_steps": sum(e.get("mode") == "guide" for e in preview), "cost": cost(preview)},
        "factcheck": {"runs": len(by_kind["factcheck"]), "cost": cost(by_kind["factcheck"])},
        "cost_total": cost(entries), "cost_by_day": dict(sorted(by_day.items())), "cost_by_day_kind": dict(sorted(by_day_kind.items())),
    }
