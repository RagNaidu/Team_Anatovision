"""Notes upload: versioned, never touches data/raw/notes, re-parses and re-indexes only that lecture."""
import hashlib
import io
import json
from pathlib import Path

import chromadb
import docx
import numpy as np
import pytest

from src import notes_upload as nu
from src.ingest import parse
from src.retrieval import index as idx

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "notes"
ROOT = Path(__file__).resolve().parents[1]


def raw_fingerprint():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(RAW.iterdir())}


class FakeEmbedder:
    def __init__(self):
        self.encoded = []

    def encode(self, texts, normalize_embeddings=True, convert_to_numpy=True, **kw):
        self.encoded += list(texts)
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            v = np.array([b / 255 + 0.01 for b in h[:8]])
            out.append(v / np.linalg.norm(v))
        return np.array(out)


def make_docx(sections, title="Test Region"):
    d = docx.Document()
    d.add_paragraph(title, style="Title")
    for heading, text in sections:
        d.add_heading(heading, 1)
        d.add_paragraph(text)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


V1 = make_docx([("Overview", "The test muscle attaches to the test bone."), ("Nerves", "The test nerve supplies the test muscle.")])
V2 = make_docx([("Overview", "The test muscle attaches to the test bone."), ("Nerves", "The test nerve supplies the test muscle and skin."),
                ("Vessels", "The test artery runs beside the nerve.")])
NAME = "Lecture 23 - Test Region - Notes.docx"
OTHER = {"id": "note-L01-other-000-00", "source_type": "notes", "priority": 2, "lecture": "Lecture 01 - Other", "breadcrumb": "Lecture 01 - Other > A",
         "section_path": ["A"], "source_url": "", "source_file": "x.docx", "section_number": "", "chunk_index": 0, "n_chunks": 1, "text": "other text"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(nu, "UPLOAD_DIR", tmp_path / "notes_uploaded")
    monkeypatch.setattr(nu, "SECTIONS_PATH", tmp_path / "sections.jsonl")
    monkeypatch.setattr(idx, "CHUNKS_PATH", tmp_path / "chunks.jsonl")
    monkeypatch.setattr(idx, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(idx, "COLLECTION", "t_" + tmp_path.name[-8:].replace("-", "_"))
    other_section = {"lecture_id": "L01-other", "lecture_title": "Lecture 01 - Other", "section_path": ["A"], "breadcrumb": "Lecture 01 - Other > A",
                     "text": "other text", "text_clean": "other text", "source_file": "x.docx", "source_type": "notes", "priority": 2, "order": 1}
    nu.write_sections([other_section])
    emb = FakeEmbedder()
    col = chromadb.PersistentClient(path=str(idx.CHROMA_DIR)).create_collection(idx.COLLECTION, configuration={"hnsw": {"space": "cosine"}})
    col.add(ids=[OTHER["id"]], embeddings=[emb.encode(["x"])[0].tolist()], documents=["other text"],
            metadatas=[{"source_type": "notes", "priority": 2, "lecture": "Lecture 01 - Other", "breadcrumb": "b", "source_url": "",
                        "section_number": "", "chunk_index": 0}])
    idx.CHUNKS_PATH.write_text(json.dumps(OTHER) + "\n", encoding="utf-8")
    emb.encoded.clear()
    return emb, col


def upload(data, emb, name=NAME, **kw):
    return nu.add_or_replace(name, data, model=emb, today="2026-10-07", **kw)


def test_the_original_notes_are_never_modified(env):
    emb, _ = env
    before, listing = raw_fingerprint(), sorted(p.name for p in RAW.iterdir())
    upload(V1, emb)
    upload(V2, emb)
    with pytest.raises(nu.UploadError):
        upload(b"not a docx", emb)
    assert raw_fingerprint() == before and sorted(p.name for p in RAW.iterdir()) == listing
    assert not any("Test Region" in n for n in listing)
    assert str(RAW) not in str(nu.UPLOAD_DIR)


def test_a_new_lecture_is_saved_parsed_and_indexed(env):
    emb, col = env
    out = upload(V1, emb)
    assert out["lecture"] == "Lecture 23 - Test Region" and out["version"] == 1 and out["replaced"] is False
    assert (nu.UPLOAD_DIR / out["lecture_id"] / "v001__Lecture 23 - Test Region - Notes.docx").read_bytes() == V1
    rows = [r for r in nu.read_sections() if r["lecture_id"] == out["lecture_id"]]
    assert [r["section_path"] for r in rows] == [["Overview"], ["Nerves"]]
    assert all(r["uploaded"] == "2026-10-07" and r["source_type"] == "notes" and r["priority"] == 2 for r in rows)
    chunks = idx.load_jsonl(idx.CHUNKS_PATH)
    mine = [c for c in chunks if c["id"].startswith(f"note-{out['lecture_id']}-")]
    assert len(mine) == 2 and all(c["uploaded"] == "2026-10-07" and c["source_type"] == "notes" for c in mine)
    assert col.count() == 3 and out["index"] == {"kept": 0, "embedded": 2, "removed": 0}


def test_other_lectures_are_untouched_by_an_upload(env):
    emb, col = env
    upload(V1, emb)
    upload(V2, emb)
    assert [c for c in idx.load_jsonl(idx.CHUNKS_PATH) if c["id"] == OTHER["id"]] == [OTHER]
    assert col.get(ids=[OTHER["id"]])["documents"] == ["other text"]
    assert any(r["lecture_id"] == "L01-other" for r in nu.read_sections())


def test_a_replacement_keeps_old_versions_and_re_embeds_only_what_changed(env):
    emb, col = env
    first = upload(V1, emb)
    emb.encoded.clear()
    second = upload(V2, emb)
    folder = nu.UPLOAD_DIR / first["lecture_id"]
    assert sorted(p.name for p in folder.iterdir()) == ["v001__Lecture 23 - Test Region - Notes.docx",
                                                       "v002__Lecture 23 - Test Region - Notes.docx"]
    assert second["version"] == 2 and second["replaced"] is True
    assert second["index"] == {"kept": 1, "embedded": 2, "removed": 2}          # "Overview" unchanged; "Nerves" changed, "Vessels" new
    assert len(emb.encoded) == 2 and not any("The test muscle attaches" in t for t in emb.encoded)
    assert col.count() == 4
    manifest = nu.load_manifest()[first["lecture_id"]]
    assert manifest["active"] == 2 and [v["version"] for v in manifest["versions"]] == [1, 2]
    assert len([r for r in nu.read_sections() if r["lecture_id"] == first["lecture_id"]]) == 3


def test_a_replaced_lecture_keeps_its_position(env):
    emb, _ = env
    upload(V1, emb)
    order = [r["lecture_id"] for r in nu.read_sections()]
    assert order[0] == "L01-other" and order[-1] == "L23-test-region"
    upload(V2, emb)
    assert [r["lecture_id"] for r in nu.read_sections()][0] == "L01-other"


def test_bad_uploads_are_refused_without_changing_anything(env):
    emb, _ = env
    before = nu.read_sections()
    for name, data in (("Lecture 23 - X.pdf", V1), ("Lecture 23 - X.docx", b""), ("Lecture 23 - X.docx", b"MZ not word"),
                       ("My notes.docx", V1), ("Lecture 23 - X.docx", b"PK\x03\x04 broken zip")):
        with pytest.raises(nu.UploadError):
            upload(data, emb, name=name)
    assert nu.read_sections() == before
    assert [c["id"] for c in idx.load_jsonl(idx.CHUNKS_PATH)] == [OTHER["id"]]


def test_a_corrupt_docx_leaves_a_recorded_version_but_nothing_active(env):
    emb, _ = env
    with pytest.raises(nu.UploadError):
        upload(b"PK\x03\x04 broken zip", emb, name="Lecture 24 - Broken.docx")
    entry = nu.load_manifest()["L24-broken"]
    assert entry["active"] is None and entry["versions"][0]["error"]
    assert not any(r["lecture_id"] == "L24-broken" for r in nu.read_sections())


def test_a_doc_file_without_libreoffice_is_saved_but_not_activated(env, monkeypatch):
    emb, _ = env
    monkeypatch.setattr(parse, "find_soffice", lambda: None)
    with pytest.raises(nu.UploadError, match="LibreOffice"):
        upload(b"\xd0\xcf\x11\xe0 old word file", emb, name="Lecture 25 - Old Format.doc")
    assert nu.load_manifest()["L25-old-format"]["active"] is None


def test_path_tricks_in_the_file_name_stay_inside_the_upload_folder(env):
    emb, _ = env
    assert nu.clean_name("../../etc/Lecture 23 - X.docx") == "Lecture 23 - X.docx"
    assert nu.clean_name("..\\..\\Lecture 23 - X.docx") == "Lecture 23 - X.docx"
    out = upload(V1, emb, name="../../../Lecture 23 - Test Region - Notes.docx")
    stored = list((nu.UPLOAD_DIR / out["lecture_id"]).iterdir())
    assert len(stored) == 1 and nu.UPLOAD_DIR in stored[0].parents


def test_a_full_re_parse_re_applies_the_uploads(env):
    emb, _ = env
    upload(V1, emb)
    originals = [r for r in nu.read_sections() if r["lecture_id"] == "L01-other"]
    rebuilt = nu.apply_uploads(list(originals))
    assert [r["lecture_id"] for r in rebuilt].count("L23-test-region") == 2 and rebuilt[0]["lecture_id"] == "L01-other"
    assert all(r.get("uploaded") == "2026-10-07" for r in rebuilt if r["lecture_id"] == "L23-test-region")


def test_library_shows_uploaded_badge_data(env):
    emb, _ = env
    upload(V1, emb)
    rows = {r["lecture_id"]: r for r in nu.library()}
    assert rows["L23-test-region"]["uploaded"] == "2026-10-07" and rows["L23-test-region"]["sections"] == 2
    assert rows["L01-other"]["uploaded"] == "" and rows["L01-other"]["sections"] == 1


def test_estimate_cost():
    assert nu.estimate_cost(100) == pytest.approx(1.5)


def test_uploading_the_same_file_twice_is_refused(env):
    emb, _ = env
    upload(V1, emb)
    with pytest.raises(nu.UploadError, match="identical"):
        upload(V1, emb)
    assert len(list((nu.UPLOAD_DIR / "L23-test-region").iterdir())) == 1
