"""Build the search index: course-note sections + OpenStax sections -> chunks -> Chroma (+ chunk table for BM25).

Inputs : data/processed/sections.jsonl          (Dr. Inglis's notes, source_type "notes", priority 2)
         data/processed/openstax_sections.jsonl (OpenStax A&P 2e, source_type "open_text", priority 3)
         data/processed/guide_chunks.jsonl      (dissection-guide slides, source_type "dissection_guide", priority 2: the notes' tier)
Outputs: data/index/chunks.jsonl   one record per chunk (text + metadata; BM25 is built from this at load time)
         data/index/chroma/        Chroma collection with BAAI/bge-small-en-v1.5 embeddings (cosine)

Notes sections are indexed as they are (one chunk per section). OpenStax sections longer than ~1,500
characters are split into overlapping chunks; every chunk keeps section_path and source_url.
The text that is embedded is breadcrumb + text_clean, so headings help retrieval.

Run (repo root):  .venv/bin/python -m src.retrieval.index
"""
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTES_PATH = ROOT / "data" / "processed" / "sections.jsonl"
REFS_PATH = ROOT / "data" / "processed" / "openstax_sections.jsonl"
INDEX_DIR = ROOT / "data" / "index"
CHUNKS_PATH = INDEX_DIR / "chunks.jsonl"
CHROMA_DIR = INDEX_DIR / "chroma"
COLLECTION = "anatovision"

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge: queries only, not passages
CHUNK_TRIGGER = 1500   # OpenStax sections longer than this are split
CHUNK_SIZE = 1200      # target chunk length in characters
CHUNK_OVERLAP = 250
NOTE_CHUNK_TRIGGER = 2200  # notes sections are kept whole unless longer than this (e.g. narrated script slides)

STOPWORDS = set("""a an and are as at be been by can do does did for from has have how in into is it its of on or that
the their there these this those to was were what when where which who why with within also than then such may
most more other some each both via per not but if all any one two""".split())


def tokenize(text):
    """Shared by index and search so BM25 sees the same tokens at build and query time."""
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS and len(t) > 1]


def load_jsonl(path):
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def split_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP, trigger=CHUNK_TRIGGER):
    """Overlapping windows that start and end on sentence/word boundaries where possible."""
    if len(text) <= trigger:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind(". "), window.rfind(".\n"), window.rfind("\n\n"))
            if cut < size * 0.6:  # no good sentence end: fall back to a space
                cut = window.rfind(" ")
            end = start + cut + 1 if cut > 0 else end
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        nxt = end - overlap
        sp = text.find(" ", nxt)
        start = sp + 1 if 0 <= sp < end else nxt
    return [c for c in chunks if c]


def note_chunks(sections):
    for s in sections:
        pieces = split_text(s["text_clean"], trigger=NOTE_CHUNK_TRIGGER)
        for j, piece in enumerate(pieces):
            yield {
                "id": f"note-{s['lecture_id']}-{s['order']:03d}-{j:02d}",
                "source_type": s["source_type"], "priority": s["priority"],
                "lecture": s["lecture_title"], "breadcrumb": s["breadcrumb"],
                "section_path": s["section_path"], "source_url": "", "source_file": s["source_file"],
                "section_number": "", "chunk_index": j, "n_chunks": len(pieces),
                "uploaded": s.get("uploaded", ""),
                "text": piece, "embed_text": f"{s['breadcrumb']}\n{piece}",
            }


def ref_chunks(sections):
    for k, s in enumerate(sections):
        pieces = split_text(s["text"])
        crumb = "OpenStax A&P 2e > " + " > ".join(s["section_path"])
        for j, piece in enumerate(pieces):
            yield {
                "id": f"ref-{k:04d}-{j:02d}",
                "source_type": s["source_type"], "priority": s["priority"],
                "lecture": s["chapter"], "breadcrumb": crumb,
                "section_path": s["section_path"], "source_url": s["source_url"], "source_file": "",
                "section_number": s["section_number"] or "", "chunk_index": j, "n_chunks": len(pieces),
                "text": piece, "embed_text": f"{crumb}\n{piece}",
            }


GUIDES_PATH = ROOT / "data" / "processed" / "guide_chunks.jsonl"


def guide_chunks():
    """Dissection-guide slides, prepared by scripts/guides_build.py. Embedded as breadcrumb + slide text, like the notes."""
    if not GUIDES_PATH.exists():
        return []
    out = []
    for c in load_jsonl(GUIDES_PATH):
        c["embed_text"] = f"{c['breadcrumb']}\n{c['text']}"
        out.append(c)
    return out


def metadata_of(c):
    return {"source_type": c["source_type"], "priority": c["priority"], "lecture": c["lecture"], "lecture2": c.get("lecture2", ""), "guide": c.get("guide", ""),
            "breadcrumb": c["breadcrumb"], "source_url": c["source_url"], "section_number": c["section_number"],
            "chunk_index": c["chunk_index"]}


def build_chunks():
    notes = load_jsonl(NOTES_PATH)
    refs = load_jsonl(REFS_PATH)
    return list(note_chunks(notes)) + guide_chunks() + list(ref_chunks(refs))


def build_index():
    import chromadb
    from sentence_transformers import SentenceTransformer

    t0 = time.time()
    chunks = build_chunks()
    n_notes = sum(c["source_type"] == "notes" for c in chunks)
    n_guides = sum(c["source_type"] == "dissection_guide" for c in chunks)
    print(f"{len(chunks)} chunks ({n_notes} from the notes, {n_guides} from the dissection guides, "
          f"{len(chunks) - n_notes - n_guides} from OpenStax)", flush=True)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    with CHUNKS_PATH.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps({k: v for k, v in c.items() if k != "embed_text"}, ensure_ascii=False) + "\n")

    model = SentenceTransformer(EMBED_MODEL)
    vectors = model.encode([c["embed_text"] for c in chunks], batch_size=32, normalize_embeddings=True,
                           show_progress_bar=False, convert_to_numpy=True)
    print(f"embedded in {time.time() - t0:.0f}s", flush=True)

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    col = client.create_collection(COLLECTION, configuration={"hnsw": {"space": "cosine"}})
    for i in range(0, len(chunks), 500):
        batch = chunks[i:i + 500]
        col.add(
            ids=[c["id"] for c in batch],
            embeddings=vectors[i:i + 500].tolist(),
            documents=[c["text"] for c in batch],
            metadatas=[metadata_of(c) for c in batch],
        )
    print(f"Chroma collection '{COLLECTION}': {col.count()} vectors -> {CHROMA_DIR.relative_to(ROOT)} "
          f"({time.time() - t0:.0f}s total)")


def update_lecture(lecture_id, sections, model=None, progress=None):
    """Re-index ONE lecture after its notes changed, without touching the other 4,000+ chunks.

    sections: the lecture's new section records (may be empty to remove it). A chunk whose breadcrumb and text did not
    change keeps its stored embedding; only new or changed chunks are embedded. -> {"kept", "embedded", "removed"}.
    progress(fraction, message) is called as it goes.
    """
    import chromadb
    say = progress or (lambda f, m: None)
    prefix = f"note-{lecture_id}-"
    chunks = load_jsonl(CHUNKS_PATH)
    old = [c for c in chunks if c["id"].startswith(prefix)]
    new = list(note_chunks(sections))
    say(0.05, f"Comparing {len(new)} new chunks with {len(old)} indexed ones")
    col = chromadb.PersistentClient(path=str(CHROMA_DIR)).get_collection(COLLECTION)
    stored = {}
    if old:
        got = col.get(ids=[c["id"] for c in old], include=["embeddings"])
        vec_of = dict(zip(got["ids"], got["embeddings"]))             # get() does not keep the requested order: pair by id
        stored = {(c["breadcrumb"], c["text"]): list(map(float, vec_of[c["id"]])) for c in old if c["id"] in vec_of}
    todo = [c for c in new if (c["breadcrumb"], c["text"]) not in stored]
    vectors = {}
    if todo:
        if model is None:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(EMBED_MODEL)
        for i in range(0, len(todo), 16):
            batch = todo[i:i + 16]
            enc = model.encode([c["embed_text"] for c in batch], normalize_embeddings=True, convert_to_numpy=True)
            for c, v in zip(batch, enc):
                vectors[c["id"]] = [float(x) for x in v]
            say(0.1 + 0.7 * min(1.0, (i + 16) / len(todo)), f"Embedding {min(i + 16, len(todo))} of {len(todo)} changed chunks")
    say(0.85, "Updating the search index")
    if old:
        col.delete(ids=[c["id"] for c in old])
    if new:
        col.add(ids=[c["id"] for c in new],
                embeddings=[vectors.get(c["id"]) or stored[(c["breadcrumb"], c["text"])] for c in new],
                documents=[c["text"] for c in new],
                metadatas=[metadata_of(c) for c in new])
    first = next((i for i, c in enumerate(chunks) if c["id"].startswith(prefix)), None)
    rest = [c for c in chunks if not c["id"].startswith(prefix)]
    at = first if first is not None else len(rest)     # a replaced lecture keeps its place; a new one goes after the notes
    if first is None:
        at = max([i + 1 for i, c in enumerate(rest) if c["source_type"] == "notes"] or [0])
    merged = rest[:at] + [{k: v for k, v in c.items() if k != "embed_text"} for c in new] + rest[at:]
    tmp = CHUNKS_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for c in merged:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    tmp.replace(CHUNKS_PATH)
    say(1.0, "Search index updated")
    return {"kept": len(new) - len(todo), "embedded": len(todo), "removed": len(old)}


if __name__ == "__main__":
    sys.exit(build_index())
