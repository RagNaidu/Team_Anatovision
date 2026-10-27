"""Trusted-web fallback: up to 3 short passages from the sites in src/web_sources.py, for a question the notes, the dissection
guides and OpenStax could not answer.

  lookup(query) -> WebResult(passages, error, cached, seconds)
  passage = {"id", "title", "site", "site_id", "url", "text" (<= ~1,500 characters), "retrieved" (date)}

Rules: only hosts on the allowlist are ever contacted (src/web_sources.check on every request, no redirects followed);
6 seconds in total for everything; results cached 7 days in data/web_cache/ (git-ignored); ANY error or an empty result
returns no passages and the caller falls back to the ordinary "not covered" message. The text is fetched, never generated:
the answer model may use only these passages (see qa.answer_question, mode "web").

Sources, in this order: Wikipedia (MediaWiki API, en.wikipedia.org only; on unless WEB_ALLOW_WIKIPEDIA=off), then NLM MeSH definitions
and MedlinePlus health topics as a supplement; Tavily (restricted to the allowlisted domains) only when TAVILY_API_KEY is set.
"""
import hashlib
import html
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

from src import terms, web_sources

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "web_cache"
USER_AGENT = "AnatoVision/1.0 (UB CDA 650 course project)"      # generic on purpose: no personal name, email or username
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
MEDLINE = "https://wsearch.nlm.nih.gov/ws/query"
WIKI_API = "https://en.wikipedia.org/w/api.php"
TAVILY = "https://api.tavily.com/search"
MAX_KEYWORDS = 6
WIKI_GAP = 0.7
NCBI_GAP = 0.4            # seconds between NCBI or Wikipedia calls (NCBI's keyless limit is 3 per second)


@dataclass
class WebResult:
    passages: list = field(default_factory=list)
    error: str = ""
    cached: bool = False
    seconds: float = 0.0
    keywords: list = field(default_factory=list)


class Http:
    """requests with the allowlist in front of every call. Redirects are not followed (a redirect could leave the list)."""
    _ncbi_lock = threading.Lock()
    _ncbi_last = 0.0

    def __init__(self):
        import requests
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT

    _last = {}

    def _gap(self, url):
        """Space out calls per host: NCBI allows 3 a second without a key; Wikipedia answers 429 to bursts."""
        for host, gap in (("eutils.ncbi.nlm.nih.gov", NCBI_GAP), ("en.wikipedia.org", WIKI_GAP)):
            if host in url:
                with Http._ncbi_lock:
                    wait_for = gap - (time.monotonic() - Http._last.get(host, 0.0))
                    if wait_for > 0:
                        time.sleep(wait_for)
                    Http._last[host] = time.monotonic()

    def get(self, url, params=None, timeout=4.0):
        for attempt in (1, 2):                      # one retry, only for a busy server (429 / 5xx) or a dropped connection
            self._gap(web_sources.check(url))
            try:
                r = self.s.get(url, params=params, timeout=timeout, allow_redirects=False)
                if r.status_code in (429, 500, 502, 503, 504) and attempt == 1:
                    try:
                        time.sleep(min(float(r.headers.get("Retry-After", 0.6)), 2.2))
                    except ValueError:
                        time.sleep(0.6)
                    continue
                return self._ok(r)
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(0.3)

    def post(self, url, json_body, timeout=4.0):
        r = self.s.post(web_sources.check(url), json=json_body, timeout=timeout, allow_redirects=False)
        return self._ok(r)

    @staticmethod
    def _ok(r):
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        return r


def keywords(query):
    return terms.meaningful_words(query)[:MAX_KEYWORDS]


def clean_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def trim(text, limit=web_sources.PASSAGE_CHARS):
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return cut[:end + 1] if end > limit * 0.5 else cut.rsplit(" ", 1)[0] + " ..."


def relevant(text, kws):
    """Every keyword of a one- or two-word question (by stem) must appear in the passage; from three words, 60% of them."""
    if not kws:
        return False
    have = terms.stem_set(text)
    need = len(kws) if len(kws) <= 2 else -(-len(kws) * 3 // 5)
    return sum(terms.stem(k) in have for k in kws) >= need


def title_relevant(title, kws):
    """Looser gate used to FILL A GAP in a textbook answer: the page's title shares distinctive words with the question
    ('Femoral triangle' for 'boundaries and contents of the femoral triangle'); one shared word is not enough once the question has 3+."""
    have = terms.stem_set(title)
    return sum(terms.stem(k) in have for k in kws) >= (2 if len(kws) > 2 else 1)


def _passage(site_id, title, url, text):
    site = next(s for s in web_sources.SITES if s["id"] == site_id)
    pid = "web-" + hashlib.sha1(url.encode()).hexdigest()[:10]
    return {"id": pid, "title": re.sub(r"[\[\]]", "", clean_html(title)).strip(), "site": site["short"], "site_id": site_id,
            "license": site.get("license", ""),
            "url": url, "text": trim(clean_html(text)), "retrieved": date.today().isoformat()}


# ----------------------------------------------------------------------------
# one function per source: each returns a list of passages (or raises; the caller treats that as "no result")
# ----------------------------------------------------------------------------

def from_mesh(kws, http, left):
    term = " ".join(kws)
    r = http.get(EUTILS + "esearch.fcgi", {"db": "mesh", "term": term, "retmode": "json", "retmax": 3}, left())
    ids = r.json()["esearchresult"]["idlist"][:3]
    if not ids:
        return []
    r = http.get(EUTILS + "esummary.fcgi", {"db": "mesh", "id": ",".join(ids), "retmode": "json"}, left())
    data = r.json()["result"]
    out = []
    for uid in data.get("uids", ids):
        d = data.get(uid) or {}
        note, names = (d.get("ds_scopenote") or "").strip(), d.get("ds_meshterms") or []
        if not note or not names:
            continue
        also = [n for n in names[1:] if not n.lower().startswith(names[0].lower())][:8]
        text = f"{names[0]}: {note}" + (f" Other names: {'; '.join(also)}." if also else "")
        if relevant(" ".join(names) + " " + note, kws):
            out.append(_passage("mesh", f"MeSH: {names[0]}", f"https://www.ncbi.nlm.nih.gov/mesh/{uid}", text))
    return out


def from_medlineplus(kws, http, left):
    r = http.get(MEDLINE, {"db": "healthTopics", "term": " ".join(kws), "retmax": 3}, left())
    out = []
    for doc in re.findall(r"<document\b[^>]*>.*?</document>", r.text, re.S):
        url = re.search(r'url="([^"]+)"', doc)
        title = re.search(r'<content name="title">(.*?)</content>', doc, re.S)
        summary = re.search(r'<content name="FullSummary">(.*?)</content>', doc, re.S)
        if not (url and title and summary):
            continue
        link, text = html.unescape(url.group(1)), clean_html(html.unescape(summary.group(1)))
        if web_sources.page_url_allowed(link) and relevant(clean_html(html.unescape(title.group(1))) + " " + text, kws):
            out.append(_passage("medlineplus", html.unescape(title.group(1)), link, text))
    return out[:2]


ANATOMY_WORDS = re.compile(
    r"anatom|\bmuscle|\bnerve|\bartery|\bvein\b|\bbone\b|\bgland|ganglion|\bbrain|cortex|\bduct\b|\bligament|tendon|\bfascia|"
    r"\blobe\b|gyrus|sulcus|fissure|foramen|\bcavity|\borgan\b|\btissue|membrane|\bjoint|\bnucleus|\bplexus|\bsinus|"
    r"\bsphincter|\bvessel|\bcartilage|\bepitheli|\bcranial|\bthoracic|\babdomin|\bpelvi|\bcerebr|\bspinal|\bvertebra|\blymph", re.I)
SECTION_RE = re.compile(r"^==+\s*(.+?)\s*==+\s*$", re.M)
SKIP_SECTIONS = {"references", "external links", "see also", "further reading", "notes", "citations", "sources", "bibliography",
                 "history", "etymology", "in popular culture", "gallery", "additional images"}


def wiki_url(title):
    return "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))


NOT_ANATOMY_CATS = re.compile(r"\d{4} (?:births|deaths)|anatomists|physicians|surgeons|scientists|people|biograph|medical procedures|"
                              r"disambiguation|drugs|medications|pharmaceutical", re.I)


def is_anatomy_page(page):
    """A page about the body, judged from its categories (Category:...anatomy) and its opening text. Disambiguation pages, people
    (an anatomist named for a structure), procedures and pages about something else are not."""
    cats = " ".join(c.get("title", "") for c in page.get("categories", []))
    if NOT_ANATOMY_CATS.search(cats):
        return False
    if re.search(r"anatom|histology|physiology|neuro(?:science|logy)|embryolog", cats, re.I):
        return True
    return len(ANATOMY_WORDS.findall(page.get("extract", "")[:600])) >= 2          # categories list only some of a page's tags


def best_section(full_text, kws, limit=web_sources.PASSAGE_CHARS):
    """The page's intro plus the (up to two) sections that share the most keywords with the question, trimmed to about `limit` characters
    ('Boundaries' and 'Contents' of a structure may be two sections)."""
    parts = SECTION_RE.split(full_text)
    intro = parts[0].strip()
    sections = [(parts[i].strip(), parts[i + 1].strip()) for i in range(1, len(parts) - 1, 2)]
    sections = [(h, t) for h, t in sections if h.lower() not in SKIP_SECTIONS and len(t) > 80]
    want = {terms.stem(k) for k in kws}
    pref = re.compile(r"structure|anatomy|location|description|course|function|relations|morpholog|boundar|contents", re.I)
    scored = sorted(((len(want & terms.stem_set(h)) * 2 + len(want & terms.stem_set(t)) + (0.5 if pref.search(h) else 0), -i, h, t)
                     for i, (h, t) in enumerate(sections)), reverse=True)
    if not scored:
        return trim(intro, limit)
    chosen = sorted(scored[:2], key=lambda r: -r[1]) if len(scored) > 1 and scored[1][0] >= 1 else scored[:1]     # page order
    intro_part = trim(intro, 450 if len(chosen) > 1 else 700)
    room = max(250, (limit - len(intro_part)) // len(chosen) - 12)
    return trim(intro_part + "".join(f"\n\n{h}: {trim(t, room)}" for _, _, h, t in chosen), limit)


def from_wikipedia(kws, http, left, loose=False):
    """Search 'keywords anatomy' (so an ambiguous title finds the body part), drop disambiguation and non-anatomy pages, then for up
    to 3 pages read the whole text and keep the intro plus the most relevant section."""
    base = {"action": "query", "format": "json", "formatversion": 2}
    r = http.get(WIKI_API, {**base, "generator": "search", "gsrsearch": " ".join(kws) + " anatomy", "gsrlimit": 8, "gsrnamespace": 0,
                            "prop": "pageprops|extracts|categories", "ppprop": "disambiguation", "exintro": 1, "explaintext": 1,
                            "exlimit": 8, "cllimit": 40}, left())
    pages = sorted((r.json().get("query") or {}).get("pages") or [], key=lambda p: p.get("index", 99))
    keep = [p for p in pages if "disambiguation" not in (p.get("pageprops") or {}) and p.get("extract")
            and "(disambiguation)" not in p["title"] and is_anatomy_page(p)
            and (title_relevant(p["title"], kws) if loose else relevant(p["title"] + " " + p["extract"], kws))][:web_sources.MAX_PASSAGES]
    if not keep:
        return []

    def full(p):
        d = http.get(WIKI_API, {**base, "titles": p["title"], "prop": "extracts", "explaintext": 1, "exsectionformat": "wiki"}, left())
        pg = (d.json().get("query") or {}).get("pages") or []
        return pg[0].get("extract", "") if pg else ""
    out = []
    for k, p in enumerate(keep):
        text = trim(p["extract"])
        if k == 0:                                         # Wikipedia asks for few requests: only the best page is read in full
            try:
                text = best_section(full(p), kws) or text
            except Exception:                              # a failed section fetch: the intro alone is still good text
                pass
        out.append(_passage("wikipedia", p["title"], wiki_url(p["title"]), text))
    return out


def from_tavily(query, kws, http, left):
    key = web_sources.tavily_key()
    r = http.post(TAVILY, {"api_key": key, "query": query[:300], "include_domains": web_sources.tavily_domains(),
                           "max_results": 3, "search_depth": "basic"}, left())
    out = []
    for item in r.json().get("results", []):
        url = item.get("url", "")
        site = web_sources.site_for(url)
        if site and web_sources.page_url_allowed(url) and relevant(item.get("title", "") + " " + item.get("content", ""), kws):
            out.append(_passage(site["id"], item.get("title") or site["short"], url, item.get("content", "")))
    return out


# ----------------------------------------------------------------------------
# cache
# ----------------------------------------------------------------------------

def cache_key(kws, sources=None, loose=False):
    sites = ",".join(sorted(s["id"] for s in web_sources.enabled_sites())) + ("+tavily" if web_sources.tavily_key() else "")
    sites += ("|only:" + ",".join(sorted(sources)) if sources else "") + ("|loose" if loose else "")
    return hashlib.sha1((" ".join(sorted(terms.stems_of(kws))) + "|" + sites).encode()).hexdigest()


def cache_get(kws, now=None, cache_dir=None, sources=None, loose=False):
    path = Path(cache_dir or CACHE_DIR) / f"{cache_key(kws, sources, loose)}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        age = ((now or datetime.now(timezone.utc)) - datetime.fromisoformat(data["ts"])).total_seconds()
        if age < web_sources.CACHE_DAYS * 86400:
            return data["passages"]
    except (OSError, ValueError, KeyError):
        pass
    return None


def cache_put(kws, passages, now=None, cache_dir=None, sources=None, loose=False):
    d = Path(cache_dir or CACHE_DIR)
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{cache_key(kws, sources, loose)}.json").write_text(json.dumps(
            {"ts": (now or datetime.now(timezone.utc)).isoformat(), "keywords": kws, "passages": passages}, ensure_ascii=False),
            encoding="utf-8")
    except OSError:
        pass


# ----------------------------------------------------------------------------
# lookup
# ----------------------------------------------------------------------------

def lookup(query, *, http=None, now=None, cache_dir=None, timeout=web_sources.TOTAL_TIMEOUT, sources=None, loose=False):
    """-> WebResult. Never raises. sources: only these site ids (e.g. ("wikipedia",)); loose: the gap-filling gate (see title_relevant)."""
    t0 = time.monotonic()
    kws = keywords(query)
    res = WebResult(keywords=kws)
    if not kws:
        return res
    try:
        hit = cache_get(kws, now, cache_dir, sources, loose)
        if hit is not None:
            res.passages, res.cached = hit, True
            res.seconds = round(time.monotonic() - t0, 2)
            return res
        http = http or Http()
        deadline = t0 + timeout

        def left():
            remaining = deadline - time.monotonic()
            if remaining <= 0.05:
                raise TimeoutError("web lookup timed out")
            return min(remaining, 4.0)

        jobs = {}
        ex = ThreadPoolExecutor(max_workers=4)
        want = lambda sid: sources is None or sid in sources
        if want("mesh"):
            jobs[ex.submit(from_mesh, kws, http, left)] = "mesh"
        if want("medlineplus"):
            jobs[ex.submit(from_medlineplus, kws, http, left)] = "medlineplus"
        if want("wikipedia") and any(s["id"] == "wikipedia" for s in web_sources.enabled_sites()):
            jobs[ex.submit(from_wikipedia, kws, http, left, loose)] = "wikipedia"
        if want("tavily") and web_sources.tavily_key():
            jobs[ex.submit(from_tavily, query, kws, http, left)] = "tavily"
        done, pending = wait(list(jobs), timeout=max(0.1, deadline - time.monotonic()))
        ex.shutdown(wait=False, cancel_futures=True)
        by_source, errors = {}, []
        for f in done:
            try:
                by_source[jobs[f]] = f.result()
            except Exception as exc:
                errors.append(f"{jobs[f]}: {type(exc).__name__}")
        if pending:
            errors.append("timeout")
        order = ["wikipedia", "tavily", "mesh", "medlineplus"]      # Wikipedia first; the others supplement what is left
        seen, merged = set(), []
        for k in order:
            for p in by_source.get(k, []):
                if p["url"] not in seen and web_sources.page_url_allowed(p["url"]):
                    seen.add(p["url"])
                    merged.append(p)
        res.passages = merged[:web_sources.MAX_PASSAGES]
        res.error = "; ".join(errors)
        if not errors:                     # an empty answer is cached too, but an error or timeout never is
            cache_put(kws, res.passages, now, cache_dir, sources, loose)
    except Exception as exc:               # silent fallback: the caller shows the ordinary "not covered" message
        res.passages, res.error = [], type(exc).__name__
    res.seconds = round(time.monotonic() - t0, 2)
    return res
