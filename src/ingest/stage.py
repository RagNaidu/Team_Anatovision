"""Run code against a STAGED copy of the data (sections, guides, map, index, fact-check report) without touching the live files.

    with stage.use(Path("data/staging_v2")):
        ...  # every module that reads data/processed/*, the index, the guide map or the fact-check report reads the staged copy

Used for the revised-notes build: the tests and live checks run on the stage before it is swapped in (scripts/revision_build.py swap).
"""
import contextlib
from pathlib import Path


def layout(stage):
    stage = Path(stage)
    return {"sections": stage / "processed" / "sections.jsonl", "openstax": stage / "processed" / "openstax_sections.jsonl",
            "slides": stage / "processed" / "guide_slides.jsonl", "gchunks": stage / "processed" / "guide_chunks.jsonl",
            "gcache": stage / "processed" / "guide_map_cache.json", "map": stage / "dissection_guides_map.json",
            "index": stage / "index", "factcheck": stage / "reports" / "factcheck_all.json"}


@contextlib.contextmanager
def use(stage):
    from app_api import catalog
    from src import notes_upload, review, reports, trust, verified
    from src.ingest import guide_map
    from src.ingest import guides as G
    from src.ingest import parse
    from src.modes import guide, qa
    from src.retrieval import index, search
    L = layout(stage)
    patches = [(parse, "OUT_PATH", L["sections"]), (G, "SECTIONS_PATH", L["sections"]), (G, "SLIDES_PATH", L["slides"]), (G, "CHUNKS_PATH", L["gchunks"]),
               (G, "MAP_PATH", L["map"]), (guide_map, "CACHE_PATH", L["gcache"]), (guide, "SECTIONS_PATH", L["sections"]), (trust, "SECTIONS_PATH", L["sections"]),
               (verified, "SECTIONS_PATH", L["sections"]), (notes_upload, "SECTIONS_PATH", L["sections"]), (catalog, "SECTIONS_PATH", L["sections"]),
               (index, "NOTES_PATH", L["sections"]), (index, "REFS_PATH", L["openstax"]), (index, "GUIDES_PATH", L["gchunks"]), (index, "INDEX_DIR", L["index"]),
               (index, "CHUNKS_PATH", L["index"] / "chunks.jsonl"), (index, "CHROMA_DIR", L["index"] / "chroma"),
               (search, "CHROMA_DIR", L["index"] / "chroma"), (search, "CHUNKS_PATH", L["index"] / "chunks.jsonl"),
               (qa, "FACTCHECK_PATH", L["factcheck"]), (review, "FACTCHECK_PATH", L["factcheck"]), (reports, "FACTCHECK_PATH", L["factcheck"])]
    old = [(m, a, getattr(m, a)) for m, a, _ in patches]
    for m, a, v in patches:
        setattr(m, a, v)
    catalog._cache.clear()
    try:
        yield L
    finally:
        for m, a, v in old:
            setattr(m, a, v)
        catalog._cache.clear()
