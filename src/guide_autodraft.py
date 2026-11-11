"""Read arrows, lines, ellipses and short text boxes from an instructor's own guide slides (python-pptx) and turn them into DRAFT marks on the rendered slide.

Shape positions (EMU) are converted to 0-1 slide coordinates, which are also the coordinates of the rendered slide image. Group transforms are applied; rotation is not
(a rotated shape is drawn from its unrotated box: the instructor checks every draft in the editor). Each mark is linked to the step of its station whose text best
matches the label text (an arrow or highlight takes the step of the nearest matched label). Nothing is ever approved here.
"""
import re

from src import guide_crops as GC
from src.guide_marks import MarkStore, inside, to_crop_geom

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
LINES = {"line", "straightConnector1", "bentConnector2", "bentConnector3", "bentConnector4", "bentConnector5", "curvedConnector2", "curvedConnector3", "curvedConnector4", "curvedConnector5"}
BLOCK_ARROWS = {"rightArrow": ((0, .5), (1, .5)), "leftArrow": ((1, .5), (0, .5)), "upArrow": ((.5, 1), (.5, 0)), "downArrow": ((.5, 0), (.5, 1))}
ELLIPSES = {"ellipse", "oval"}
STOP = {"the", "and", "for", "with", "that", "this", "from", "your", "are", "into", "its", "have", "then", "each", "other", "there"}
FOOTER = re.compile(r"PAS\s?\d+|Class\s+\d+|Laboratory Session|Gross Human Anatomy|Dissection Guide", re.I)
NEAR = 0.25


def tokens(text):
    return {w for w in re.findall(r"[a-z]{3,}", (text or "").lower()) if w not in STOP}


def match_step(label, steps):
    """-> index of the step whose text contains the most of the label's words (at least 60% of them), else None."""
    want = tokens(label)
    if not want:
        return None
    best, score = None, 0.0
    for i, s in enumerate(steps):
        sc = len(want & tokens(s)) / len(want)
        if sc > score:
            best, score = i, sc
    return best if score >= 0.6 else None


def _xfrm(el):
    x = el.find(f".//{A}xfrm")
    return x


def _box(shape):
    return shape.left, shape.top, shape.width, shape.height


def walk(shapes, tf=lambda x, y: (x, y), ks=(1.0, 1.0)):
    """Yield (shape, to_slide) for every non-group shape, mapping coordinates out of nested groups. ks = the accumulated scale of the group frames."""
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    for s in shapes:
        if s.shape_type == MSO_SHAPE_TYPE.GROUP:
            x = s._element.find(f".//{A}xfrm")
            off, ext, choff, chext = (x.find(f"{A}off"), x.find(f"{A}ext"), x.find(f"{A}chOff"), x.find(f"{A}chExt")) if x is not None else (None,) * 4
            if None in (off, ext, choff, chext) or int(chext.get("cx")) == 0 or int(chext.get("cy")) == 0:
                yield from walk(s.shapes, tf, ks)
                continue
            sx, sy = int(ext.get("cx")) / int(chext.get("cx")), int(ext.get("cy")) / int(chext.get("cy"))
            ox, oy, cx, cy = int(off.get("x")), int(off.get("y")), int(choff.get("x")), int(choff.get("y"))

            def inner(px, py, ox=ox, oy=oy, cx=cx, cy=cy, sx=sx, sy=sy, tf=tf):
                return tf(ox + (px - cx) * sx, oy + (py - cy) * sy)
            yield from walk(s.shapes, inner, (ks[0] * sx, ks[1] * sy))
        else:
            yield s, tf


def _prst(shape):
    p = shape._element.find(f".//{A}prstGeom")
    return p.get("prst") if p is not None else None


def _flips(shape):
    x = shape._element.find(f".//{A}xfrm")
    return (x is not None and x.get("flipH") == "1"), (x is not None and x.get("flipV") == "1")


def _ln(shape):
    return shape._element.find(f".//{A}ln")


def _arrowhead(shape):
    """-> (head_at_start, head_at_end)"""
    ln = _ln(shape)
    if ln is None:
        return False, False
    h, t = ln.find(f"{A}headEnd"), ln.find(f"{A}tailEnd")
    on = lambda e: e is not None and e.get("type", "none") != "none"
    return on(h), on(t)


def _dashed(shape):
    ln = _ln(shape)
    d = ln.find(f"{A}prstDash") if ln is not None else None
    return d is not None and d.get("val", "solid") != "solid"


def _no_fill(shape):
    sp = shape._element.find(f"{{http://schemas.openxmlformats.org/presentationml/2006/main}}spPr")
    return sp is not None and sp.find(f"{A}noFill") is not None


def _endpoints(shape):
    """The two ends of a line shape: flipped as the shape is flipped, then rotated about the shape's centre."""
    l, t, w, h = _box(shape)
    fh, fv = _flips(shape)
    x0, x1 = (l + w, l) if fh else (l, l + w)
    y0, y1 = (t + h, t) if fv else (t, t + h)
    deg = GC.rot_of(shape)
    if deg:
        cx, cy = l + w / 2, t + h / 2
        return GC.rotate_pt(x0, y0, cx, cy, deg), GC.rotate_pt(x1, y1, cx, cy, deg)
    return (x0, y0), (x1, y1)


def draft_slide(slide, size, steps, tf_root=None):
    """-> [{"kind", "geom", "text", "step"}] draft marks of one pptx slide. size = (slide width, slide height) in EMU."""
    sw, sh = size
    norm = lambda p: (round(min(1, max(0, p[0] / sw)), 4), round(min(1, max(0, p[1] / sh)), 4))
    labels, shapes_out, plain = [], [], []
    for shape, tf in walk(slide.shapes):
        try:
            if shape.is_placeholder or shape.shape_type is None:
                continue
        except Exception:
            continue
        prst = _prst(shape)
        tag = shape._element.tag.split("}")[1]
        text = shape.text_frame.text.strip() if getattr(shape, "has_text_frame", False) and shape.has_text_frame else ""
        if tag == "cxnSp" or prst in LINES:
            a, b = (tf(*pt) for pt in _endpoints(shape))
            head_start, head_end = _arrowhead(shape)
            if head_end or head_start:
                p, q = (norm(b), norm(a)) if (head_start and not head_end) else (norm(a), norm(b))
                shapes_out.append({"kind": "arrow", "geom": {"from": list(p), "to": list(q)}, "anchor": q})
            elif _dashed(shape):
                shapes_out.append({"kind": "cut", "geom": {"points": [list(norm(a)), list(norm(b))]}, "anchor": norm(b)})
            else:
                plain.append((norm(a), norm(b)))                   # a leader line from a label to a structure
        elif prst in BLOCK_ARROWS:
            l, t, w, h = _box(shape)
            (fx, fy), (gx, gy) = BLOCK_ARROWS[prst]
            cx, cy, deg = l + w / 2, t + h / 2, GC.rot_of(shape)
            pa, pb = (l + fx * w, t + fy * h), (l + gx * w, t + gy * h)
            if deg:
                pa, pb = GC.rotate_pt(*pa, cx, cy, deg), GC.rotate_pt(*pb, cx, cy, deg)
            a, b = tf(*pa), tf(*pb)
            shapes_out.append({"kind": "arrow", "geom": {"from": list(norm(a)), "to": list(norm(b))}, "anchor": norm(b)})
        elif prst in ELLIPSES and (_no_fill(shape) or not text):
            l, t, w, h = _box(shape)
            c = norm(tf(l + w / 2, t + h / 2))
            quarter = round(GC.rot_of(shape) / 90.0) % 2 == 1               # a quarter turn swaps the two radii (other angles: the unrotated box, checked by the instructor)
            w, h = (h, w) if quarter else (w, h)
            l, t = (l + (shape.width - w) / 2, t + (shape.height - h) / 2) if quarter else (l, t)
            rx, ry = max(0.005, abs(norm(tf(l + w, t))[0] - norm(tf(l, t))[0]) / 2), max(0.005, abs(norm(tf(l, t + h))[1] - norm(tf(l, t))[1]) / 2)
            shapes_out.append({"kind": "highlight", "geom": {"cx": c[0], "cy": c[1], "rx": round(rx, 4), "ry": round(ry, 4)}, "anchor": c})
        elif text and len(text.split()) <= 6 and len(text) > 2 and not FOOTER.search(text) and not re.fullmatch(r"[\d\W]+", text):
            l, t, w, h = _box(shape)
            c = norm(tf(l + w / 2, t + h / 2))
            p0, p1 = norm(tf(l, t)), norm(tf(l + w, t + h))
            labels.append({"kind": "label", "geom": {"x": c[0], "y": c[1]}, "text": " ".join(text.split())[:80], "step": match_step(text, steps), "anchor": c, "box": (p0[0], p0[1], p1[0], p1[1])})
    for lab in labels:                                          # the slide already shows the label text: the pin goes on the STRUCTURE its leader line points to
        x0, y0, x1, y1 = lab.pop("box")
        pad = 0.03
        for a, b in plain:
            for near, far in ((a, b), (b, a)):
                if x0 - pad <= near[0] <= x1 + pad and y0 - pad <= near[1] <= y1 + pad and not (x0 <= far[0] <= x1 and y0 <= far[1] <= y1):
                    lab["geom"] = {"x": far[0], "y": far[1]}
                    lab["anchor"] = far
                    break
            else:
                continue
            break
    for m in shapes_out:                                        # an arrow / highlight / cut takes the step of the nearest label that matched a step
        near = [(abs(l["anchor"][0] - m["anchor"][0]) + abs(l["anchor"][1] - m["anchor"][1]), l["step"]) for l in labels if l["step"] is not None]
        near = [n for n in near if n[0] <= NEAR]
        m["step"] = min(near)[1] if near else None
        m["text"] = ""
    return [{k: v for k, v in m.items() if k != "anchor"} for m in shapes_out + labels]


def to_crops(marks, crops):
    """Slide-normalised draft marks -> marks on the cropped pictures: [(crop k, mark)]. A mark whose anchor is outside every crop is dropped."""
    from src.guide_marks import anchor
    out = []
    for m in marks:
        a = anchor(m["kind"], m["geom"])
        c = next((c for c in crops if inside(a, c["box"], 0.01)), None)
        if c is None:
            continue
        g, _partly = to_crop_geom(m["kind"], m["geom"], c["box"])
        out.append((c["k"], {**m, "geom": g}))
    return out


def draft_guide(pptx, guide_id, stations, crops_of, store=None):
    """Auto-draft marks for the pictures of one guide. crops_of(slide) = [{"k", "box"}]. -> {"marks": n, "linked": n, "dropped": n}. Only DRAFT marks are written."""
    from pptx import Presentation
    store = store or MarkStore()
    prs = Presentation(str(pptx))
    size = (prs.slide_width, prs.slide_height)
    station_of = {s: st for st in stations for s in st["slides"]}
    total = linked = dropped = 0
    for n, slide in enumerate(prs.slides, 1):
        crops = crops_of(n)
        if not crops or n not in station_of:
            continue
        marks = draft_slide(slide, size, station_of[n]["steps"])
        mine = to_crops(marks, crops)
        dropped += len(marks) - len(mine)
        for c in crops:
            made = store.replace_auto_drafts(guide_id, n, [m for k, m in mine if k == c["k"]], crop=c["k"], source="auto")
            total += len(made)
            linked += sum(m["step"] is not None for m in made)
    return {"marks": total, "linked": linked, "dropped": dropped}
