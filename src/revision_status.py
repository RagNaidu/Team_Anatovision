"""Has a source an old answer cited been changed or removed since? (the revised notes replaced many sections)

An answer saved in a chat keeps the text of the passages it cited. When the chat is opened again, each notes or guide passage is looked up in the CURRENT index by
content: still there (any chunk holds at least 85% of its words) = fine; not there but a chunk with the same lecture and heading exists = "updated"; neither = "removed".
OpenStax and web passages are never labelled. The labels are plain words for the student: "Source updated", "Source removed".
"""
import re

from src.ingest.revision import tokens

THRESHOLD = 0.85
LABELS = {"updated": "Source updated", "removed": "Source removed"}


class CurrentIndex:
    def __init__(self, chunks):
        self.by_type, self.by_key = {}, {}
        for c in chunks:
            if c.get("source_type") not in ("notes", "dissection_guide"):
                continue
            toks = set(tokens(c["text"]))
            self.by_type.setdefault(c["source_type"], []).append(toks)
            self.by_key[(c["lecture"], _plain(c["breadcrumb"]))] = toks

    def status(self, src):
        """src: a passage of a saved answer: {"source_type", "lecture", "breadcrumb", "text"}. -> None | "updated" | "removed"."""
        kind = src.get("source_type")
        if kind not in ("notes", "dissection_guide"):
            return None
        want = set(tokens(src.get("text", "")))
        if len(want) < 4:
            return None
        for toks in self.by_type.get(kind, []):
            if len(want & toks) / len(want) >= THRESHOLD:
                return None
        return "updated" if (src.get("lecture"), _plain(src.get("breadcrumb", ""))) in self.by_key else "removed"


def _plain(text):
    return re.sub(r"\s+", " ", (text or "").replace("›", ">")).strip().lower()
