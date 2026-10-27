"""The ONLY place that says which web sites the fallback may read. Nothing outside this list is ever fetched.

To change what is allowed, edit SITES below (and nothing else). Each site lists the exact host names the program may
contact and, optionally, a path prefix a page URL must start with.

  NLM MeSH (NCBI E-utilities)   the US National Library of Medicine's anatomical vocabulary: a short, authoritative definition
                                (scope note) of a structure, through the free NCBI E-utilities (no key). StatPearls (NCBI
                                Bookshelf) was tried first, but its pages are behind a reCAPTCHA and E-utilities return only
                                titles for it, so it can be reached only through Tavily (see below), never by scraping.
  MedlinePlus                   US National Library of Medicine patient-level health topics, through its free web service
  Wikipedia                     approved by Dr. Inglis (2026-10-19) and ON by default; WEB_ALLOW_WIKIPEDIA=off turns it off. Asked first
                                in the web tier; MeSH and MedlinePlus supplement it. Text is CC BY-SA 4.0 (credited in the Sources tab).
  Tavily (optional)             if TAVILY_API_KEY is set, Tavily is used to search, restricted to the domains above, and its
                                results are still dropped unless the page URL is on the list. Tavily itself is only the search
                                service, never a source.

Env: WEB_FALLBACK (on|off, default on: it passed the live checks on 2026-10-19), WEB_ALLOW_WIKIPEDIA (on|off, default on).
"""
import os
from urllib.parse import urlparse

from dotenv import load_dotenv

SITES = [
    {"id": "mesh", "name": "NLM MeSH and StatPearls (NCBI, National Library of Medicine)", "short": "NLM MeSH", "default": True,
     "api_hosts": ["eutils.ncbi.nlm.nih.gov"],
     "page_hosts": ["www.ncbi.nlm.nih.gov"], "page_prefix": ("/mesh/", "/books/"),
     "tavily_domain": "ncbi.nlm.nih.gov"},
    {"id": "medlineplus", "name": "MedlinePlus (US National Library of Medicine)", "short": "MedlinePlus", "default": True,
     "api_hosts": ["wsearch.nlm.nih.gov"],
     "page_hosts": ["medlineplus.gov"], "page_prefix": "/",
     "tavily_domain": "medlineplus.gov"},
    {"id": "wikipedia", "name": "Wikipedia", "short": "Wikipedia", "default": True, "env": "WEB_ALLOW_WIKIPEDIA",
     "license": "Wikipedia, CC BY-SA 4.0",
     "api_hosts": ["en.wikipedia.org"],
     "page_hosts": ["en.wikipedia.org"], "page_prefix": "/wiki/",
     "tavily_domain": "en.wikipedia.org"},
]
TAVILY_HOST = "api.tavily.com"        # search service only (used when TAVILY_API_KEY is set); never a source of text

MAX_PASSAGES = 3
PASSAGE_CHARS = 1500
TOTAL_TIMEOUT = 6.0
CACHE_DAYS = 7


def _flag(name, default):
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    return (os.environ.get(name) or default).strip().lower() in ("on", "1", "true", "yes")


def web_fallback_on():
    return _flag("WEB_FALLBACK", "on")


def site_enabled(site):
    if site.get("env"):
        return _flag(site["env"], "on" if site["default"] else "off")
    return site["default"]


def enabled_sites():
    return [s for s in SITES if site_enabled(s)]


def tavily_key():
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    return os.environ.get("TAVILY_API_KEY") or ""


def tavily_domains():
    return [s["tavily_domain"] for s in enabled_sites()]


def _host_ok(url, hosts, prefix=""):
    p = urlparse(url)
    prefixes = (prefix,) if isinstance(prefix, str) else tuple(prefix)
    return p.scheme == "https" and (p.hostname or "").lower() in hosts and p.path.startswith(prefixes or ("/",))


def api_url_allowed(url):
    """True if `url` is a service endpoint of an enabled site (or the Tavily search service when a key is set)."""
    if tavily_key() and _host_ok(url, [TAVILY_HOST]):
        return True
    return any(_host_ok(url, s["api_hosts"]) for s in enabled_sites())


def page_url_allowed(url):
    return any(_host_ok(url, s["page_hosts"], s["page_prefix"]) for s in enabled_sites())


def url_allowed(url):
    return api_url_allowed(url) or page_url_allowed(url)


def site_for(url):
    """The enabled site a page URL belongs to, or None."""
    for s in enabled_sites():
        if _host_ok(url, s["page_hosts"] + s["api_hosts"], ""):
            return s
    return None


class NotAllowed(Exception):
    pass


def check(url):
    """Raise NotAllowed unless `url` is on the list. Every network call goes through this."""
    if not url_allowed(url):
        raise NotAllowed(urlparse(url).hostname or "?")
    return url


def allowed_list():
    """[(name, hosts, on_by_default, currently_enabled)] for the README / instructor screen."""
    return [(s["name"], s["page_hosts"] + [h for h in s["api_hosts"] if h not in s["page_hosts"]], s["default"], site_enabled(s))
            for s in SITES]
