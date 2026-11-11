"""Draft label pins (and arrows where a leader line can be seen) from the TEXT that is part of a cropped picture, found by OCR.

For each cropped picture: OCR finds the text lines; a line becomes a candidate label when it is short (at most 6 words), is not step text, is not a number, and its words are
structure names the guide or its lecture notes use (at least 60% of its words of 4+ letters appear in that vocabulary). A candidate is linked to the station step whose text
contains its words, if any. If a thin dark line starts at the label and ends elsewhere (Hough lines on the picture) the pin goes on the structure the line points to and an arrow
from the label to that end is drafted too; otherwise the pin sits just left of the text. Labels already drafted from the slide's own shapes are not duplicated.
Everything is a DRAFT (source "ocr"); nothing is approved here, and the instructor sees every one in the editor.
"""
import re

from src import guide_crops as GC
from src import ocr
from src.guide_autodraft import match_step

MIN_CONF = 0.45
SAME_SPOT = 0.05


def long_words(text):
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in GC.STOP}


def vocabulary(*texts):
    v = set()
    for t in texts:
        v |= long_words(t)
    return v


def merge_lines(lines):
    """OCR returns one line at a time; a label set in two or three lines (\"Great / Saphenous / Vein\") is joined into one when the lines are stacked closely and line up."""
    ls = sorted([l for l in lines if l["conf"] >= MIN_CONF], key=lambda l: (round(l["box"][1], 3), l["box"][0]))
    out = []
    for l in ls:
        x0, y0, x1, y1 = l["box"]
        for g in out:
            gx0, gy0, gx1, gy1 = g["box"]
            h = max(y1 - y0, gy1 - gy0)
            centred = abs((x0 + x1) / 2 - (gx0 + gx1) / 2) <= 0.6 * max(x1 - x0, gx1 - gx0) or abs(x0 - gx0) <= 0.02 or abs(x1 - gx1) <= 0.02
            if 0 <= y0 - gy1 <= 0.9 * h and centred and len((g["text"] + " " + l["text"]).split()) <= 6 and g.get("n", 1) < 3:
                g["text"] += " " + l["text"]
                g["box"] = [min(x0, gx0), min(y0, gy0), max(x1, gx1), max(y1, gy1)]
                g["conf"] = min(g["conf"], l["conf"])
                g["n"] = g.get("n", 1) + 1
                break
        else:
            out.append({**l, "box": list(l["box"])})
    return out


def candidate(line, steps):
    t = " ".join(line["text"].split()).strip(" .,;:")
    if line["conf"] < MIN_CONF or not 3 <= len(t) <= 48 or len(t.split()) > 6 or re.fullmatch(r"[\d\W]+", t):
        return None
    if GC.is_step_text(t, steps) or GC.FOOTER.search(t):
        return None
    return t


def find_leader(gray, box):
    """A leader line from the label's box: -> ((x, y) at the label, (x, y) far end) normalised, or None. gray = a 2-D uint8 array."""
    import cv2
    import numpy as np
    H, W = gray.shape
    x0, y0, x1, y1 = box
    pad = 0.012
    ex = (max(0, int((x0 - 0.42) * W)), max(0, int((y0 - 0.42) * H)), min(W, int((x1 + 0.42) * W)), min(H, int((y1 + 0.42) * H)))
    sub = gray[ex[1]:ex[3], ex[0]:ex[2]]
    if sub.size == 0:
        return None
    edges = cv2.Canny(sub, 60, 160)
    segs = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=30, minLineLength=max(14, int(0.04 * W)), maxLineGap=4)
    if segs is None:
        return None
    best, best_len = None, 0.0
    near = (x0 - pad, y0 - pad * 1.5, x1 + pad, y1 + pad * 1.5)
    for s in np.array(segs).reshape(-1, 4):
        p = (float(s[0] + ex[0]) / W, float(s[1] + ex[1]) / H)
        q = (float(s[2] + ex[0]) / W, float(s[3] + ex[1]) / H)
        for a, b in ((p, q), (q, p)):
            in_a = near[0] <= a[0] <= near[2] and near[1] <= a[1] <= near[3]
            in_b = x0 <= b[0] <= x1 and y0 <= b[1] <= y1
            length = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
            if in_a and not in_b and 0.04 <= length <= 0.4 and length > best_len:
                best, best_len = (a, b), length
    return best


def draft_picture(img, steps, vocab, existing=()):
    """img = the cropped picture (PIL). existing = [(x, y, text)] labels already drafted on it. -> ([marks], {"lines": n, "step_text_lines": n})"""
    import numpy as np
    lines = ocr.read(img)
    n_lines = len(lines)
    lines = merge_lines(lines) + [l for l in lines if l["conf"] < MIN_CONF]
    gray = np.array(img.convert("L"))
    marks, step_text = [], 0
    for ln in lines:
        t = candidate(ln, steps)
        if t is None:
            if GC.is_step_text(ln["text"], steps) and ln["conf"] >= MIN_CONF:
                step_text += 1
            continue
        toks = long_words(t)
        if not toks or len(toks & vocab) / len(toks) < 0.6:
            continue
        x0, y0, x1, y1 = ln["box"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if any(abs(ex - cx) < SAME_SPOT and abs(ey - cy) < SAME_SPOT or long_words(et) == toks for ex, ey, et in existing):
            continue
        step = match_step(t, steps)
        leader = find_leader(gray, (x0, y0, x1, y1))
        r4 = lambda v: round(min(1.0, max(0.0, v)), 4)
        if leader:
            (ax, ay), (bx, by) = leader
            marks.append({"kind": "label", "geom": {"x": r4(bx), "y": r4(by)}, "text": t[:80], "step": step})
            marks.append({"kind": "arrow", "geom": {"from": [r4(ax), r4(ay)], "to": [r4(bx), r4(by)]}, "text": "", "step": step})
        elif step is not None:                       # no leader line to follow: a pin beside the text is only useful when it ties the label to a step
            marks.append({"kind": "label", "geom": {"x": r4(x0 - 0.02), "y": r4(cy)}, "text": t[:80], "step": step})
    return marks, {"lines": n_lines, "step_text_lines": step_text}
