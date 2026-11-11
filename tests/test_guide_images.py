"""Cropped guide pictures and step-by-step marks: crop planning from pptx shapes (several pictures, labels kept, step text and footers left out, text-only slides, flattened slides,
rotated shapes), resolution, coordinates in the crop, re-mapping older marks, draft marks never reach students, access (grants, instructor-only original slide, low-confidence crops
hidden until checked), the editor API, OCR drafts, chat image cards, "Explain simply". Images and databases are throw-away; the real guides are only read."""
import json

import pytest
from PIL import Image, ImageDraw

from app_api import catalog, guide_media
from src import auth
from src import guide_autodraft as AD
from src import guide_crops as GC
from src import guide_images as GI
from src import guide_marks as GM
from src import guide_ocr_marks as OM
from src.modes import guide_slides as GS

G17 = "class-17"
G26 = "class-26"


def guide(gid):
    return catalog.guide_by_id(gid)


def stations(gid):
    g = guide(gid)
    return GS.build_stations(GS.slides_of(g["file"]), g["entry"]["class_label"])


def picture_slides(gid):
    in_station = {n for st in stations(gid) for n in st["slides"]}
    return sorted({r["n"] for r in GS.slides_of(guide(gid)["file"]) if (r.get("n_pictures") or r.get("n_diagrams")) and r["n"] in in_station})


def visual_station(gid):
    vis = set(picture_slides(gid))
    return next(s for s in stations(gid) if any(n in vis for n in s["slides"]) and not s["image_only"] and len([n for n in s["slides"] if n in vis]) >= 1)


@pytest.fixture
def imgs(tmp_path, monkeypatch):
    """A throw-away image folder: every picture slide of two guides gets one small crop (the first picture slide of class 17 gets two, the last one a low-confidence crop)."""
    monkeypatch.setattr(GI, "IMG_DIR", tmp_path / "imgs")
    for gid in (G17, G26):
        d = GI.guide_dir(gid)
        d.mkdir(parents=True)
        info = {}
        vis = picture_slides(gid)
        for r in GS.slides_of(guide(gid)["file"]):
            n = r["n"]
            e = {"w": 1280, "h": 720, "status": "none", "crops": []}
            if n in vis or any(s["image_only"] and n in s["slides"] for s in stations(gid)):
                ks = 2 if gid == G17 and n == vis[0] else 1
                for k in range(1, ks + 1):
                    Image.new("RGB", (160, 200), "white").save(GI.crop_path(gid, n, k), "WEBP")
                    Image.new("RGB", (40, 50), "white").save(GI.crop_path(gid, n, k, True), "WEBP")
                    low = gid == G17 and n == vis[-1]
                    e["crops"].append({"k": k, "box": [0.5, 0.0, 0.9, 0.9], "w": 160, "h": 200, "confidence": "low" if low else "high", "why": "step text overlaps the picture" if low else ""})
                e["status"] = "review" if gid == G17 and n == vis[-1] else "auto"
            Image.new("RGB", (128, 72), "white").save(GI.original_path(gid, n))
            info[str(n)] = e
        (d / "meta.json").write_text(json.dumps({"mode": "render", "version": 2, "slides": info}))
    return tmp_path / "imgs"


# ---- pictures belong to the right stations ----------------------------------------------------------------------------------------------

def test_a_station_gets_the_cropped_pictures_of_its_own_slides_in_order(imgs):
    g = guide(G17)
    first_vis = picture_slides(G17)[0]
    s = next(x for x in stations(G17) if first_vis in x["slides"])
    out = guide_media.station_images(g, s)
    assert out[0]["slide"] == first_vis and [i["crop"] for i in out if i["slide"] == first_vis] == [1, 2]
    one = out[0]
    assert one["url"] == f"/api/guides/{G17}/slides/{first_vis}/crops/1/image" and one["thumb_url"].endswith("/crops/1/thumb")
    assert one["caption"].startswith(f"Slide {first_vis} · Dr. Inglis's dissection guide") and "picture 1 of 2" in one["alt"]
    assert all(i["slide"] in s["slides"] for i in out)


def test_an_image_only_station_shows_its_picture_instead_of_see_slide_n(imgs):
    g = guide(G26)
    st = next(s for s in stations(G26) if s["image_only"])
    out = guide_media.station_images(g, st)
    assert st["steps"] == [] and [i["slide"] for i in out] == st["slides"]


def test_a_low_confidence_crop_is_hidden_from_students_until_the_instructor_checks_it(imgs):
    g = guide(G17)
    last = picture_slides(G17)[-1]
    s = next(x for x in stations(G17) if last in x["slides"])
    assert last not in [i["slide"] for i in guide_media.station_images(g, s)]
    admin = guide_media.station_images(g, s, student=False)
    low = next(i for i in admin if i["slide"] == last)
    assert low["confidence"] == "low" and low["reviewed"] is False and low["original_url"].endswith(f"/slides/{last}/original")
    GM.MarkStore().set_reviewed(G17, last, 1, True, "Dr. Inglis")
    assert last in [i["slide"] for i in guide_media.station_images(g, s)]


def test_the_image_path_cannot_escape_the_image_folder():
    with pytest.raises(ValueError):
        GI.guide_dir("../etc")
    with pytest.raises(ValueError):
        GI.crop_path("class-17/../x", 1)


# ---- planning a crop from the pptx shapes ----------------------------------------------------------------------------------------------

def pptx_slide(shapes):
    """A one-slide deck. shapes = [("pic", l, t, w, h) | ("text", l, t, w, h, text) | ("line", x0, y0, x1, y1) | ("oval", l, t, w, h)] in slide fractions."""
    import io
    from pptx import Presentation
    from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
    prs = Presentation()
    sl = prs.slides.add_slide(prs.slide_layouts[6])
    W, H = prs.slide_width, prs.slide_height
    png = io.BytesIO()
    Image.new("RGB", (40, 40), "red").save(png, "PNG")
    for s in shapes:
        if s[0] == "pic":
            png.seek(0)
            sl.shapes.add_picture(png, int(s[1] * W), int(s[2] * H), int(s[3] * W), int(s[4] * H))
        elif s[0] == "text":
            sl.shapes.add_textbox(int(s[1] * W), int(s[2] * H), int(s[3] * W), int(s[4] * H)).text_frame.text = s[5]
        elif s[0] == "line":
            sl.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, int(s[1] * W), int(s[2] * H), int(s[3] * W), int(s[4] * H))
        elif s[0] == "oval":
            o = sl.shapes.add_shape(MSO_SHAPE.OVAL, int(s[1] * W), int(s[2] * H), int(s[3] * W), int(s[4] * H))
            o.fill.background()
    return sl, (W, H)


STEPS = ["Transect the tendons of the sartorius and gracilis muscles from their distal attachments.", "Identify the tibial collateral ligament of the knee."]


def test_the_crop_covers_the_picture_and_its_labels_but_not_step_text_or_footer():
    sl, size = pptx_slide([("text", 0.05, 0.12, 0.40, 0.55, "1. Transect the tendons of the sartorius and gracilis muscles from their distal attachments."),
                           ("pic", 0.55, 0.10, 0.35, 0.75),
                           ("text", 0.43, 0.40, 0.12, 0.06, "Pes anserinus"), ("line", 0.52, 0.43, 0.62, 0.45),
                           ("text", 0.3, 0.95, 0.4, 0.04, "PAS407 – Class 17 Dissection Guide")])
    plan = GC.plan_slide(sl, size, STEPS)
    assert plan["status"] == "auto" and len(plan["crops"]) == 1
    x0, y0, x1, y1 = plan["crops"][0]["box"]
    assert 0.40 <= x0 <= 0.45 and 0.08 <= y0 <= 0.11 and 0.90 <= x1 <= 0.94 and 0.84 <= y1 <= 0.88        # the label box (left of the picture) is inside, the step text (x < 0.45) is not
    assert y1 < 0.93 and plan["crops"][0]["confidence"] == "high"


def test_two_separate_pictures_become_two_crops_in_reading_order():
    sl, size = pptx_slide([("pic", 0.55, 0.55, 0.30, 0.35), ("pic", 0.10, 0.10, 0.30, 0.35)])
    plan = GC.plan_slide(sl, size, STEPS)
    assert len(plan["crops"]) == 2 and plan["crops"][0]["box"][1] < plan["crops"][1]["box"][1]
    sl2, size2 = pptx_slide([("pic", 0.10, 0.10, 0.30, 0.35), ("pic", 0.39, 0.12, 0.30, 0.30)])
    assert len(GC.plan_slide(sl2, size2, STEPS)["crops"]) == 1                                        # touching pictures are one figure


def test_text_only_slides_and_logo_slides_have_no_picture():
    sl, size = pptx_slide([("text", 0.1, 0.1, 0.8, 0.5, "1. Transect the tendons of the sartorius and gracilis muscles from their distal attachments.")])
    assert GC.plan_slide(sl, size, STEPS) == {"crops": [], "flat": False, "status": "none"}
    sl2, size2 = pptx_slide([("pic", 0.1, 0.1, 0.3, 0.4), ("text", 0.5, 0.45, 0.4, 0.1, "End of Dissection")])
    assert GC.plan_slide(sl2, size2, STEPS)["status"] == "none"


def test_step_text_over_the_picture_makes_the_crop_low_confidence():
    sl, size = pptx_slide([("pic", 0.40, 0.10, 0.50, 0.75), ("text", 0.42, 0.50, 0.45, 0.3, "2. Identify the tibial collateral ligament of the knee and note its attachments.")])
    plan = GC.plan_slide(sl, size, STEPS)
    assert plan["crops"][0]["confidence"] == "low" and "step text" in plan["crops"][0]["why"] and plan["status"] == "review"


def test_a_flattened_slide_is_found_by_image_analysis_with_step_text_painted_out(monkeypatch):
    sl, size = pptx_slide([("pic", 0.0, 0.0, 1.0, 1.0)])
    plan = GC.plan_slide(sl, size, STEPS)
    assert plan["flat"] is True and plan["crops"][0]["confidence"] == "low"
    img = Image.new("RGB", (1000, 600), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([600, 80, 920, 480], fill=(200, 90, 80))                      # the illustration
    d.rectangle([40, 100, 420, 140], fill="black")                             # a line of step text
    long_line = {"text": "1. Transect the tendons of the sartorius and gracilis muscles", "box": [0.04, 0.16, 0.42, 0.24], "conf": 1.0}
    label = {"text": "Pes anserinus", "box": [0.50, 0.30, 0.59, 0.34], "conf": 1.0}
    monkeypatch.setattr(GC.ocr, "read", lambda image, level="accurate": [long_line, label])
    box, note = GC.flat_region(img, STEPS)
    assert box[0] > 0.45 and box[2] < 0.97 and box[1] < 0.2 and box[3] > 0.78 and note == ""             # the illustration plus the label next to it, not the text on the left


def test_the_crop_is_rendered_large_enough():
    for box in ([0.5, 0.0, 0.9, 0.9], [0.0, 0.0, 1.0, 1.0], [0.2, 0.2, 0.3, 0.3]):
        wp = GC.page_width_for(box, 0.5625)
        long_side = max((box[2] - box[0]) * wp, (box[3] - box[1]) * wp * 0.5625)
        assert long_side >= 1600 or wp == GC.MAX_PAGE_W


# ---- coordinates, remapping, rotation --------------------------------------------------------------------------------------------------

def test_marks_scale_to_any_display_size():
    arrow = GM.clean_geom("arrow", {"from": [0.25, 0.5], "to": [0.75, 0.5]})
    assert GM.scale_geom("arrow", arrow, 400, 200) == {"from": [100.0, 100.0], "to": [300.0, 100.0]}
    assert GM.scale_geom("arrow", arrow, 1280, 720) == {"from": [320.0, 360.0], "to": [960.0, 360.0]}
    ell = GM.clean_geom("highlight", {"cx": 0.5, "cy": 0.5, "rx": 0.1, "ry": 0.2})
    assert GM.scale_geom("highlight", ell, 1000, 500) == {"cx": 500.0, "cy": 250.0, "rx": 100.0, "ry": 100.0}


@pytest.mark.parametrize("kind,geom", [("arrow", {"from": [0, 0], "to": [1.2, 0]}), ("arrow", {"from": [0.5, 0.5], "to": [0.5, 0.5]}), ("cut", {"points": [[0, 0]]}),
                                       ("highlight", {"cx": 0.5, "cy": 0.5, "rx": 0, "ry": 0.1}), ("label", {"x": "a", "y": 1}), ("squiggle", {})])
def test_bad_geometry_is_refused(kind, geom):
    with pytest.raises(GM.MarkError):
        GM.clean_geom(kind, geom)


def test_older_marks_move_onto_the_cropped_pictures_and_the_ones_outside_are_flagged_drafts(tmp_path):
    s = GM.MarkStore(tmp_path / "m.db")
    crops = lambda n: [{"k": 1, "box": [0.5, 0.0, 0.9, 1.0]}]
    inside = s.create(G17, 6, "label", {"x": 0.7, "y": 0.5}, "Pes anserinus", 1, "x", status="approved")
    partly = s.create(G17, 6, "arrow", {"from": [0.45, 0.5], "to": [0.7, 0.5]}, "", 1, "x", status="approved")
    outside = s.create(G17, 6, "label", {"x": 0.1, "y": 0.5}, "On the step text", 1, "x", status="approved")
    for m in (inside, partly, outside):                                      # these were made in SLIDE coordinates, before the slides were cropped
        with s._db() as db:
            db.execute("UPDATE marks SET space = 'slide' WHERE id = ?", (m["id"],))
    out = s.remap_to_crops(G17, crops)
    assert out == {"moved": 2, "flagged": 2}
    a, b, c = s.get(inside["id"]), s.get(partly["id"]), s.get(outside["id"])
    assert a["geom"] == {"x": 0.5, "y": 0.5} and a["status"] == "approved" and a["flag"] == "" and a["space"] == "crop" and a["crop"] == 1
    assert b["status"] == "draft" and "Partly outside" in b["flag"] and b["geom"]["from"][0] == 0.0
    assert c["status"] == "draft" and "Outside" in c["flag"] and c["space"] == "slide"
    shown = GM.student_marks(s.list(G17, [6]))
    assert [m["text"] for m in shown] == ["Pes anserinus"] and shown[0]["crop"] == 1                  # only the approved, unflagged, converted mark reaches a student
    assert s.set_status(G17, [6], "approved") == 0                                                       # a bulk approve never approves flagged marks
    s.update(c["id"], {"geom": {"x": 0.3, "y": 0.4}}, "x")
    assert s.get(c["id"])["flag"] == "" and s.get(c["id"])["space"] == "crop"


def test_an_older_database_is_migrated_and_its_marks_wait_in_slide_coordinates(tmp_path):
    import sqlite3
    p = tmp_path / "old.db"
    with sqlite3.connect(p) as db:
        db.executescript("CREATE TABLE marks (id TEXT PRIMARY KEY, guide_id TEXT NOT NULL, slide INTEGER NOT NULL, kind TEXT NOT NULL, geom TEXT NOT NULL, text TEXT NOT NULL DEFAULT '', step INTEGER,"
                         " ord INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'draft', author TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1, source TEXT NOT NULL DEFAULT 'manual',"
                         " created REAL NOT NULL, updated REAL NOT NULL);"
                         "INSERT INTO marks (id, guide_id, slide, kind, geom, status, created, updated) VALUES ('m-1', 'class-17', 6, 'label', '{\"x\": 0.5, \"y\": 0.5}', 'approved', 1, 1);")
    s = GM.MarkStore(p)
    m = s.get("m-1")
    assert m["space"] == "slide" and m["crop"] == 1 and GM.student_marks([m]) == []              # not shown to a student until it is moved onto a crop


def test_rotated_lines_arrows_and_ellipses_are_drafted_in_the_right_place():
    sl, size = pptx_slide([("line", 0.2, 0.5, 0.6, 0.5)])
    line = sl.shapes[0]
    line.rotation = 90.0                                                      # a horizontal line turned a quarter turn about its centre becomes vertical
    ln = line._element.find(f".//{AD.A}ln") or line.line._get_or_add_ln()
    from lxml import etree
    etree.SubElement(ln, f"{AD.A}tailEnd").set("type", "triangle")
    marks = AD.draft_slide(sl, size, [])
    arrow = next(m for m in marks if m["kind"] == "arrow")
    (fx, fy), (tx, ty) = arrow["geom"]["from"], arrow["geom"]["to"]
    assert abs(fx - 0.4) < 0.01 and abs(tx - 0.4) < 0.01 and abs(fy - tx) < 1 and abs(fy - 0.5) > 0.1 and abs(ty - fy) > 0.15        # vertical, about x = 0.4 (the shape's centre)
    sl2, size2 = pptx_slide([("oval", 0.3, 0.4, 0.4, 0.1)])
    sl2.shapes[0].rotation = 90.0
    hi = next(m for m in AD.draft_slide(sl2, size2, []) if m["kind"] == "highlight")["geom"]
    assert hi["rx"] < hi["ry"]                                                # a quarter turn swaps the two radii (it was wider than tall)


def test_the_autodraft_keeps_marks_on_pictures_in_crop_coordinates_and_never_approves(tmp_path):
    sl, size = pptx_slide([("pic", 0.5, 0.1, 0.4, 0.8), ("text", 0.45, 0.4, 0.12, 0.06, "Pes anserinus")])
    marks = AD.draft_slide(sl, size, ["Transect the tendons (pes anserinus)."])
    crops = [{"k": 1, "box": [0.44, 0.08, 0.92, 0.92]}]
    mine = AD.to_crops(marks, crops)
    assert len(mine) == 1 and mine[0][0] == 1 and 0.0 <= mine[0][1]["geom"]["x"] <= 0.3 and mine[0][1]["step"] == 0
    s = GM.MarkStore(tmp_path / "m.db")
    made = s.replace_auto_drafts(G17, 5, [m for _k, m in mine], crop=1, source="auto")
    assert {m["status"] for m in made} == {"draft"} and GM.student_marks(s.list(G17, [5])) == []
    assert AD.to_crops(marks, [{"k": 1, "box": [0.0, 0.0, 0.3, 0.3]}]) == []                          # outside every crop: dropped


# ---- OCR drafts ------------------------------------------------------------------------------------------------------------------------

def test_ocr_labels_become_draft_pins_and_a_leader_line_gives_an_arrow(monkeypatch):
    img = Image.new("RGB", (800, 600), "white")
    d = ImageDraw.Draw(img)
    d.line([(285, 300), (520, 360)], fill="black", width=4)                   # a leader line from the label to the structure
    lines = [{"text": "Pes anserinus", "box": [0.10, 0.45, 0.36, 0.55], "conf": 0.98},
             {"text": "Medial Collateral Ligament", "box": [0.10, 0.80, 0.50, 0.86], "conf": 0.95},
             {"text": "1. Transect the tendons of the sartorius and gracilis muscles", "box": [0.1, 0.1, 0.9, 0.16], "conf": 1.0},
             {"text": "Fig 3", "box": [0.9, 0.9, 0.95, 0.95], "conf": 0.9}, {"text": "Pes anserinus", "box": [0.1, 0.45, 0.36, 0.55], "conf": 0.2}]
    monkeypatch.setattr(OM.ocr, "read", lambda image, level="accurate": lines)
    vocab = OM.vocabulary("the pes anserinus and the tibial collateral ligament")
    marks, info = OM.draft_picture(img, ["Transect the tendons (pes anserinus).", "Identify the tibial collateral ligament."], vocab)
    pins = [m for m in marks if m["kind"] == "label"]
    assert [p["text"] for p in pins] == ["Pes anserinus", "Medial Collateral Ligament"] and pins[0]["step"] == 0 and pins[1]["step"] == 1
    assert info["step_text_lines"] == 1
    arrows = [m for m in marks if m["kind"] == "arrow"]
    assert len(arrows) == 1 and arrows[0]["geom"]["to"][0] > arrows[0]["geom"]["from"][0] and abs(arrows[0]["geom"]["to"][0] - 520 / 800) < 0.06
    again, _ = OM.draft_picture(img, ["Transect the tendons (pes anserinus)."], vocab, existing=[(0.2, 0.5, "Pes anserinus")])
    assert all(m["text"] != "Pes anserinus" for m in again if m["kind"] == "label")                  # not duplicated over a label the slide already had


# ---- draft marks never reach students; steps and marks stay in sync ------------------------------------------------------------------------

def test_only_approved_marks_reach_students_and_an_edit_sends_a_mark_back_to_draft():
    s = GM.MarkStore()
    a = s.create(G17, 6, "label", {"x": 0.5, "y": 0.5}, "Pes anserinus", 1, "Dr. Inglis")
    s.create(G17, 6, "arrow", {"from": [0.1, 0.1], "to": [0.4, 0.4]}, "", 1, "Dr. Inglis")
    s.replace_auto_drafts(G17, 6, [{"kind": "highlight", "geom": {"cx": 0.5, "cy": 0.5, "rx": 0.1, "ry": 0.1}, "step": 0}], source="ocr")
    assert GM.student_marks(s.list(G17, [6])) == []
    s.set_status(G17, [6], "approved", "Dr. Inglis")
    shown = GM.student_marks(s.list(G17, [6]))
    assert len(shown) == 3 and set(shown[0]) == {"id", "slide", "crop", "kind", "geom", "text", "step", "n"}
    s.update(a["id"], {"text": "Pes anserinus (changed)"}, "Dr. Inglis")
    assert [m["text"] for m in GM.student_marks(s.list(G17, [6])) if m["kind"] == "label"] == []


def test_auto_and_ocr_drafts_are_redone_separately_without_touching_approved_or_hand_made_marks():
    s = GM.MarkStore()
    s.replace_auto_drafts(G17, 3, [{"kind": "label", "geom": {"x": 0.2, "y": 0.2}, "text": "Femur", "step": None}], source="auto")
    s.replace_auto_drafts(G17, 3, [{"kind": "label", "geom": {"x": 0.4, "y": 0.4}, "text": "Tibia", "step": None}], source="ocr")
    hand = s.create(G17, 3, "label", {"x": 0.3, "y": 0.3}, "Mine", None, "Dr. Inglis")
    s.set_status(G17, [3], "approved")
    s.replace_auto_drafts(G17, 3, [{"kind": "label", "geom": {"x": 0.9, "y": 0.9}, "text": "New", "step": None}], source="ocr")
    assert sorted(m["text"] for m in s.list(G17, [3])) == ["Femur", "Mine", "New", "Tibia"] and s.get(hand["id"])["status"] == "approved"


def test_a_label_is_matched_to_the_step_that_names_it():
    steps = ["Review the bony architecture of the knee.", "Transect the tendons of the sartorius, gracilis, and semitendinosus (pes anserinus).", "Identify the tibial collateral ligament."]
    assert AD.match_step("Pes anserinus", steps) == 1 and AD.match_step("Medial Collateral Ligament", steps) == 2 and AD.match_step("Sartorius fascia lata", steps) is None


# ---- the API --------------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def api(tmp_path, monkeypatch, imgs):
    from fastapi.testclient import TestClient
    from app_api.main import create_app
    from app_api.routers import auth as auth_router
    monkeypatch.setattr(auth, "USERS_PATH", tmp_path / "users.json")
    auth.save_users({"prof": auth.new_record("Prof", "professor", "password-long-1"),
                     "s17": auth.new_record("S17", "student", "password-long-1", ["Dissection Guide, Class 17"]),
                     "none": auth.new_record("None", "student", "password-long-1", [])})
    monkeypatch.setenv("ANATOVISION_API_SESSIONS_PATH", str(tmp_path / "sessions.db"))
    auth_router._fails.clear()
    auth._fails.clear()
    app = create_app(warm_runtime=False)
    with TestClient(app) as c:
        yield c


def login(c, u):
    c.post("/api/auth/logout")
    assert c.post("/api/auth/login", json={"username": u, "password": "password-long-1"}).status_code == 200


def high_slide():
    return picture_slides(G17)[0]


def test_pictures_are_served_only_to_users_who_may_open_the_guide(api):
    n = high_slide()
    url = f"/api/guides/{G17}/slides/{n}/crops/1/image"
    assert api.get(url).status_code == 401                                    # not signed in: there is no public URL
    login(api, "none")
    assert api.get(url).status_code == 403 and api.get(url.replace("image", "thumb")).status_code == 403
    login(api, "s17")
    r = api.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp" and r.content[:4] == b"RIFF"
    assert "private" in r.headers["cache-control"] and "noindex" in r.headers["x-robots-tag"]
    assert api.get(url.replace("image", "thumb")).status_code == 200
    assert api.get(f"/api/guides/{G26}/slides/1/crops/1/image").status_code == 403                  # a guide the student has no grant for
    assert api.get(f"/api/guides/{G17}/slides/9999/crops/1/image").status_code == 404
    assert api.get(f"/api/guides/{G17}/slides/{n}/crops/9/image").status_code == 404
    login(api, "prof")
    assert api.get(f"/api/guides/{G26}/slides/{picture_slides(G26)[0]}/crops/1/image").status_code == 200       # an instructor may open every guide


def test_the_whole_original_slide_is_for_instructors_only(api):
    n = high_slide()
    url = f"/api/guides/{G17}/slides/{n}/original"
    assert api.get(url).status_code == 401
    login(api, "s17")
    assert api.get(url).status_code == 403                                    # not even a student who may open the guide
    login(api, "prof")
    r = api.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert api.get(f"/api/guides/{G17}/slides/{n}/image").status_code in (404, 405)                       # the old whole-slide route is gone


def test_a_low_confidence_crop_is_404_for_a_student_until_the_instructor_checks_it(api):
    last = picture_slides(G17)[-1]
    url = f"/api/guides/{G17}/slides/{last}/crops/1/image"
    login(api, "s17")
    assert api.get(url).status_code == 404
    login(api, "prof")
    assert api.get(url).status_code == 200
    assert api.post(f"/api/admin/guides/{G17}/slides/{last}/crops/1/review", json={"ok": True}).status_code == 200
    login(api, "s17")
    assert api.get(url).status_code == 200
    login(api, "prof")
    assert api.post(f"/api/admin/guides/{G17}/slides/{last}/crops/1/review", json={"ok": False}).status_code == 200
    login(api, "s17")
    assert api.get(url).status_code == 404


def test_station_objects_carry_pictures_and_only_approved_marks(api):
    n = high_slide()
    st = next(x for x in stations(G17) if n in x["slides"])
    s = GM.MarkStore()
    ok = s.create(G17, n, "arrow", {"from": [0.1, 0.1], "to": [0.3, 0.3]}, "", 0, "x")
    s.set_status(G17, [n], "approved")
    s.create(G17, n, "label", {"x": 0.5, "y": 0.5}, "Draft pin", 0, "x")
    s.update(ok["id"], {"text": "edited"}, "x")                                # edited -> back to draft
    s.create(G17, n, "highlight", {"cx": 0.4, "cy": 0.4, "rx": 0.1, "ry": 0.1}, "", 0, "x", status="approved")
    s.create(G17, n, "label", {"x": 0.7, "y": 0.2}, "On the second picture", 0, "x", status="approved", crop=2)
    login(api, "s17")
    body = api.get(f"/api/guides/{G17}/stations").json()
    mine = next(b for b in body if b["index"] == st["n"] - 1)
    im1 = next(i for i in mine["images"] if i["slide"] == n and i["crop"] == 1)
    im2 = next(i for i in mine["images"] if i["slide"] == n and i["crop"] == 2)
    assert [m["kind"] for m in im1["marks"]] == ["highlight"] and [m["text"] for m in im2["marks"]] == ["On the second picture"]
    assert json.dumps(body).count("Draft pin") == 0 and all("confidence" not in i for b in body for i in b["images"])
    assert all(set(m) == {"id", "slide", "crop", "kind", "geom", "text", "step", "n"} for b in body for i in b["images"] for m in i["marks"])


def test_the_annotation_editor_api_is_instructor_only_and_saves_edits_approves_and_flags(api):
    n = high_slide()
    st = next(x for x in stations(G17) if n in x["slides"])
    base = f"/api/admin/guides/{G17}"
    login(api, "s17")
    for method, url, body in [("get", f"{base}/annotations", None), ("post", f"{base}/marks", {"slide": n, "kind": "label", "geom": {"x": .5, "y": .5}, "text": "x"}),
                              ("put", f"{base}/marks/m-1", {"text": "x"}), ("delete", f"{base}/marks/m-1", None), ("post", f"{base}/stations/0/approve", {"approve": True}),
                              ("post", f"{base}/marks/reorder", {"slide": 1, "ids": []}), ("post", f"{base}/slides/{n}/crops/1/review", {"ok": True})]:
        r = getattr(api, method)(url, **({"json": body} if body is not None else {}))
        assert r.status_code == 403, (method, url)
    login(api, "prof")
    made = api.post(f"{base}/marks", json={"slide": n, "crop": 1, "kind": "arrow", "geom": {"from": [0.1, 0.1], "to": [0.4, 0.3]}, "step": 0})
    assert made.status_code == 200 and made.json()["status"] == "draft" and made.json()["crop"] == 1
    mid = made.json()["id"]
    assert api.post(f"{base}/marks", json={"slide": n, "kind": "label", "geom": {"x": .5, "y": .5}, "text": ""}).status_code == 422
    assert api.post(f"{base}/marks", json={"slide": n, "crop": 7, "kind": "label", "geom": {"x": .5, "y": .5}, "text": "t"}).status_code == 422        # that picture does not exist
    assert api.post(f"{base}/marks", json={"slide": n, "kind": "arrow", "geom": {"from": [0, 0], "to": [2, 2]}}).status_code == 422
    two = api.post(f"{base}/marks", json={"slide": n, "kind": "label", "geom": {"x": .5, "y": .5}, "text": "Pin"}).json()["id"]
    assert api.post(f"{base}/marks/reorder", json={"slide": n, "crop": 1, "ids": [two, mid]}).status_code == 200
    ann = api.get(f"{base}/annotations").json()
    station = next(s for s in ann["stations"] if s["index"] == st["n"] - 1)
    im = next(i for i in station["images"] if i["slide"] == n and i["crop"] == 1)
    assert [m["id"] for m in im["marks"]] == [two, mid] and im["original_url"].endswith(f"/slides/{n}/original") and im["confidence"] == "high"
    assert station["drafts"] == 2 and ann["rendered"] is True
    # a flagged mark (outside the crop) is never approved by the station's bulk approve
    s = GM.MarkStore()
    flagged = s.create(G17, n, "label", {"x": 0.9, "y": 0.9}, "Stray", None, "x")
    with s._db() as db:
        db.execute("UPDATE marks SET flag = 'Outside the cropped picture' WHERE id = ?", (flagged["id"],))
    assert api.post(f"{base}/stations/{st['n'] - 1}/approve", json={"approve": True}).json() == {"changed": 2}
    assert s.get(flagged["id"])["status"] == "draft"
    assert api.put(f"{base}/marks/{mid}", json={"step": 0}).json()["status"] == "approved"
    assert api.put(f"{base}/marks/{mid}", json={"step": None}).json()["status"] == "draft"
    assert api.put(f"{base}/marks/{mid}", json={"geom": {"from": [0.2, 0.2], "to": [0.5, 0.5]}}).json()["geom"]["from"] == [0.2, 0.2]
    assert api.delete(f"{base}/marks/{two}").status_code == 200 and api.delete(f"{base}/marks/{two}").status_code == 404


# ---- chat image cards --------------------------------------------------------------------------------------------------------------------

def fake_view(crumb, text):
    src = {"source_type": "dissection_guide", "cite": f"Dissection Guide, {crumb}", "crumb": crumb}
    return {"sources": [src], "sources_list": [{"n": 1, "chunk": 0}], "cite_unit": {1: 0}, "units": [{"text": text}]}


def test_chat_cards_only_for_guides_the_student_may_open_and_only_cropped_pictures(imgs):
    n = high_slide()
    st = next(x for x in stations(G17) if n in x["slides"])
    view = fake_view(f"Class 17, slide {n}", st["steps"][0])
    md = "1. First step. [1]\n2. Second step."
    granted = guide_media.chat_images(view, md, ["Dissection Guide, Class 17"])
    assert len(granted) == 1 and granted[0]["guide_id"] == G17 and granted[0]["slide"] == n and granted[0]["crop"] == 1 and granted[0]["url"].endswith("/crops/1/image")
    assert guide_media.chat_images(view, md, []) == [] and guide_media.chat_images(view, md, ["Dissection Guide, Class 26"]) == []
    assert len(guide_media.chat_images(view, md, None)) == 1
    last = picture_slides(G17)[-1]
    assert guide_media.chat_images(fake_view(f"Class 17, slide {last}", "x"), md, None) == []         # a low-confidence crop is not shown until it is checked


def test_a_concept_answer_gets_at_most_one_image_and_a_procedural_one_a_card_per_step(imgs):
    vis = [n for n in picture_slides(G17) if n != picture_slides(G17)[-1]][:3]
    srcs = [{"source_type": "dissection_guide", "cite": f"Dissection Guide, Class 17, slide {n}", "crumb": f"Class 17, slide {n}"} for n in vis]
    view = {"sources": srcs, "sources_list": [{"n": i + 1, "chunk": i} for i in range(len(vis))], "cite_unit": {}, "units": []}
    assert len(guide_media.chat_images(view, "The ligament is strong.", None)) == 1
    steps = guide_media.chat_images(view, "1. Cut here. [1]\n2. Then here. [2]\n3. Then here. [3]", None)
    assert [c["slide"] for c in steps] == vis and guide_media.is_procedural("1. a\n2. b") and not guide_media.is_procedural("1. only one")


def test_a_chat_card_carries_only_the_approved_marks_of_its_step_and_its_picture(imgs):
    n = high_slide()
    st = next(x for x in stations(G17) if n in x["slides"])
    s = GM.MarkStore()
    s.create(G17, n, "label", {"x": .5, "y": .5}, "step 0", 0, "x", status="approved")
    s.create(G17, n, "label", {"x": .6, "y": .6}, "step 1", 1 if len(st["steps"]) > 1 else 0, "x", status="approved")
    s.create(G17, n, "label", {"x": .7, "y": .7}, "draft", 0, "x")
    s.create(G17, n, "label", {"x": .8, "y": .8}, "other picture", 0, "x", status="approved", crop=2)
    card = guide_media.chat_images(fake_view(f"Class 17, slide {n}", st["steps"][0]), "1. do it\n2. then", None)[0]
    texts = {m["text"] for m in card["marks"]}
    assert "draft" not in texts and "other picture" not in texts and "step 0" in texts and ("step 1" not in texts or len(st["steps"]) == 1)


# ---- Explain simply ------------------------------------------------------------------------------------------------------------------------

def test_explain_simply_is_short_grounded_and_labelled(monkeypatch):
    from src import guide_explain as GE
    station = {"title": "Pes anserinus", "steps": ["Transect the tendons of the sartorius, gracilis and semitendinosus muscles."]}
    notes = [{"label": "Notes · L13", "text": "The pes anserinus is the common insertion of three muscles on the medial tibia.", "breadcrumb": "L13 > Knee", "lecture": "Lecture 13"}]
    seen = {}

    def fake(client, system, messages, max_tokens, schema, model=None):
        seen["user"] = messages[0]["content"]
        return {"explanation": "You cut the three tendons that share one insertion, so you can lift them away and see the ligament below."}, {"input_tokens": 1, "output_tokens": 1}
    monkeypatch.setattr(GE.llm, "complete_json", fake)
    out, _ = GE.explain(object(), "m", station, notes, "more_fat")
    assert out["text"].startswith("You cut") and "<body_type>more_fat</body_type>" in seen["user"] and "common insertion" in seen["user"] and GE.LABEL == "AI explanation, check your guide"
    assert GE.valid("One. Two. Three. Four. Five.", "x") == "too long" and GE.valid("Cut 5 cm deep.", "Cut deep.") == "a number that is not in the guide or the notes" and GE.valid("", "x") == "empty"
    monkeypatch.setattr(GE.llm, "complete_json", lambda *a, **k: ({"explanation": "Cut 12 cm below the knee."}, {"input_tokens": 1, "output_tokens": 1}))
    assert GE.explain(object(), "m", station, notes)[0] is None                                    # an invented number is rejected twice, so nothing is shown


def test_the_explain_endpoint_is_for_students_with_access_and_not_for_picture_stations(api, monkeypatch):
    from src import guide_explain as GE
    from src import service
    from tests.test_service import FakeClient

    class Searcher:
        chunks = []

        def search(self, query, k=5, allowed_lectures=None, rerank=True):
            from src.retrieval.search import SearchResult
            return SearchResult(query, False, [], 0.0, "")
    st = next(s for s in stations(G17) if s["steps"] and not s["image_only"])
    monkeypatch.setattr(GE.llm, "complete_json", lambda *a, **k: ({"explanation": "You open the area so you can see the structures."}, {"input_tokens": 1, "output_tokens": 1}))
    api.app.state.runtime = service.Runtime(searcher=Searcher(), next_of={}, client=FakeClient(""), model="m")
    url = f"/api/guides/{G17}/stations/{st['n'] - 1}/explain"
    assert api.post(url, json={}).status_code == 401
    login(api, "none")
    assert api.post(url, json={}).status_code == 403
    login(api, "prof")
    assert api.post(url, json={}).status_code == 403                                                      # a student tool
    login(api, "s17")
    r = api.post(url, json={"body_type": "more_fat"})
    assert r.status_code == 200 and r.json()["label"] == "AI explanation, check your guide" and r.json()["text"].startswith("You open") and r.json()["sources"][0]["type"] == "guide"
    assert api.post(f"/api/guides/{G17}/stations/9999/explain", json={}).status_code == 404
