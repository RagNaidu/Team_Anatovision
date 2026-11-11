"""Request every distinct OpenStax section URL in the ingested book and record which ones really exist.
Writes data/processed/openstax_url_check.json: {"checked": date, "ok": [urls], "bad": {url: reason}}.
The app links a source to its exact section only if the URL is in "ok"; otherwise it links the book's contents page.
.venv/bin/python scripts/verify_openstax_urls.py"""
import json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
import requests
ROOT = Path(__file__).resolve().parents[1]
rows = [json.loads(l) for l in open(ROOT / "data/processed/openstax_sections.jsonl")]
urls = sorted({r["source_url"] for r in rows if r["source_url"]})
UA = {"User-Agent": "AnatoVision/1.0 (UB CDA 650 course project)"}

def check(u):
    for attempt in (1, 2):
        try:
            r = requests.get(u, headers=UA, timeout=20)
            if r.status_code == 200 and "pages/" in r.url and not re.search(r"<title>\s*OpenStax\s*</title>", r.text[:5000]):
                return u, None
            reason = f"HTTP {r.status_code}"
        except Exception as e:
            reason = type(e).__name__
        time.sleep(1)
    return u, reason

with ThreadPoolExecutor(4) as ex:
    res = list(ex.map(check, urls))
out = {"checked": date.today().isoformat(), "ok": [u for u, why in res if not why], "bad": {u: why for u, why in res if why}}
(ROOT / "data/processed/openstax_url_check.json").write_text(json.dumps(out, indent=1))
print(len(out["ok"]), "ok,", len(out["bad"]), "not verified", list(out["bad"].items())[:10])
