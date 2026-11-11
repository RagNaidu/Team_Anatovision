"""The revised lecture notes and dissection guides (Dr. Inglis, delivered 2026-10/11 as two zips): safe extraction and CONTENT matching.

Titles and numbers cannot be trusted (the revised set renumbers lectures and renames guides), so a revised file is matched to the file it
replaces by what it SAYS: tf-idf cosine over the whole text, one-to-one (Hungarian assignment), with the runner-up score as a margin check.

  extract(zip_path, dest)           -> [Path]; skips __MACOSX, ~$ temp files, .DS_Store; fixes file names the zip stored as UTF-8 without the flag
  notes_text(records) / deck_text   -> the plain text of a lecture or a guide
  similarity_matrix(old, new)       -> (names_old, names_new, matrix)
  assign(matrix)                    -> [(i, j)] one-to-one
The zips are only ever read.
"""
import math
import re
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np

SKIP = re.compile(r"(^|/)(__MACOSX/|~\$|\.DS_Store)")
WORD = re.compile(r"[a-z][a-z0-9]{2,}")
STOP = set("the and for that with from this which are was were has have not its into their they them there these those been being also can may will "
           "lecture notes slide slides class guide dissection laboratory session figure image images reading readings step note".split())


def member_name(info):
    """zipfile decodes names as cp437 unless the UTF-8 flag is set; a name saved as UTF-8 without the flag comes out as 'Class 04 ��� Laminectomy'."""
    name = info.filename
    if not info.flag_bits & 0x800:
        try:
            name = name.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name


def extract(zip_path, dest):
    """Extract the files of a zip (flat, by file name) into dest. Refuses a name that would escape dest. The zip is never modified. -> [Path]"""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    out = []
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = member_name(info)
            if info.is_dir() or SKIP.search(name):
                continue
            base = Path(name).name
            target = (root / base).resolve()
            if root not in target.parents:
                raise ValueError(f"unsafe path in zip: {info.filename}")
            if not target.exists():
                with z.open(info) as src:
                    target.write_bytes(src.read())
            out.append(target)
    return sorted(out)


def tokens(text):
    return [w.rstrip("s") if len(w) > 4 else w for w in WORD.findall((text or "").lower()) if w not in STOP]


def tfidf_matrix(docs_a, docs_b):
    """Rows = docs_a then docs_b, in one tf-idf space (sublinear tf, smoothed idf), L2-normalised. -> (A, B) arrays."""
    toks = [Counter(tokens(t)) for t in list(docs_a) + list(docs_b)]
    df = Counter(w for c in toks for w in c)
    vocab = {w: i for i, w in enumerate(sorted(w for w, n in df.items() if n >= 1))}
    n = len(toks)
    m = np.zeros((n, len(vocab)), dtype=np.float32)
    for r, c in enumerate(toks):
        for w, k in c.items():
            m[r, vocab[w]] = (1 + math.log(k)) * (math.log((1 + n) / (1 + df[w])) + 1)
        norm = np.linalg.norm(m[r])
        if norm:
            m[r] /= norm
    return m[:len(docs_a)], m[len(docs_a):]


def similarity_matrix(docs_a, docs_b):
    a, b = tfidf_matrix(docs_a, docs_b)
    return a @ b.T


def assign(sim, floor=0.0):
    """One-to-one best pairing (Hungarian). -> [(i, j, score)] for pairs with score > floor."""
    from scipy.optimize import linear_sum_assignment
    rows, cols = linear_sum_assignment(-sim)
    return [(int(i), int(j), float(sim[i, j])) for i, j in zip(rows, cols) if sim[i, j] > floor]


def runner_up(sim, i, j, axis):
    """The best OTHER score for row i (axis 0) or column j (axis 1) besides the assigned one."""
    vec = np.array(sim[i, :] if axis == 0 else sim[:, j], dtype=float)
    vec[j if axis == 0 else i] = -1
    return float(vec.max()) if vec.size > 1 else 0.0


# ---------------------------------------------------------------------------------------------------------------
# notes: a plain-text copy of a revised .docx (the parser reads headings from the .docx itself and uses the text copy for the outline layouts)
# ---------------------------------------------------------------------------------------------------------------

def docx_text_copy(docx_path, out_path):
    """Write `docx_path` as the text layout src/ingest/parse.py expects: one paragraph per line, list items as '-   text' indented 4 spaces per level."""
    from docx import Document
    doc = Document(str(docx_path))
    lines = []
    for p in doc.paragraphs:
        text = re.sub(r"\s+", " ", p.text).strip()
        pPr = p._p.pPr
        level = None
        if pPr is not None and pPr.numPr is not None:
            level = int(pPr.numPr.ilvl.val) if pPr.numPr.ilvl is not None else 0
        if not text:
            lines.append("")
        elif level is not None:
            lines.append("    " * level + "-   " + text)
        else:
            lines.append(text)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------------------------------------------
# section / slide diff of one pair of documents
# ---------------------------------------------------------------------------------------------------------------
SAME, EDITED, REWRITTEN = 0.98, 0.50, 0.30


def diff_sections(old_secs, new_secs):
    """old_secs / new_secs: [{"path", "text"}]. Best match of every old section among the new ones and of every new section among the old ones (tf-idf cosine).
    -> {"unchanged", "edited", "rewritten", "removed", "added": counts, "removed_paths", "added_paths", "changed_paths"}"""
    if not old_secs or not new_secs:
        return {"unchanged": 0, "edited": 0, "rewritten": 0, "removed": len(old_secs), "added": len(new_secs),
                "removed_paths": [s["path"] for s in old_secs], "added_paths": [s["path"] for s in new_secs], "changed_paths": []}
    sim = similarity_matrix([s["text"] for s in old_secs], [s["text"] for s in new_secs])
    best_old = sim.max(axis=1)
    best_new = sim.max(axis=0)
    out = {"unchanged": int((best_old >= SAME).sum()), "edited": int(((best_old >= EDITED) & (best_old < SAME)).sum()),
           "rewritten": int(((best_old >= REWRITTEN) & (best_old < EDITED)).sum()), "removed": int((best_old < REWRITTEN).sum()),
           "added": int((best_new < REWRITTEN).sum())}
    out["removed_paths"] = [old_secs[i]["path"] for i in range(len(old_secs)) if best_old[i] < REWRITTEN]
    out["added_paths"] = [new_secs[j]["path"] for j in range(len(new_secs)) if best_new[j] < REWRITTEN]
    out["changed_paths"] = [old_secs[i]["path"] for i in range(len(old_secs)) if REWRITTEN <= best_old[i] < SAME]
    return out


# ---------------------------------------------------------------------------------------------------------------
# version metadata, titles
# ---------------------------------------------------------------------------------------------------------------
SUPERSEDED_NOTE = "Earlier version, not in revised notes"


def v2_stem(file_name):
    """'Lecture 04 - The_Shoulder - Notes.docx' -> 'Lecture 04 - The Shoulder'; 'Lecture 01 - ... - Notes - Reviewed.docx' -> 'Lecture 01 - ...'; '... script.docx' -> '...'."""
    stem = Path(file_name).stem.replace("_", " ")
    stem = re.sub(r"\s*-\s*Notes\s*-\s*Reviewed$", "", stem, flags=re.I)
    stem = re.sub(r"\s*-\s*(Student )?Notes$", "", stem, flags=re.I)
    stem = re.sub(r"\s+script$", "", stem, flags=re.I)
    return re.sub(r"\s+", " ", stem).strip()


def with_version(record, version, doc_id=None, superseded=False):
    """Every section record carries doc_id (the lecture id), version (1 = the first files, 2 = the revised ones) and a section_id."""
    doc = doc_id or record["lecture_id"]
    out = dict(record)
    out.update(doc_id=doc, version=version, section_id=f"{doc}#{record['order']:03d}:{' > '.join(record['section_path'])}")
    if superseded:
        out["superseded"] = SUPERSEDED_NOTE
    return out


def squash(text):
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def find_quote(quote, docs):
    """Where a flagged quote lives now. docs = [(doc key, [(section_path_list, text)])]. -> (doc key, section index) of the first section containing it, else None."""
    q = squash(quote)
    if not q:
        return None
    for key, secs in docs:
        for i, (_path, text) in enumerate(secs):
            if q in squash(text):
                return key, i
    return None


def best_sentence(quote, texts):
    """The sentence among `texts` that shares most words with the quote (for 'the new wording'). -> str or ''."""
    want = set(tokens(quote))
    best, score = "", 0.0
    for t in texts:
        for sent in re.split(r"(?<=[.!?])\s+|\n+", t):
            have = set(tokens(sent))
            if want and have:
                s = len(want & have) / len(want | have)
                if s > score:
                    best, score = sent.strip(" -"), s
    return best if score >= 0.25 else ""
