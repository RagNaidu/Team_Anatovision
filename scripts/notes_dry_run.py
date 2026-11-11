"""Live dry run of the Notes manager with REAL services (BullsAI fact-check, bge-small embeddings) on a STAGED index. Nothing is swapped: the manager's own database,
originals and staging folder go to a throw-away folder, the live files are only read (md5 printed before and after), and the document is discarded at the end."""
import hashlib, io, json, shutil, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
from src import notes_manager as NM

LIVE = ["data/users.json", "data/flags.jsonl", "data/question_log.jsonl", "data/verified_fixes.jsonl", "data/processed/sections.jsonl", "data/index/chunks.jsonl",
        "data/dissection_guides_map.json", "reports/factcheck_all.json", "data/processed/guide_slides.jsonl"]
md5 = lambda: {p: hashlib.md5((ROOT / p).read_bytes()).hexdigest() if (ROOT / p).exists() else None for p in LIVE}


def fake_docx():
    import docx
    d = docx.Document()
    d.add_heading("Zorblax Anatomy", 1)
    d.add_heading("The Quillon Gland", 2)
    d.add_paragraph("TEST DOCUMENT, made up. The quillon gland of the zorblax lies behind the third glimmer plate and drains through the hollow wibble duct. "
                    "The wibble duct is supplied by the fictional mirth artery and is always longer than the zorblax tail.")
    b = io.BytesIO(); d.save(b); return b.getvalue()


tmp = Path(tempfile.mkdtemp(prefix="nm_dry_"))
NM.DB_PATH, NM.MANAGED_DIR, NM.BACKUP_DIR, NM.STAGING_DIR = tmp / "nm.db", tmp / "managed", tmp / "backups", tmp / "staging"
NM.SYNC = True
before, t = md5(), {}
t0 = time.time()
up = NM.create_upload("dry-run", "Lecture 99 - Zorblax Anatomy.docx", fake_docx())
t["upload_and_process (parse, map, overlap, real fact-check)"] = time.time() - t0
d = NM.detail(up["doc_id"])
print("status:", d["status"], "| job:", d["job"]["status"], d["job"]["error"], "| sections:", len(d["sections"]), "| region:", d["region"], "| overlap:", d["overlap"], "| flags:", d["flags"]["count"])
for f in d["flags"]["items"]:
    print("  flag:", f["quote"][:60], "->", f["issue"][:90])
if d["status"] == "ready":
    from src.ingest import stage as ST
    doc_id, payload = up["doc_id"], NM.load_payload(up["doc_id"], 1)
    L = NM.live()
    t0 = time.time(); stage, S = NM._stage_copy(doc_id); t["staged copy of data files"] = time.time() - t0
    try:
        NM._apply_note(S, payload, 1, False)
        t0 = time.time(); info = NM.rebuild_stage_index(stage, L); t["staged index (real bge-small; reuse live embeddings)"] = time.time() - t0
        print("staged index:", info)
        t0 = time.time()
        try:
            print("retrieval check:", NM.retrieval_check(stage, doc_id, payload))
        except NM.ManagerError as e:
            print("retrieval check FAILED:", e)
        t["retrieval check"] = time.time() - t0
    finally:
        shutil.rmtree(stage, ignore_errors=True)
NM.discard("dry-run", up["doc_id"])
print("discarded; live data unchanged:", md5() == before)
for k, v in t.items():
    print(f"  {v:6.1f}s  {k}")
shutil.rmtree(tmp, ignore_errors=True)
