"""A student's 'Report an error' on an answer. It goes to data/flags.jsonl through the existing flags function (qa.append_flag),
as an open flag of type student_report, for Dr. Inglis. Nothing is read back: a student never sees any flag, including their own."""
from datetime import datetime, timezone

from src.modes import qa

REASONS = ("The answer is wrong", "The answer does not match the notes", "A citation points to the wrong place",
           "Something important is missing", "Something else")
MAX_COMMENT = 500


def report_error(username, question, answer_text, cites, reason, comment="", web_urls=()):
    """-> True if written. Raises ValueError for a reason that is not on the list."""
    if reason not in REASONS:
        raise ValueError("Choose a reason from the list.")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry = {"type": "student_report", "student": username, "question": (question or "")[:600], "answer": (answer_text or "")[:1500],
             "cites": list(cites)[:12], "reason": reason, "comment": (comment or "").strip()[:MAX_COMMENT]}
    if web_urls:
        entry.update(web=True, web_urls=list(web_urls)[:6])          # an answer from the trusted web: Dr. Inglis sees which pages
    return qa.append_flag(entry, key=f"student_report|{username}|{now}|{hash((question, answer_text)) & 0xffffff:x}")
