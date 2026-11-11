"""Pictures of the dissection guides: where they live, how a station finds its images, and building them.

  data/processed/guide_images/<guide_id>/crop_<n>_<k>.webp        the k-th anatomy picture of slide n, cropped from the rendered slide (>= 1600 px on its long side)
  data/processed/guide_images/<guide_id>/crop_<n>_<k>_thumb.webp  a thumbnail
  data/processed/guide_images/<guide_id>/slide_<n>.png            the whole slide at 1280 px: for INSTRUCTORS only ("View original slide"), never sent to students
  data/processed/guide_images/<guide_id>/meta.json                {"mode": "render" | "pictures", "version": 2, "slides": {"n": {"w", "h", "status": "auto" | "review" | "none", "crops": [{"k", "box", "w", "h", "confidence", "why"}]}}}

`box` is the crop's place on the slide as fractions [x0, y0, x1, y1]. Rendering needs LibreOffice (soffice) and pypdfium2; without LibreOffice the build falls back to the pictures
embedded in the slides (no labels or arrows). Images are never AI-generated and are served only to a signed-in user who may open the guide (app_api/routers/guide.py).
"""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMG_DIR = ROOT / "data" / "processed" / "guide_images"
FULL_W = 1280
CAPTION = "Slide {n} · Dr. Inglis's dissection guide"
DISCLAIMER = "Your cadaver may look different."
META_VERSION = 2


def soffice():
    return shutil.which("soffice") or ("/opt/homebrew/bin/soffice" if Path("/opt/homebrew/bin/soffice").exists() else None)


def guide_dir(guide_id, base=None):
    if not re.fullmatch(r"[a-z0-9-]+", guide_id or ""):
        raise ValueError("bad guide id")
    return Path(base or IMG_DIR) / guide_id


def crop_path(guide_id, slide, k=1, thumb=False, base=None):
    return guide_dir(guide_id, base) / f"crop_{int(slide)}_{int(k)}{'_thumb' if thumb else ''}.webp"


def original_path(guide_id, slide, base=None):
    return guide_dir(guide_id, base) / f"slide_{int(slide)}.png"


def meta(guide_id, base=None):
    p = guide_dir(guide_id, base) / "meta.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"mode": None, "version": 0, "slides": {}}


def crops_of(guide_id, slide, base=None):
    """The crops of one slide: [{"k", "box", "w", "h", "confidence", "why"}] that have a file."""
    return [c for c in meta(guide_id, base)["slides"].get(str(slide), {}).get("crops", []) if crop_path(guide_id, slide, c["k"], False, base).exists()]


def has_image(guide_id, slide, k=1, base=None):
    return crop_path(guide_id, slide, k, False, base).exists()


def images_for(guide_id, slides, title="", base=None, reviewed=None, student=True):
    """The pictures of the given slides, in slide order and reading order: [{"slide", "crop", "url", "thumb_url", "caption", "alt", "w", "h", "confidence", "why"}].
    For a student (student=True) a LOW-confidence crop is left out until the instructor has marked it checked (`reviewed` = a set of (slide, crop))."""
    out = []
    for n in slides:
        cs = crops_of(guide_id, n, base)
        for c in cs:
            if student and c["confidence"] != "high" and (n, c["k"]) not in (reviewed or set()):
                continue
            more = f" (picture {c['k']} of {len(cs)})" if len(cs) > 1 else ""
            out.append({"slide": n, "crop": c["k"], "url": f"/api/guides/{guide_id}/slides/{n}/crops/{c['k']}/image", "thumb_url": f"/api/guides/{guide_id}/slides/{n}/crops/{c['k']}/thumb",
                        "caption": CAPTION.format(n=n) + more, "alt": f"Slide {n}{more}" + (f": {title}" if title else ""), "w": c["w"], "h": c["h"], "confidence": c["confidence"], "why": c.get("why", "")})
    return out


def box_of(guide_id, slide, k, base=None):
    c = next((c for c in meta(guide_id, base)["slides"].get(str(slide), {}).get("crops", []) if c["k"] == k), None)
    return c["box"] if c else None


# ---------------------------------------------------------------- building
def slide_rows(path_slides, file):
    return [json.loads(l) for l in Path(path_slides).read_text(encoding="utf-8").splitlines() if l.strip() and json.loads(l)["file"] == file]


def render_pdf(pptx, workdir, timeout=900):
    pdf = Path(workdir) / (Path(pptx).stem + ".pdf")
    subprocess.run([soffice(), "--headless", "--convert-to", "pdf", "--outdir", str(workdir), str(pptx)], check=True, capture_output=True, timeout=timeout)
    return pdf


def build_guide(pptx, guide_id, rows, steps_of_slide=None, base=None, force=False):
    """Render one guide and crop every slide to its anatomy pictures. rows = its parsed slides; steps_of_slide(n) = the step texts of the station that holds slide n (for telling step text
    from labels). -> {"slides": {"auto": n, "review": n, "none": n}, "crops": n, "skipped": reason or ""}"""
    import pypdfium2 as pdfium
    from pptx import Presentation
    from src import guide_crops as GC
    dest = guide_dir(guide_id, base)
    m0 = meta(guide_id, base)
    if m0["mode"] == "render" and m0.get("version") == META_VERSION and not force:
        return {"slides": {}, "crops": 0, "skipped": "already built"}
    dest.mkdir(parents=True, exist_ok=True)
    for old in list(dest.glob("crop_*")) + list(dest.glob("slide_*")):
        old.unlink()
    steps_of_slide = steps_of_slide or (lambda n: [])
    prs = Presentation(str(pptx))
    size = (prs.slide_width, prs.slide_height)
    with tempfile.TemporaryDirectory() as tmp:
        doc = pdfium.PdfDocument(str(render_pdf(pptx, tmp)))
        pages = len(doc)
        visible = [r["n"] for r in rows if not r.get("hidden")]
        order = [r["n"] for r in rows] if pages == len(rows) else visible if pages == len(visible) else None
        if order is None:
            return {"slides": {}, "crops": 0, "skipped": f"{pages} pages but {len(rows)} slides ({len(visible)} not hidden)"}
        kinds = {r["n"]: r.get("kind") for r in rows}
        info, counts, ncrops = {}, {"auto": 0, "review": 0, "none": 0}, 0
        slides = list(prs.slides)
        for i, n in enumerate(order):
            page = doc[i]
            full = page.render(scale=FULL_W / page.get_width()).to_pil().convert("RGB")
            full.save(original_path(guide_id, n, base), "PNG", optimize=True)
            entry = {"w": full.size[0], "h": full.size[1], "status": "none", "crops": []}
            if kinds.get(n) in ("title", "end", "empty") or n > len(slides):
                info[str(n)] = entry
                counts["none"] += 1
                continue
            plan = GC.plan_slide(slides[n - 1], size, steps_of_slide(n))
            for k, c in enumerate(plan["crops"], 1):
                box, why = c["box"], c["why"]
                if plan["flat"]:
                    big = page.render(scale=2400 / page.get_width()).to_pil().convert("RGB")
                    box, note = GC.flat_region(big, steps_of_slide(n))
                    why = (c["why"] + ("; " + note if note else "")).strip("; ")
                img = GC.crop_page(page, box)
                w, h = GC.save_crop(img, crop_path(guide_id, n, k, False, base), crop_path(guide_id, n, k, True, base))
                entry["crops"].append({"k": k, "box": [round(v, 4) for v in box], "w": w, "h": h, "confidence": c["confidence"], "why": why})
                ncrops += 1
            entry["status"] = plan["status"]
            counts[plan["status"]] += 1
            info[str(n)] = entry
        doc.close()
    (dest / "meta.json").write_text(json.dumps({"mode": "render", "version": META_VERSION, "slides": info}), encoding="utf-8")
    return {"slides": counts, "crops": ncrops, "skipped": ""}


def build_pictures(pptx, guide_id, rows, base=None):
    """Fallback without LibreOffice: each picture embedded in a slide becomes a crop as it is (labels and arrows drawn on the slide are NOT in it)."""
    from io import BytesIO
    from PIL import Image
    from pptx import Presentation
    from src import guide_crops as GC
    from src.guide_autodraft import walk
    prs = Presentation(str(pptx))
    dest = guide_dir(guide_id, base)
    dest.mkdir(parents=True, exist_ok=True)
    kinds = {r["n"]: r.get("kind") for r in rows}
    info, ncrops = {}, 0
    for n, slide in enumerate(prs.slides, 1):
        entry = {"w": 0, "h": 0, "status": "none", "crops": []}
        if kinds.get(n) not in ("title", "end", "empty"):
            pics = []
            for shp, tf in walk(slide.shapes):
                if GC._is_picture(shp):
                    try:
                        pics.append((GC.bbox(shp, tf, (prs.slide_width, prs.slide_height)), shp.image.blob))
                    except Exception:
                        continue
            for k, (b, blob) in enumerate(sorted(pics, key=lambda p: (round(p[0][1] * 6), p[0][0])), 1):
                if GC.area(b) < GC.MIN_AREA:
                    continue
                img = Image.open(BytesIO(blob)).convert("RGB")
                w, h = GC.save_crop(img, crop_path(guide_id, n, k, False, base), crop_path(guide_id, n, k, True, base))
                entry["crops"].append({"k": k, "box": [round(v, 4) for v in b], "w": w, "h": h, "confidence": "low", "why": "embedded picture only (no LibreOffice): labels and arrows are missing"})
                ncrops += 1
            entry["status"] = "review" if entry["crops"] else "none"
        info[str(n)] = entry
    (dest / "meta.json").write_text(json.dumps({"mode": "pictures", "version": META_VERSION, "slides": info}), encoding="utf-8")
    return {"slides": {}, "crops": ncrops, "skipped": ""}
