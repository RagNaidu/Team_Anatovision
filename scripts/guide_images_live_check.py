"""Live end-to-end check as student1 with the REAL index and BullsAI, on throw-away copies of everything that gets written (users, sessions, chats, usage log, marks).
The real users.json is only read; student1's copy loses the Class 14 guide grant (and its lecture) so a 403 can be shown. A session is issued directly (no password needed).
Usage: python scripts/guide_images_live_check.py"""
import io
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
from PIL import Image
from fastapi.testclient import TestClient

tmp = Path(tempfile.mkdtemp(prefix="gi_live_"))
users = json.loads((ROOT / "data" / "users.json").read_text(encoding="utf-8"))
from app_api import catalog as _cat
_g14 = _cat.guide_by_id("class-14")["entry"]
_drop = {"Dissection Guide, Class 14", _g14.get("matched_lecture"), _g14.get("also_lecture")}
users["student1"]["allowed_lectures"] = [t for t in users["student1"]["allowed_lectures"] if t not in _drop]          # student1's COPY loses Class 14 and the lecture it follows
(tmp / "users.json").write_text(json.dumps(users))
shutil.copy(ROOT / "data" / "guide_annotations.db", tmp / "marks.db")
from src import auth, chat_store, guide_marks, guide_store, usage, web_fallback
from src.modes import qa
auth.USERS_PATH = tmp / "users.json"
guide_marks.DB_PATH = tmp / "marks.db"
chat_store.DB_PATH = tmp / "chats.db"
guide_store.DB_PATH = tmp / "guides.db"
usage.QUESTION_LOG_PATH = tmp / "q.jsonl"
usage.SETTINGS_PATH = tmp / "settings.json"
qa.FLAGS_PATH = tmp / "flags.jsonl"
web_fallback.CACHE_DIR = tmp / "web"
import os
os.environ["ANATOVISION_API_SESSIONS_PATH"] = str(tmp / "sessions.db")
from app_api.main import create_app
from app_api import catalog
from app_api.sessions import SessionStore
from src.modes import guide_slides as GS

out = []
say = lambda *a: (print(*a, flush=True), out.append(" ".join(str(x) for x in a)))
store = guide_marks.MarkStore()
g15 = catalog.guide_by_id("class-15")
st15 = GS.build_stations(GS.slides_of(g15["file"]), g15["entry"]["class_label"])
station = next(s for s in st15 if 3 in s["slides"])
# approve the OCR drafts of Class 15 in the COPY only, so a student's cards have marks to show
for m in store.list("class-15", None):
    pass
store.set_status("class-15", sorted({m["slide"] for m in store.list("class-15")}), "approved", "live-check")
n_drafts_real = sum(1 for m in guide_marks.MarkStore(ROOT / "data" / "guide_annotations.db").list("class-15") if m["status"] == "draft")
n_approved_real = sum(1 for m in guide_marks.MarkStore(ROOT / "data" / "guide_annotations.db").list("class-15") if m["status"] == "approved")
t0 = time.time()
app = create_app(warm_runtime=False)
with TestClient(app) as c:
    from src import service
    app.state.runtime = service.build_runtime()
    say(f"runtime ready in {time.time() - t0:.1f}s")
    token = SessionStore().create("student1")
    c.cookies.set("av_session", token) if False else None
    from app_api import config
    c.cookies.set(config.COOKIE_NAME, token)

    # 1 a granted station with its crops
    r = c.get("/api/guides/class-15/stations")
    say("GET class-15 stations:", r.status_code)
    s = next(x for x in r.json() if 3 in x["slides"])
    say(f"station {s['index'] + 1} '{s['title']}': {len(s['images'])} picture(s), slides {s['slides']}")
    for im in s["images"]:
        rr = c.get(im["url"])
        w, h = Image.open(io.BytesIO(rr.content)).size
        say(f"  slide {im['slide']} picture {im['crop']}: image {rr.status_code} {rr.headers['content-type']} {w}x{h}px (long side {max(w, h)}), thumb {c.get(im['thumb_url']).status_code}, approved marks sent: {len(im['marks'])}")
    # 2 no draft marks leak: every mark sent is approved in the DB
    approved_ids = {m["id"] for m in guide_marks.MarkStore().list("class-15", None, "approved")}
    sent = [m["id"] for x in r.json() for i in x["images"] for m in i["marks"]]
    say("every mark sent to the student is approved:", all(i in approved_ids for i in sent), f"({len(sent)} sent)")
    say(f"in the REAL marks database Class 15 has {n_approved_real} approved and {n_drafts_real} draft marks (nothing was approved there)")
    # 3 an ungranted guide
    r14 = c.get("/api/guides/class-14/stations")
    first = next(iter(__import__('src.guide_images', fromlist=['x']).meta("class-14")["slides"].items()))
    crop14 = next((int(n) for n, e in __import__('src.guide_images', fromlist=['x']).meta("class-14")["slides"].items() if e["crops"]), None)
    say("GET class-14 stations (not granted):", r14.status_code, "| its picture:", c.get(f"/api/guides/class-14/slides/{crop14}/crops/1/image").status_code)
    c.cookies.clear()
    say("same picture without signing in:", c.get(s["images"][0]["url"]).status_code, "| original slide:", c.get(f"/api/guides/class-15/slides/3/original").status_code)
    c.cookies.set(config.COOKIE_NAME, token)
    say("original (whole) slide as a student:", c.get("/api/guides/class-15/slides/3/original").status_code)
    # 4 a procedural chat question
    from src import llm
    try:
        llm.complete(llm.make_client(), "Say ok", [{"role": "user", "content": "ok?"}], 20, llm.default_model())
        gateway = True
    except Exception as e:
        gateway = False
        say("BullsAI gateway is NOT reachable from here (" + str(e)[:80] + "): the model-written answer and Explain simply cannot be run now.")
    q = {"question": "How do I dissect and reflect the anteromedial thigh? Give me the steps.", "length": "brief"}
    if gateway:
        chat = c.post("/api/chats").json()["id"]
        t1 = time.time()
        a = c.post("/api/ask", json={**q, "chat_id": chat})
        msg = a.json()
        say(f"POST /api/ask: {a.status_code} in {time.time() - t1:.1f}s")
        say("answer (first 400 chars):", msg["markdown"][:400].replace("\n", " | "))
        cards = msg["images"]
    else:
        # real retrieval from the live index for the same question, then the real card builder on the guide steps it found (the model's wording is the only thing missing)
        from app_api import guide_media
        rt = app.state.runtime
        res = rt.searcher.search(q["question"], k=8, allowed_lectures=json.loads((tmp / "users.json").read_text())["student1"]["allowed_lectures"], rerank=False)
        guide_hits = [h.chunk for h in res.hits if h.chunk["source_type"] == "dissection_guide"]
        say(f"retrieval found {len(res.hits)} passages, {len(guide_hits)} from dissection guides: " + "; ".join(qa.cite_for(h) for h in guide_hits[:5]))
        view = {"sources": [{"source_type": "dissection_guide", "cite": qa.cite_for(h), "crumb": qa.cite_for(h)} for h in guide_hits], "sources_list": [{"n": i + 1, "chunk": i} for i in range(len(guide_hits))],
                "cite_unit": {}, "units": []}
        md = "\n".join(f"{i + 1}. Step from the guide. [{i + 1}]" for i in range(len(guide_hits)))
        cards = guide_media.chat_images(view, md, json.loads((tmp / "users.json").read_text())["student1"]["allowed_lectures"])
    say(f"image cards: {len(cards)}")
    for im in cards:
        rr = c.get(im["url"])
        w, h = Image.open(io.BytesIO(rr.content)).size
        say(f"  card slide {im['slide']} pic {im['crop']} step {im['step']}: {rr.status_code} {w}x{h}, marks {len(im['marks'])}, all approved: {all(m['id'] in approved_ids for m in im['marks'])}")
    # 5 explain simply
    if gateway:
        ex = c.post(f"/api/guides/class-15/stations/{s['index']}/explain", json={"body_type": "more_fat"})
        say("Explain simply:", ex.status_code, ex.json().get("label") if ex.status_code == 200 else ex.json())
        if ex.status_code == 200:
            say("  ", ex.json()["text"])
(ROOT / "reports" / "guide_images_live_check.md").write_text("# Live check as student1 (real index and BullsAI, throw-away copies of everything written)\n\n```\n" + "\n".join(out) + "\n```\n", encoding="utf-8")
shutil.rmtree(tmp, ignore_errors=True)
