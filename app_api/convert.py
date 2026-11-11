"""Student-safe answer views (src/student_view.py) -> the contract's Message and Source objects.

Nothing is added here that the student view does not already contain: this module only renames, reorders and writes the markdown.
The [n] markers in the markdown are the citation numbers of the student view, and Source.n is the same number.

A line the fact-check doubts or Dr. Inglis corrected keeps its small note as an italic sentence under the line (the contract has no
field for it), and a withheld line shows only the neutral sentence, exactly as in the Streamlit app.
"""
import re
from datetime import datetime, timezone

from app_api import catalog
from src import student_view as sv

BULLET = re.compile(r"^\s*[-*•]\s+")
NUMBERED = re.compile(r"^\s*\d+[.)]\s+")
OPENSTAX_LICENSE = "CC BY-NC-SA 4.0"
WIKIPEDIA_LICENSE = "CC BY-SA 4.0"
REFUSED_REASONS = ("clinical_advice", "not_anatomy")


def iso(ts):
    """A POSIX time (or an ISO string) -> '2026-10-20T14:03:11Z'."""
    if ts is None or ts == "":
        return None
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return ts
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def kind_of(view):
    """answer | term_lookup | not_covered | refused | error, from the student view's status and reason."""
    status, reason = view["status"], view.get("reason", "")
    if status in ("error", "capped"):
        return "error"
    if reason in REFUSED_REASONS:
        return "refused"
    if status in ("not_found", "out_of_scope"):
        return "not_covered"
    if status == "access_limited" and not view["sources"]:
        return "not_covered"
    return "term_lookup" if view.get("term") else "answer"


def _segments(blocks):
    """Consecutive bullets (or numbered steps) form one markdown list; anything else is its own paragraph."""
    out = []
    for b in blocks:
        kind = "bullet" if BULLET.match(b["text"]) else "num" if NUMBERED.match(b["text"]) else "para"
        if out and kind != "para" and out[-1][0] == kind:
            out[-1][1].append(b)
        else:
            out.append((kind, [b]))
    return out


def _status_note(block):
    """The small note a flagged line carries, as a sentence (never the reason, severity or any fact-check wording)."""
    kinds = {s["kind"] for s in block["status"]}
    notes = []
    if "check" in kinds:
        notes.append(sv.CHECK_SENTENCE)
    if "corrected" in kinds:
        notes.append(next((s["label"] + "." for s in block["status"] if s["kind"] == "corrected"), "Dr. Inglis corrected this line."))
    if "reviewing" in kinds and sv.NEUTRAL_REVIEW not in block["text"]:
        notes.append(sv.NEUTRAL_REVIEW)
    return notes


def markdown_of(view, valid):
    """The answer text with [n] markers. valid = the source numbers that exist (a marker with no source is never printed)."""
    if not view["blocks"]:
        return view["answer_text"]
    parts = []
    for kind, blocks in _segments(view["blocks"]):
        lines = []
        for b in blocks:
            if b.get("note"):
                lines.append(f"*{b['text']}*")
                continue
            line = b["text"] + "".join(f" [{n}]" for n in b["markers"] if n in valid)
            for note in _status_note(b):
                line += f"\n\n*{note}*" if kind == "para" else f" *{note}*"
            lines.append(line)
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _lecture_label(title):
    return title.replace(" - ", ", ", 1)


def _lecture_id(title):
    return catalog.lecture_id_for_title(title) if title else None


def licence_of(text, default=None):
    """'Wikipedia, CC BY-SA 4.0' -> 'CC BY-SA 4.0'."""
    m = re.search(r"CC[ -][A-Z][A-Z-]*(?: [\d.]+)?", text or "")
    return m.group(0).replace("CC-", "CC ") if m else default


def source_of(n, src):
    """One retrieved passage of the student view -> Source."""
    t, text = src["source_type"], src["text"]
    if t == "open_text":
        entry = sv.source_entry(src)
        number = src.get("section_number")
        return dict(n=n, type="openstax", title="OpenStax Anatomy & Physiology 2e, " + (f"section {number}" if number else "textbook"),
                    subtitle=(src.get("crumb") or src["breadcrumb"].split(" > ")[-1]), lecture_id=None, url=entry["url"] or None,
                    snippet=text, retrieved_at=None, license=OPENSTAX_LICENSE)
    if t == "web":
        wiki = src.get("site") == "Wikipedia"
        title = re.sub(r"^MeSH:\s*", "", src.get("title") or "")
        return dict(n=n, type="wikipedia" if wiki else "web", title=f"{src.get('site') or 'Web'}: {title}".strip(": "),
                    subtitle=src.get("site") or "Web", lecture_id=None, url=src.get("source_url") or None, snippet=text,
                    retrieved_at=src.get("retrieved") or None, license=licence_of(src.get("license"), WIKIPEDIA_LICENSE if wiki else None))
    if t == "dissection_guide":
        return dict(n=n, type="guide", title="Dissection guide", subtitle=src["crumb"], lecture_id=_lecture_id(src["lecture"]),
                    url=None, snippet=text, retrieved_at=None, license=None)
    section = (src.get("crumb") or "").split(" › ")[-1]
    topic = src["lecture"].split(" - ", 1)[-1]
    tail = f" › {section}" if section and section != topic else ""
    earlier = " (Earlier version, not in revised notes)" if src.get("superseded") else ""
    return dict(n=n, type="notes", title="Lecture notes", subtitle=_lecture_label(src["lecture"]) + tail + earlier, lecture_id=_lecture_id(src["lecture"]),
                url=None, snippet=text, retrieved_at=None, license=None)


def fix_source(n, fix):
    return dict(n=n, type="verified_fix", title="Verified correction", subtitle=f"{fix['by']}, {fix['date']}",
                lecture_id=_lecture_id(fix.get("lecture", "")), url=None, snippet=fix["correction"], retrieved_at=None, license=None)


def sources_of(view, current=None):
    """current: a src.revision_status.CurrentIndex when an OLD answer is shown again (its sources may have changed since)."""
    out = []
    for e in view["sources_list"]:
        if e["fix"] is not None:
            out.append(fix_source(e["n"], view["fixes"][e["fix"]]))
        elif e["chunk"] is not None:
            src = view["sources"][e["chunk"]]
            s = source_of(e["n"], src)
            if current is not None and (rev := current.status(src)):
                s["revision"] = rev
            out.append(s)
    return out


def footer_of(view):
    basis, note = view.get("footer") or None, view.get("notice") or None
    return {"basis_line": basis, "access_note": note} if (basis or note) else None


_NO_IMAGES = object()


def assistant_message(view, *, id, created, timing_ms=0, current=None, allowed=_NO_IMAGES):
    """The student view of an answer -> Message. allowed: the student's grants (list) or None; when given, guide slide images the student may open are attached."""
    kind = kind_of(view)
    has_text = kind in ("answer", "term_lookup")
    sources = sources_of(view, current) if has_text else []
    markdown = markdown_of(view, {s["n"] for s in sources}) if has_text else view["answer_text"]
    images = []
    if has_text and allowed is not _NO_IMAGES:
        from app_api import guide_media
        try:
            images = guide_media.chat_images(view, markdown, allowed)
        except Exception:                              # an image card is never worth failing an answer
            images = []
    return {"id": id, "role": "assistant", "created_at": iso(created), "kind": kind, "markdown": markdown, "sources": sources,
            "footer": footer_of(view) if kind in ("answer", "term_lookup", "not_covered") else None, "timing_ms": int(timing_ms or 0), "images": images}


def user_message(text, *, id, created):
    return {"id": id, "role": "user", "created_at": iso(created), "kind": "answer", "markdown": text, "sources": [], "footer": None, "timing_ms": 0}


def message_id(chat_id, seq):
    return f"{chat_id}:{seq}"


def parse_message_id(mid):
    chat_id, _, seq = mid.rpartition(":")
    return (chat_id, int(seq)) if chat_id and seq.isdigit() else (None, None)


def chat_messages(chat, current=None, allowed=_NO_IMAGES):
    """get_chat_rows(...) -> [Message]. current: see sources_of. allowed: see assistant_message."""
    out = []
    for m in chat["messages"]:
        mid = message_id(chat["id"], m["seq"])
        if m["role"] == "user":
            out.append(user_message(m["text"], id=mid, created=m["created"]))
        else:
            out.append(assistant_message(m["result"], id=mid, created=m["created"], timing_ms=m["timing_ms"], current=current, allowed=allowed))
    return out


def web_urls(view):
    return [s["source_url"] for s in view.get("sources", []) if s["source_type"] == "web" and s.get("source_url")]
