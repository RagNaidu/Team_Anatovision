"""Text positions in an image. One function, `read(image)`, with the backend chosen at run time:
  * Apple Vision through ocrmac (macOS, local, no model download) - used on this machine;
  * pytesseract when the tesseract program is installed;
  * otherwise None: callers then skip the steps that need OCR and say so.
Boxes are normalised 0-1 with the origin at the TOP left: [x0, y0, x1, y1]. Nothing is sent over the network."""
import shutil

_BACKEND = {}


def backend():
    if "b" not in _BACKEND:
        b = None
        try:
            from ocrmac import ocrmac  # noqa: F401
            b = "vision"
        except Exception:
            if shutil.which("tesseract"):
                try:
                    import pytesseract  # noqa: F401
                    b = "tesseract"
                except Exception:
                    b = None
        _BACKEND["b"] = b
    return _BACKEND["b"]


def read(image, level="accurate"):
    """-> [{"text", "box": [x0, y0, x1, y1], "conf"}] one per recognised LINE of text; [] if no backend."""
    b = backend()
    if b == "vision":
        from ocrmac import ocrmac
        out = []
        for text, conf, (x, y, w, h) in ocrmac.OCR(image, recognition_level=level).recognize():
            out.append({"text": text.strip(), "conf": float(conf), "box": [x, 1 - (y + h), x + w, 1 - y]})      # Vision's origin is bottom-left
        return [o for o in out if o["text"]]
    if b == "tesseract":
        import pytesseract
        W, H = image.size
        d = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        lines = {}
        for i, t in enumerate(d["text"]):
            if t.strip() and float(d["conf"][i]) > 0:
                k = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
                lines.setdefault(k, []).append(i)
        out = []
        for idx in lines.values():
            x0 = min(d["left"][i] for i in idx) / W
            y0 = min(d["top"][i] for i in idx) / H
            x1 = max(d["left"][i] + d["width"][i] for i in idx) / W
            y1 = max(d["top"][i] + d["height"][i] for i in idx) / H
            out.append({"text": " ".join(d["text"][i] for i in idx), "box": [x0, y0, x1, y1], "conf": sum(float(d["conf"][i]) for i in idx) / len(idx) / 100})
        return out
    return []
