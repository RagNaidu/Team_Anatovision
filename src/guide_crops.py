"""Crop each guide slide to its anatomy picture only (no step text, headers or footers).

Plan (from the pptx): the picture / diagram shapes of a slide are clustered (touching or overlapping pictures become one crop; separate pictures stay separate crops, in
reading order); label, arrow, line, ellipse and freeform shapes that overlap or touch a cluster are added; text boxes holding step text (more than 6 words, numbered, or
matching the station steps), headers, footers and slide numbers are never added. Then the PDF page is rendered at the resolution that makes the crop at least MIN_LONG px on
its long side, and cropped. A picture that fills most of the slide (a flattened slide) is cropped by image analysis: OCR finds the text lines, long ones (step text) are
painted out, and the remaining non-background area is the illustration (low confidence: it needs a look). A slide with no picture gets no image.

Confidence: "high" = from picture shapes with no step text over the picture; "low" = flattened slide, step text overlapping the picture, a crop covering most of the slide, or a tiny
picture. Students see a low-confidence crop only after the instructor marks it checked.
"""
import re

from src import ocr

MIN_LONG = 1600
MAX_PAGE_W = 7000
MARGIN = 0.012
TOUCH = 0.012
FLAT_AREA = 0.70
MIN_AREA = 0.012
FOOTER_BAND = 0.085
THUMB_LONG = 420
FOOTER = re.compile(r"PAS\s?\d+|Class\s+\d+\s+Dissection|Laboratory Session|Gross Human Anatomy|Dissection Guide", re.I)
CLOSING = re.compile(r"End of (the )?(Laboratory|Dissection|Session)|University at Buffalo|Gross Human Anatomy", re.I)       # title and closing slides carry the university logo, not anatomy
NUMBERED = re.compile(r"^\s*\d{1,2}\s*[.)]\s+\S")
STOP = {"the", "and", "for", "with", "that", "this", "from", "your", "are", "into", "its", "have", "then", "each", "other", "there"}
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def words_of(text):
    return {w for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in STOP}


def is_step_text(text, steps=()):
    """Text that belongs to the step list: numbered or long (more than 6 words). A short phrase that a step also mentions is a LABEL, not step text. Credit lines (\"Copyright ...\") are
    part of the third-party artwork and are not step text either."""
    t = " ".join((text or "").split())
    if not t or re.match(r"(?i)^(copyright|©)", t):
        return False
    return bool(NUMBERED.match(t) or len(t.split()) > 6)


def rot_of(shape):
    try:
        return float(shape.rotation or 0.0)
    except Exception:
        return 0.0


def rotate_pt(x, y, cx, cy, deg):
    import math
    a = math.radians(deg)
    dx, dy = x - cx, y - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)


def bbox(shape, tf, size):
    """Normalised (x0, y0, x1, y1) of a shape on the slide, with its rotation and its group transform applied."""
    sw, sh = size
    l, t, w, h = shape.left, shape.top, shape.width, shape.height
    cx, cy = l + w / 2, t + h / 2
    pts = [(l, t), (l + w, t), (l + w, t + h), (l, t + h)]
    deg = rot_of(shape)
    if deg:
        pts = [rotate_pt(x, y, cx, cy, deg) for x, y in pts]
    pts = [tf(x, y) for x, y in pts]
    xs, ys = [p[0] / sw for p in pts], [p[1] / sh for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def grow(b, m):
    return (b[0] - m, b[1] - m, b[2] + m, b[3] + m)


def clamp(b):
    return (max(0.0, b[0]), max(0.0, b[1]), min(1.0, b[2]), min(1.0, b[3]))


def touches(a, b, m=0.0):
    return not (a[2] + m < b[0] or b[2] + m < a[0] or a[3] + m < b[1] or b[3] + m < a[1])


def area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def overlap_area(a, b):
    return area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def _is_picture(shape):
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    try:
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            return True
        if shape.is_placeholder and shape.__class__.__name__ == "PlaceholderPicture":
            return True
    except Exception:
        pass
    return False


def _is_diagram(shape):
    uri = " ".join(shape._element.xpath(".//a:graphicData/@uri")) if shape._element.tag.endswith("graphicFrame") else ""
    return "diagram" in uri or "chart" in uri


def _placeholder_kind(shape):
    try:
        return str(shape.placeholder_format.type) if shape.is_placeholder else ""
    except Exception:
        return ""


def classify(slide, size, steps):
    """-> (pictures, annotations, texts): lists of (bbox, shape-info). Pictures are picture or diagram shapes; annotations are lines, arrows, ellipses, freeforms and short labels;
    texts are step text / headers / footers (never part of a crop, but remembered to see whether they overlap one)."""
    from src.guide_autodraft import walk, LINES, BLOCK_ARROWS, ELLIPSES, _prst
    pics, ann, texts = [], [], []
    for shape, tf in walk(slide.shapes):
        try:
            b = bbox(shape, tf, size)
        except Exception:
            continue
        ph = _placeholder_kind(shape)
        text0 = shape.text_frame.text.strip() if getattr(shape, "has_text_frame", False) and shape.has_text_frame else ""
        if text0 and CLOSING.search(text0) and FOOTER_BAND <= b[1] and b[3] <= 1 - FOOTER_BAND:
            texts.append((b, "closing"))
            continue
        if _is_picture(shape) or _is_diagram(shape):
            pics.append((b, "diagram" if _is_diagram(shape) else "picture"))
            continue
        text = shape.text_frame.text.strip() if getattr(shape, "has_text_frame", False) and shape.has_text_frame else ""
        if "FOOTER" in ph or "SLIDE_NUMBER" in ph or "DATE" in ph or (text and FOOTER.search(text)) or (text and (b[1] < FOOTER_BAND or b[3] > 1 - FOOTER_BAND) and len(text.split()) <= 12):
            texts.append((b, "footer"))
            continue
        tag = shape._element.tag.split("}")[1]
        prst = _prst(shape)
        if text and (is_step_text(text, steps) or ph and "TITLE" not in ph and "BODY" in ph or ph and "OBJECT" in ph):
            texts.append((b, "step"))
        elif text and len(text.split()) <= 6 and len(text) > 2 and not re.fullmatch(r"[\d\W]+", text):
            ann.append((b, "label"))
        elif tag == "cxnSp" or prst in LINES or prst in BLOCK_ARROWS or prst in ELLIPSES or prst in ("arc", "curvedConnector3") or tag == "sp" and shape.shape_type is not None and "FREEFORM" in str(shape.shape_type):
            ann.append((b, "shape"))
    return pics, ann, texts


def plan_slide(slide, size, steps):
    """-> {"crops": [{"box", "confidence", "why"}], "flat": bool, "status": "auto" | "review" | "none"}. Boxes are normalised slide coordinates."""
    pics, ann, texts = classify(slide, size, steps)
    if any(t[1] == "closing" for t in texts):
        return {"crops": [], "flat": False, "status": "none"}
    pics = [p for p in pics if area(p[0]) >= MIN_AREA]
    if not pics:
        return {"crops": [], "flat": False, "status": "none"}
    flat = max(area(clamp(p[0])) for p in pics) >= FLAT_AREA
    if flat:
        return {"crops": [{"box": [0.0, 0.0, 1.0, 1.0], "confidence": "low", "why": "the slide is one flattened picture: the illustration area is found by image analysis"}], "flat": True, "status": "review"}
    clusters = []
    for b, _k in sorted(pics, key=lambda p: (round(p[0][1] * 6), p[0][0])):
        b = clamp(b)
        merged = [c for c in clusters if touches(c, b, TOUCH)]
        for c in merged:
            clusters.remove(c)
            b = union([b, c])
        clusters.append(b)
    out = []
    for c in clusters:
        box = c
        for b, _k in ann:
            if touches(box, b, TOUCH):
                box = union([box, clamp(b)])
        box = clamp(grow(box, MARGIN))
        why, conf = [], "high"
        over = [t for t in texts if t[1] == "step" and overlap_area(box, clamp(t[0])) > 0.15 * max(area(t[0]), 1e-9)]
        if over:
            conf, why = "low", ["step text overlaps the picture"]
        if area(box) > 0.9:
            conf, why = "low", why + ["the crop covers almost the whole slide"]
        if area(box) < 0.02:
            conf, why = "low", why + ["a very small picture"]
        out.append({"box": [round(v, 4) for v in box], "confidence": conf, "why": "; ".join(why)})
    out.sort(key=lambda c: (round(c["box"][1] * 8), c["box"][0]))
    return {"crops": out, "flat": False, "status": "review" if any(c["confidence"] == "low" for c in out) else "auto"}


# ---------------------------------------------------------------- flattened slides: find the illustration by image analysis
def flat_region(img, steps):
    """img = the rendered slide (PIL). -> (box, conf-note). Step text lines (OCR) are painted out, then the non-background area is the illustration."""
    import numpy as np
    from scipy import ndimage
    from PIL import Image
    a = np.array(img.convert("RGB")).astype(np.int16)
    H, W = a.shape[:2]
    bg = np.median(np.concatenate([a[:6].reshape(-1, 3), a[-6:].reshape(-1, 3), a[:, :6].reshape(-1, 3), a[:, -6:].reshape(-1, 3)]), axis=0)
    lines = ocr.read(img)
    kept_labels = []
    for ln in lines:
        x0, y0, x1, y1 = ln["box"]
        if is_step_text(ln["text"], steps) or y0 > 1 - FOOTER_BAND or y1 < FOOTER_BAND and len(ln["text"].split()) > 3:
            a[int(y0 * H) - 2:int(y1 * H) + 2, int(x0 * W) - 2:int(x1 * W) + 2] = bg
        else:
            kept_labels.append(ln)
    mask = (np.abs(a - bg).max(axis=2) > 28)
    small = ndimage.binary_dilation(mask[::4, ::4], iterations=6)
    lab, n = ndimage.label(small)
    if n == 0:
        return (0.0, 0.0, 1.0, 1.0), "no illustration found"
    sizes = ndimage.sum(small, lab, range(1, n + 1))
    keep = [i + 1 for i, s in enumerate(sizes) if s >= 0.02 * small.size]
    if not keep:
        keep = [int(np.argmax(sizes)) + 1]
    ys, xs = np.where(np.isin(lab, keep))
    box = (xs.min() * 4 / W, ys.min() * 4 / H, (xs.max() + 1) * 4 / W, (ys.max() + 1) * 4 / H)
    for ln in kept_labels:                                         # short labels next to the picture stay in
        if touches(box, tuple(ln["box"]), 0.03):
            box = union([box, tuple(ln["box"])])
    return clamp(grow(box, MARGIN)), ""


# ---------------------------------------------------------------- rendering
def page_width_for(box, aspect):
    """Page width in px so that the crop's long side is at least MIN_LONG px."""
    fw, fh = max(1e-3, box[2] - box[0]), max(1e-3, box[3] - box[1])
    import math
    return int(min(MAX_PAGE_W, max(1600, math.ceil(MIN_LONG / max(fw, fh * aspect)) + 1)))


def crop_page(page, box):
    """page = a pypdfium2 page. -> the PIL crop at >= MIN_LONG px on its long side (when the page can be rendered that large)."""
    pw, ph = page.get_size()
    wp = page_width_for(box, ph / pw)
    img = page.render(scale=wp / pw).to_pil().convert("RGB")
    W, H = img.size
    return img.crop((round(box[0] * W), round(box[1] * H), round(box[2] * W), round(box[3] * H)))


def save_crop(img, path, thumb_path):
    from PIL import Image
    img.save(path, "WEBP", quality=92, method=4)
    t = img.copy()
    t.thumbnail((THUMB_LONG, THUMB_LONG), Image.LANCZOS)
    t.save(thumb_path, "WEBP", quality=85)
    return img.size
