"""Swap the staged version 2 (data/staging_v2/) in as the live data, with a backup, and carry the knock-on effects. Reversible: `rollback`.

  .venv/bin/python scripts/revision_swap.py plan       what would change (grants, guide places) without touching anything
  .venv/bin/python scripts/revision_swap.py swap       back up the files it will change into data/archive/v1_<date>/, then replace them
  .venv/bin/python scripts/revision_swap.py rollback   put the backup back

Files replaced: data/processed/{sections,guide_slides,guide_chunks}.jsonl, guide_map_cache.json, data/dissection_guides_map.json, data/index/, reports/factcheck_all.json.
Files changed in place (backed up first): data/users.json (grants follow the renamed lectures and guides), data/guide_sessions.db (a student's place in a revised guide, by content).
Never touched: data/raw/** (the v1 files stay where they are), flags.jsonl, question_log.jsonl, verified_fixes.jsonl, chats.db, quizzes.db.
"""
import json
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import auth, guide_store  # noqa: E402
from src.ingest import guides as G  # noqa: E402
from src.ingest import revision as R  # noqa: E402
from src.ingest import stage as ST  # noqa: E402
from src.modes import guide_chat  # noqa: E402

STAGE = ROOT / "data" / "staging_v2"
ARCHIVE = ROOT / "data" / "archive" / f"v1_{date.today().isoformat()}"
REPLACED = [("data/processed/sections.jsonl", "sections"), ("data/processed/guide_slides.jsonl", "slides"), ("data/processed/guide_chunks.jsonl", "gchunks"),
            ("data/processed/guide_map_cache.json", "gcache"), ("data/dissection_guides_map.json", "map"), ("reports/factcheck_all.json", "factcheck")]
IN_PLACE = ["data/users.json", "data/guide_sessions.db"]
STATION_MATCH = 0.5          # a student's station is carried to the revised guide when the best revised station is at least this similar


def rmap():
    return json.loads((STAGE / "revision_map.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- grants
def new_grants(allowed, m, v1_lectures=None, v1_guide_labels=None, v2_lectures=None, v2_labels=None):
    """The revised names of what a student could open: each old lecture or guide maps to its revised match (same grant). A document that is brand new in the revision
    is granted to nobody until the instructor grants it. (The extra arguments are kept for older callers and ignored.) -> (new titles, titles that have no match)"""
    lec = {n["v1_title"]: n["v2_title"] for n in m["notes"] if n["v2_title"]}
    gl = {g["v1_label"]: g["v2_label"] for g in m["guides"] if g["v1_label"]}
    out, dropped = set(), []
    for t in set(allowed):
        if t in lec:
            out.add(lec[t])
        elif t in gl:
            out.add(gl[t])
        else:
            dropped.append(t)
    return sorted(out), sorted(dropped)


# ---------------------------------------------------------------- guide progress
def v2_guide_for_file(file):
    from app_api import catalog
    return next((g for g in catalog.guides() if g["file"] == file), None)


def station_texts(slides_path, file, class_label):
    from src.modes import guide_slides as GS
    rows = [json.loads(l) for l in Path(slides_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    return GS.build_stations([r for r in rows if r["file"] == file], class_label)


def carry_station(old_text, new_stations):
    """-> index of the revised station that says the same thing (or None)."""
    if not new_stations or not old_text.strip():
        return None
    sim = R.similarity_matrix([old_text], [s["text"] for s in new_stations])[0]
    j = int(sim.argmax())
    return j if float(sim[j]) >= STATION_MATCH else None


def plan_progress(m):
    """Compute (without writing) the new guide_history rows and guide_sessions rows. Must run BEFORE the swap (it reads the v1 catalog)."""
    from app_api import catalog
    pairs = {p["v1_file"]: p for p in m["guides"]}
    v1_by_id = {g["id"]: g for g in catalog.guides()}
    v1_entries = G.map_by_file()
    gs = guide_store.GuideStore()
    hist, sessions = [], []
    with sqlite3.connect(gs.path) as db:
        rows = db.execute("SELECT user, item, kind, ref, title, station, count, updated, body_type FROM guide_history").fetchall()
        sess = db.execute("SELECT user, guide, state, updated FROM guide_sessions").fetchall()
    with ST.use(STAGE):
        v2_guides = list(catalog.guides())
        v2_by_file = {g["file"]: g for g in v2_guides}
        v2_lec = {l["id"] for l in catalog.lectures()}
        for user, item, kind, ref, title, station, count, updated, bt in rows:
            if kind == "guide":
                g1 = v1_by_id.get(ref)
                p = pairs.get(g1["file"]) if g1 else None
                g2 = v2_by_file.get(p["v2_file"]) if p else None
                if not g2:
                    hist.append(("drop", user, item)); continue
                old_stations = station_texts(ROOT / "data" / "processed" / "guide_slides.jsonl", g1["file"], v1_entries[g1["file"]]["class_label"])
                new_stations = station_texts(STAGE / "processed" / "guide_slides.jsonl", g2["file"], g2["entry"]["class_label"])
                at = carry_station(old_stations[station]["text"], new_stations) if station < len(old_stations) else None
                notice = "" if at is not None else "This guide was updated. Your place could not be matched to the new stations, so you start again at station 1."
                new_title = f"Class {g2['class_number']} · {g2['title']}"
                hist.append(("put", user, f"guide:{g2['id']}", "guide", g2["id"], new_title, at if at is not None else 0, len(new_stations), bt, notice, updated, item))
            else:
                n = next((x for x in m["notes"] if x["v1_lecture_id"] == ref), None)
                new_ref = n["v2_lecture_id"] if n and n["v2_lecture_id"] in v2_lec else ""
                if not new_ref:
                    hist.append(("drop", user, item)); continue
                same = n["relation"] == "same document"
                hist.append(("put", user, f"lecture:{new_ref}", "lecture", new_ref, title, station if same else 0, count, bt,
                             "" if same else "These notes were revised. Your place could not be matched, so you start again at station 1.", updated, item))
        for user, guide_file, state, updated in sess:
            p = pairs.get(guide_file)
            g2 = v2_by_file.get(p["v2_file"]) if p else None
            old = json.loads(state)
            if not g2:
                sessions.append(("drop", user, guide_file)); continue
            old_steps = guide_chat.build_steps([r for r in (json.loads(l) for l in (ROOT / "data" / "processed" / "guide_slides.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()) if r["file"] == guide_file], old["class_label"])
            new_steps = guide_chat.build_steps([r for r in (json.loads(l) for l in (STAGE / "processed" / "guide_slides.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()) if r["file"] == g2["file"]], g2["entry"]["class_label"])
            pos = next((s for s in old_steps if s["id"] == old.get("pos")), None)
            at = carry_station(pos["text"], new_steps) if pos else None
            if at is None:
                sessions.append(("drop", user, guide_file)); continue
            st = guide_chat.new_state(g2["entry"], old.get("body_type", ""))
            st.update(started=True, pos=new_steps[at]["id"], visited=[new_steps[at]["id"]])
            sessions.append(("put", user, g2["file"], st, updated, guide_file))
    return hist, sessions


# ---------------------------------------------------------------- the commands
def cmd_plan():
    m = rmap()
    hist, sessions = plan_progress(m)
    users = json.loads((ROOT / "data" / "users.json").read_text(encoding="utf-8"))
    print("guide_history:", [(h[0], h[1], h[2], "->", h[3] if h[0] == "drop" else h[2], h[6] if h[0] == "put" and h[3] == "guide" else "", h[9] if h[0] == "put" else "") for h in hist])
    print("guide_sessions:", [(s[0], s[1], s[2]) for s in sessions])
    with ST.use(STAGE):
        from app_api import catalog
        v2_lectures = [l["title"] for l in catalog.lectures()]
        v2_labels = [g["label"] for g in catalog.guides()]
    from app_api import catalog
    v1_lectures, v1_labels = [l["title"] for l in catalog.lectures()], [g["label"] for g in catalog.guides()]
    for name, u in users.items():
        if u.get("role") == "student":
            new, dropped = new_grants(u.get("allowed_lectures", []), m, v1_lectures, v1_labels, v2_lectures, v2_labels)
            print(f"grants {name}: {len(u.get('allowed_lectures', []))} -> {len(new)}; dropped {dropped}")


def backup():
    ARCHIVE.mkdir(parents=True, exist_ok=False)
    for rel, _ in REPLACED:
        src = ROOT / rel
        if src.exists():
            (ARCHIVE / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, ARCHIVE / rel)
    shutil.copytree(ROOT / "data" / "index", ARCHIVE / "data" / "index")
    for rel in IN_PLACE:
        if (ROOT / rel).exists():
            (ARCHIVE / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, ARCHIVE / rel)
    (ARCHIVE / "MANIFEST.txt").write_text("Version 1 of the lecture notes index, guides, guide map, fact-check report, grants and guide progress, saved before the revised notes were swapped in.\n"
                                          "Restore with: .venv/bin/python scripts/revision_swap.py rollback\nThe v1 source files are still in data/raw/notes and data/raw/dissection_guides.\n")
    print("backup:", ARCHIVE.relative_to(ROOT))


def cmd_swap():
    m = rmap()
    for rel, key in REPLACED:
        if not ST.layout(STAGE)[key].exists():
            sys.exit(f"stage is incomplete: {key} is missing")
    if not (STAGE / "index" / "chunks.jsonl").exists():
        sys.exit("stage is incomplete: the index is missing")
    from app_api import catalog
    v1_lectures, v1_labels = [l["title"] for l in catalog.lectures()], [g["label"] for g in catalog.guides()]
    hist, sessions = plan_progress(m)                            # reads the v1 catalog: before the files change
    backup()
    L = ST.layout(STAGE)
    for rel, key in REPLACED:
        shutil.copy2(L[key], ROOT / rel)
    shutil.rmtree(ROOT / "data" / "index")
    shutil.copytree(L["index"], ROOT / "data" / "index")
    catalog._cache.clear()
    # grants
    catalog._cache.clear()
    v2_lectures, v2_labels = [l["title"] for l in catalog.lectures()], [g["label"] for g in catalog.guides()]
    users = auth.load_users()
    for name, u in users.items():
        if u.get("role") == "student":
            new, dropped = new_grants(u.get("allowed_lectures", []), m, v1_lectures, v1_labels, v2_lectures, v2_labels)
            u["allowed_lectures"] = new
            print(f"grants {name}: -> {len(new)} items" + (f"; dropped {dropped}" if dropped else ""))
    auth.save_users(users)
    # guide progress
    gs = guide_store.GuideStore()
    with sqlite3.connect(gs.path) as db:
        for h in hist:
            if h[0] == "drop":
                db.execute("DELETE FROM guide_history WHERE user = ? AND item = ?", (h[1], h[2]))
        for h in hist:
            if h[0] == "put":
                _, user, item, kind, ref, title, station, count, bt, notice, updated, old_item = h
                db.execute("DELETE FROM guide_history WHERE user = ? AND item = ?", (user, old_item))
                have = db.execute("SELECT station FROM guide_history WHERE user = ? AND item = ?", (user, item)).fetchone()
                if have and not notice:
                    station = max(station, have[0])
                db.execute("INSERT OR REPLACE INTO guide_history (user, item, kind, ref, title, station, count, updated, body_type, notice) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (user, item, kind, ref, title, station, count, updated, bt or "", notice))
        for s in sessions:
            if s[0] == "drop":
                db.execute("DELETE FROM guide_sessions WHERE user = ? AND guide = ?", (s[1], s[2]))
            else:
                _, user, file, st, updated, old_file = s
                db.execute("DELETE FROM guide_sessions WHERE user = ? AND guide = ?", (user, old_file))
                db.execute("INSERT OR REPLACE INTO guide_sessions (user, guide, state, updated) VALUES (?, ?, ?, ?)", (user, file, json.dumps(guide_store.student_safe(st)), updated))
        db.commit()
    print(f"guide_history rows: {sum(h[0] == 'put' for h in hist)} moved ({sum(1 for h in hist if h[0] == 'put' and h[9])} reset with a notice), {sum(h[0] == 'drop' for h in hist)} dropped; "
          f"guide_sessions: {sum(s[0] == 'put' for s in sessions)} moved, {sum(s[0] == 'drop' for s in sessions)} reset")
    print("swapped. Restore with: scripts/revision_swap.py rollback")


def cmd_rollback():
    if not ARCHIVE.exists():
        sys.exit(f"no backup at {ARCHIVE}")
    for rel, _ in REPLACED:
        if (ARCHIVE / rel).exists():
            shutil.copy2(ARCHIVE / rel, ROOT / rel)
    shutil.rmtree(ROOT / "data" / "index")
    shutil.copytree(ARCHIVE / "data" / "index", ROOT / "data" / "index")
    for rel in IN_PLACE:
        if (ARCHIVE / rel).exists():
            shutil.copy2(ARCHIVE / rel, ROOT / rel)
    print("rolled back to", ARCHIVE.relative_to(ROOT))


if __name__ == "__main__":
    {"plan": cmd_plan, "swap": cmd_swap, "rollback": cmd_rollback}[sys.argv[1] if len(sys.argv) > 1 else "plan"]()
