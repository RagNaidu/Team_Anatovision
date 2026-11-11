"""The Notes manager end to end on a THROW-AWAY data folder: upload, preview, publish, ask, edit, diff, rollback, archive, restore, purge.
A hashing embedder and a fake fact-check stand in for the model; the real live data, index, grants and review files are never touched (md5-checked)."""
import hashlib
import io
import json
import re
from pathlib import Path

import numpy as np
import pytest

from src import auth, notes_manager as NM, verified
from src.ingest import stage as ST

ROOT = Path(__file__).resolve().parents[1]
REAL = ["data/users.json", "data/flags.jsonl", "data/question_log.jsonl", "data/verified_fixes.jsonl", "data/processed/sections.jsonl", "data/index/chunks.jsonl",
        "data/dissection_guides_map.json", "reports/factcheck_all.json"]


def md5s():
    return {p: hashlib.md5((ROOT / p).read_bytes()).hexdigest() if (ROOT / p).exists() else None for p in REAL}


class Hash:
    """A deterministic bag-of-words embedder: texts that share words are close."""
    def encode(self, texts, **kw):
        out = []
        for t in ([texts] if isinstance(texts, str) else texts):
            v = np.zeros(128)
            for w in re.findall(r"[a-z]{3,}", t.lower()):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 128] += 1
            out.append(v / (np.linalg.norm(v) or 1))
        return np.array(out)


def docx_bytes(sections):
    import docx
    d = docx.Document()
    for h1, h2, body in sections:
        d.add_heading(h1, 1)
        d.add_heading(h2, 2)
        d.add_paragraph(body)
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


def pptx_bytes(slides):
    from pptx import Presentation
    p = Presentation()
    for title, body in slides:
        s = p.slides.add_slide(p.slide_layouts[1])
        s.shapes.title.text = title
        s.placeholders[1].text = body
    b = io.BytesIO()
    p.save(b)
    return b.getvalue()


ZQ = "Hoof Digits The zebra hoof is a single enlarged third digit that carries the whole"
AQ = "Alpha Lobes The alpha organ has three lobes arranged around a central cavity and is"
ZEBRA = [("Hoof", "Digits", "The zebra hoof is a single enlarged third digit that carries the whole weight of the animal across hard savanna ground."),
         ("Stripes", "Pattern", "The stripe pattern of a zebra is unique to each animal and is thought to discourage biting flies from landing on the skin.")]
BASE = [("Alpha", "Lobes", "The alpha organ has three lobes arranged around a central cavity and is supplied by the beta artery in the usual way.")]


@pytest.fixture
def lab(tmp_path, monkeypatch):
    live = tmp_path / "live"
    for p in ("processed", "reports", "index"):
        (live / p).mkdir(parents=True)
    L = ST.layout(live)
    cm = ST.use(live)
    cm.__enter__()
    monkeypatch.setattr(NM, "DB_PATH", tmp_path / "nm.db")
    monkeypatch.setattr(NM, "MANAGED_DIR", tmp_path / "managed")
    monkeypatch.setattr(NM, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(NM, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(NM, "EMBEDDER", Hash())
    monkeypatch.setattr(NM, "SYNC", True)
    monkeypatch.setattr(NM, "FACT_CHECK", lambda recs: [{"claim_quote": recs[0]["text_clean"][:40], "issue": "AI says this may be wrong", "severity": "high", "tier": "likely_factual",
                                                       "lecture": recs[0]["lecture_title"], "lecture_id": recs[0]["lecture_id"], "section_path": recs[0]["section_path"],
                                                       "breadcrumb": recs[0]["breadcrumb"], "order": recs[0]["order"], "type": "factual"}])
    monkeypatch.setattr(NM, "RELOAD", [])
    monkeypatch.setattr(auth, "USERS_PATH", tmp_path / "users.json")
    monkeypatch.setattr(verified, "FIXES_PATH", tmp_path / "fixes.jsonl")
    auth.save_users({"prof": auth.new_record("Prof", "professor", "password-long-1"),
                     "s1": auth.new_record("S1", "student", "password-long-1", ["Lecture 01 - Alpha"]),
                     "s2": auth.new_record("S2", "student", "password-long-1", ["Lecture 01 - Alpha"])})
    recs = [NM._record("L01-alpha", "Lecture 01 - Alpha", [h1, h2], body, i, "alpha.docx") for i, (h1, h2, body) in enumerate(BASE, 1)]
    from src.ingest import revision as R
    NM._write_jsonl(L["sections"], [R.with_version(r, 2) for r in recs])
    NM._write_jsonl(L["openstax"], [])
    L["map"].write_text(json.dumps({"generated": "", "zip": "Revised", "guides": []}), encoding="utf-8")
    NM._write_jsonl(L["slides"], [])
    NM._write_jsonl(L["gchunks"], [])
    L["factcheck"].write_text(json.dumps({"issues": []}), encoding="utf-8")
    NM.rebuild_stage_index(live, L)
    yield L
    cm.__exit__(None, None, None)


def search_titles(q, allowed=None):
    from src.retrieval.search import Searcher
    s = Searcher()
    s._model = NM.EMBEDDER
    res = s.search(q, k=8, allowed_lectures=allowed, rerank=False)
    return [h.chunk["doc_id"] for h in res.hits] if res.found else []


def sections_now(L):
    return NM._read_jsonl(L["sections"])


def test_a_note_goes_through_upload_preview_publish_edit_diff_rollback_archive_restore_purge(lab):
    before = md5s()
    up = NM.create_upload("prof", "Lecture 40 - Zebra Anatomy - Notes.docx", docx_bytes(ZEBRA))
    doc_id = up["doc_id"]
    d = NM.detail(doc_id)
    assert d["status"] == "ready" and d["job"]["status"] == "ready" and len(d["sections"]) == 2 and d["title"] == "Lecture 40 - Zebra Anatomy"
    assert d["sections"][0]["path"] == ["Hoof", "Digits"] and d["flags"]["count"] == 1
    assert doc_id not in {r["lecture_id"] for r in sections_now(lab)}                    # nothing live yet
    assert search_titles(ZQ) == [] or doc_id not in search_titles(ZQ)

    out = NM.publish("prof", doc_id, access="selected", students=["s1"])
    assert out["granted"] == 1 and out["flags_added"] == 1
    users = auth.load_users()
    assert "Lecture 40 - Zebra Anatomy" in users["s1"]["allowed_lectures"] and "Lecture 40 - Zebra Anatomy" not in users["s2"]["allowed_lectures"]
    assert doc_id in search_titles(ZQ)
    assert "L01-alpha" in search_titles(AQ)        # the other document is still found
    report = json.loads(lab["factcheck"].read_text())
    assert [i["revision"]["status"] for i in report["issues"]] == ["new_in_revision"]
    assert NM.list_documents(q="Zebra")["items"][0]["status"] == "published"

    e = NM.edit_sections("prof", doc_id, [{"index": 0, "text": "The zebra hoof is a single enlarged third digit used for galloping."}])
    assert e["version"] == 2
    assert any("galloping" in r["text_clean"] for r in sections_now(lab) if r["lecture_id"] == doc_id)
    diff = NM.version_diff(doc_id, 2)
    assert diff["counts"]["edited"] + diff["counts"].get("rewritten", 0) == 1
    assert [v["version"] for v in NM.version_history(doc_id)] == [2, 1]

    r = NM.rollback("prof", doc_id, 1)
    assert r["version"] == 3 and not any("galloping" in x["text_clean"] for x in sections_now(lab))
    assert NM.detail(doc_id)["live_version"] == 3 and len(list(NM.BACKUP_DIR.glob("*"))) == 3   # one backup per swap: publish, edit, rollback

    NM.archive("prof", doc_id)
    assert doc_id not in {x["lecture_id"] for x in sections_now(lab)} and doc_id not in search_titles(ZQ)
    assert NM.detail(doc_id)["status"] == "archived" and "L01-alpha" in search_titles(AQ)
    NM.restore("prof", doc_id)
    assert doc_id in search_titles(ZQ)
    NM.archive("prof", doc_id)
    with pytest.raises(NM.ManagerError):
        NM.purge("prof", doc_id, "wrong title")
    NM.purge("prof", doc_id, "Lecture 40 - Zebra Anatomy")
    assert not (NM.MANAGED_DIR / doc_id).exists() and "Lecture 40 - Zebra Anatomy" not in auth.load_users()["s1"]["allowed_lectures"]
    actions = [a["action"] for a in NM.audit_log(doc_id)]
    assert actions[0] == "purged" and "published" in actions and "uploaded" in actions and "rolled back" in actions
    assert md5s() == before


def test_an_existing_live_document_can_be_edited_and_archived_and_the_change_reaches_answers_and_flags(lab):
    items = [{"claim_quote": "supplied by the beta artery", "lecture": "Lecture 01 - Alpha", "lecture_id": "L01-alpha", "breadcrumb": "Lecture 01 - Alpha > Alpha > Lobes", "section_path": ["Alpha", "Lobes"],
              "order": 1, "revision": {"status": "unchanged"}}]
    lab["factcheck"].write_text(json.dumps({"issues": items}))
    verified.write_jsonl(verified.FIXES_PATH, [{"id": "vf-0001", "lecture": "Lecture 01 - Alpha", "breadcrumb": "x", "notes_quote": "supplied by the beta artery", "decision": "confirm_error"}])
    assert NM.list_documents(q="Alpha")["items"][0]["status"] == "published"
    NM.edit_sections("prof", "L01-alpha", [{"index": 0, "text": "The alpha organ is supplied by the gamma artery."}])
    issue = json.loads(lab["factcheck"].read_text())["issues"][0]
    assert issue["revision"]["status"] == "changed" and "gamma" in issue["revision"]["new_text"]
    assert verified.read_jsonl(verified.FIXES_PATH)[0]["needs_recheck"] is True
    NM.archive("prof", "L01-alpha")
    assert not sections_now(lab) and not NM._read_jsonl(lab["index"] / "chunks.jsonl")      # nothing of it is left to be cited


def test_a_new_pptx_guide_is_added_and_a_replacement_file_makes_a_new_version(lab, tmp_path, monkeypatch):
    from src import guide_images as GI
    from src import guide_marks as GM
    monkeypatch.setattr(GI, "IMG_DIR", tmp_path / "guide_images")
    up = NM.create_upload("prof", "Class 77 - The Zebra Leg.pptx", pptx_bytes([("Hoof", "Cut through the zebra hoof capsule and expose the single enlarged third digit carefully."),
                                                                           ("Tendon", "Identify the long flexor tendon of the zebra digit and follow it to the bone.")]))
    d = NM.detail(up["doc_id"])
    assert d["kind"] == "guide" and len(d["sections"]) == 2 and d["status"] == "ready"
    NM.publish("prof", up["doc_id"], access="all")
    assert up["doc_id"] and any(c["source_file"].endswith("Zebra Leg.pptx") or "Zebra" in c["breadcrumb"] for c in NM._read_jsonl(lab["gchunks"]))
    again = NM.create_upload("prof", "Class 77 - The Zebra Leg.pptx", pptx_bytes([("Hoof", "Cut through the hoof capsule and expose the digit.")]), doc_id=up["doc_id"])
    assert again["version"] == 2
    from app_api import catalog
    gid = next(g["id"] for g in catalog.guides() if "Zebra" in g["title"])
    marks = GM.MarkStore()
    m = marks.create(gid, 1, "label", {"x": 0.5, "y": 0.5}, "Hoof pin", None, "prof")
    marks.set_status(gid, [1], "approved")
    dd = NM.detail(up["doc_id"])
    assert dd["diff"] is not None and dd["status"] == "published" and dd["live_version"] == 1
    NM.publish("prof", up["doc_id"])
    assert NM.detail(up["doc_id"])["live_version"] == 2 and [v["version"] for v in NM.version_history(up["doc_id"])] == [2, 1]
    assert marks.get(m["id"])["status"] == "draft"                                   # the guide file changed: marks drawn on the old slides wait for the instructor again
    if GI.soffice():
        assert GI.meta(gid)["mode"] == "render" and "1" in GI.meta(gid)["slides"]            # and its slides were rendered and cropped again from the new file (text-only slides get no picture)


def test_a_doc_file_is_converted_with_libreoffice_when_it_is_installed(lab, tmp_path):
    import shutil
    import subprocess
    from src import guide_images as GI
    if not GI.soffice():
        pytest.skip("LibreOffice is not installed")
    src = tmp_path / "old.docx"
    src.write_bytes(docx_bytes(ZEBRA))
    subprocess.run([GI.soffice(), "--headless", "--convert-to", "doc", "--outdir", str(tmp_path / "out"), str(src)], check=True, capture_output=True, timeout=240)
    doc = (tmp_path / "out" / "old.doc").read_bytes()
    up = NM.create_upload("prof", "Lecture 60 - Zebra Anatomy.doc", doc)
    d = NM.detail(up["doc_id"])
    assert d["status"] == "ready" and len(d["sections"]) == 2 and d["sections"][0]["path"][0] == "Hoof"


def test_uploads_are_checked_before_anything_is_stored(lab):
    for name, data, word in [("x.txt", b"hello", "Upload a"), ("x.docx", b"not a zip", "does not look"), ("x.docx", b"", "empty"), ("x.pdf", b"PK\x03\x04", "does not look")]:
        with pytest.raises(NM.ManagerError, match=word):
            NM.create_upload("prof", name, data)
    with pytest.raises(NM.ManagerError, match="MB"):
        NM.create_upload("prof", "big.docx", b"PK\x03\x04" + b"0" * (16 << 20))
    assert not NM.MANAGED_DIR.exists() or not list(NM.MANAGED_DIR.iterdir())


def test_a_second_upload_of_the_same_lecture_is_suggested_as_a_replacement(lab):
    first = NM.create_upload("prof", "Lecture 41 - Zebra Anatomy.docx", docx_bytes(ZEBRA))
    NM.publish("prof", first["doc_id"], access="none")
    second = NM.create_upload("prof", "Lecture 41 - Zebra Anatomy v2.docx", docx_bytes([ZEBRA[0], (ZEBRA[1][0], ZEBRA[1][1], ZEBRA[1][2] + " Extra sentence about stripes on the legs.")]))
    ov = NM.detail(second["doc_id"])["overlap"]
    assert ov["doc_id"] == first["doc_id"] and ov["suggest_replace"] is True
    NM.update_mapping("prof", second["doc_id"], replaces=first["doc_id"])
    d = NM.detail(second["doc_id"])
    assert d["diff"]["counts"]["unchanged"] == 1
    NM.publish("prof", second["doc_id"], access="same")
    ids = {r["lecture_id"] for r in sections_now(lab)}
    assert second["doc_id"] in ids and first["doc_id"] not in ids
    assert NM.detail(first["doc_id"])["status"] == "archived"


def test_a_failed_check_leaves_the_live_data_untouched(lab, monkeypatch):
    up = NM.create_upload("prof", "Lecture 42 - Zebra Anatomy.docx", docx_bytes(ZEBRA))
    monkeypatch.setattr(NM, "retrieval_check", lambda *a, **k: (_ for _ in ()).throw(NM.ManagerError("The quick retrieval check failed", 409)))
    snap = {k: Path(v).read_bytes() for k, v in lab.items() if k in ("sections", "factcheck")}
    with pytest.raises(NM.ManagerError, match="retrieval check"):
        NM.publish("prof", up["doc_id"], access="all")
    assert {k: Path(lab[k]).read_bytes() for k in snap} == snap
    assert NM.detail(up["doc_id"])["status"] == "ready"


# ---- the API ---------------------------------------------------------------------------------------------------------------

@pytest.fixture
def api(lab, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app_api.main import create_app
    from app_api.routers import auth as auth_router
    monkeypatch.setenv("ANATOVISION_API_SESSIONS_PATH", str(tmp_path / "sessions.db"))
    auth_router._fails.clear()
    auth._fails.clear()
    app = create_app(warm_runtime=False)
    with TestClient(app) as c:
        yield c


def sign_in(c, user):
    r = c.post("/api/auth/login", json={"username": user, "password": "password-long-1"})
    assert r.status_code == 200, r.text


def test_the_api_lifecycle_for_an_instructor_and_403_for_every_route_for_a_student(api, lab):
    before = md5s()
    sign_in(api, "s1")
    routes = [("get", "/api/admin/notes"), ("get", "/api/admin/notes/L01-alpha"), ("post", "/api/admin/notes/L01-alpha/publish", {"access": "all"}),
              ("post", "/api/admin/notes/L01-alpha/archive"), ("post", "/api/admin/notes/L01-alpha/restore"), ("post", "/api/admin/notes/L01-alpha/purge", {"confirm_title": "x"}),
              ("put", "/api/admin/notes/L01-alpha/sections", {"edits": []}), ("get", "/api/admin/notes/L01-alpha/versions"), ("get", "/api/admin/notes/L01-alpha/audit"),
              ("post", "/api/admin/notes/L01-alpha/rollback", {"version": 1}), ("patch", "/api/admin/notes/L01-alpha/mapping", {"region": "x"}), ("post", "/api/admin/notes/L01-alpha/discard")]
    for method, url, *body in routes:
        r = getattr(api, method)(url, **({"json": body[0]} if body else {}))
        assert r.status_code == 403, (method, url, r.status_code)
    r = api.post("/api/admin/notes", files={"file": ("Lecture 50 - Zebra.docx", docx_bytes(ZEBRA))})
    assert r.status_code == 403
    api.post("/api/auth/logout")
    sign_in(api, "prof")
    r = api.post("/api/admin/notes", files={"file": ("Lecture 50 - Zebra Anatomy.docx", docx_bytes(ZEBRA))})
    assert r.status_code == 200, r.text
    doc_id = r.json()["doc_id"]
    d = api.get(f"/api/admin/notes/{doc_id}").json()
    assert d["status"] == "ready" and d["job"]["status"] == "ready" and d["flags"]["count"] == 1 and len(d["sections"]) == 2
    bad = api.post("/api/admin/notes", files={"file": ("x.exe", b"MZ")})
    assert bad.status_code == 422 and "error" in bad.json()
    assert api.post(f"/api/admin/notes/{doc_id}/publish", json={"access": "selected", "students": ["s2"]}).json()["granted"] == 1
    listing = api.get("/api/admin/notes", params={"q": "zebra"}).json()
    assert listing["items"][0]["status"] == "published" and listing["items"][0]["access_count"] == 1
    assert api.put(f"/api/admin/notes/{doc_id}/sections", json={"edits": [{"index": 0, "text": "The zebra hoof is one digit."}]}).json()["version"] == 2
    vs = api.get(f"/api/admin/notes/{doc_id}/versions").json()
    assert [v["version"] for v in vs] == [2, 1]
    counts = api.get(f"/api/admin/notes/{doc_id}/versions/2/diff").json()["counts"]
    assert counts["unchanged"] == 1 and sum(v for k, v in counts.items() if k != "unchanged") >= 1
    assert api.post(f"/api/admin/notes/{doc_id}/rollback", json={"version": 1}).json()["version"] == 3
    assert api.post(f"/api/admin/notes/{doc_id}/archive").json()["restorable_until"]
    assert api.post(f"/api/admin/notes/{doc_id}/purge", json={"confirm_title": "nope"}).status_code == 422
    assert api.post(f"/api/admin/notes/{doc_id}/restore").status_code == 200
    api.post(f"/api/admin/notes/{doc_id}/archive")
    assert api.post(f"/api/admin/notes/{doc_id}/purge", json={"confirm_title": "Lecture 50 - Zebra Anatomy"}).status_code == 200
    assert api.get(f"/api/admin/notes/{doc_id}").status_code == 404
    assert md5s() == before
