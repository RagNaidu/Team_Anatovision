"""Stage 1: keyword / term lookup and the trusted-web fallback. The model, the search and the network are all faked."""
import json
import time
from types import SimpleNamespace

import numpy as np
import pytest

from src import service, usage, web_fallback, web_sources
from src import query as qry
from src import student_report
from src import student_view as sv
from src import term_lookup
from src.modes import qa
from src.retrieval.search import Searcher
from tests.test_service import CLOSING, reply
from tests.test_student_safe import EMPTY, QSearcher, SeqClient


def note(cid, lecture, section, text, st="notes"):
    return {"id": cid, "source_type": st, "priority": 2, "lecture": lecture, "breadcrumb": f"{lecture} > {section}",
            "section_path": [section], "text": text, "section_number": "", "source_url": ""}


def ref(cid, text, num="1.2"):
    return {"id": cid, "source_type": "open_text", "priority": 3, "lecture": "Chapter 1",
            "breadcrumb": "OpenStax A&P 2e > Chapter 1 > Sec", "section_path": ["Sec"], "text": text, "section_number": num,
            "source_url": "https://openstax.org/x"}


L5, L8, L22 = "Lecture 05 - The Axilla", "Lecture 08 - Thigh", "Lecture 22 - Oral Cavity"
CHUNKS = [
    note("a", L5, "Boundaries", "The apex of the axilla is the cervico-axillary canal, between the clavicle and the first rib."),
    note("b", L8, "Femoral Triangle", "The apex of the femoral triangle is where the sartorius crosses the adductor longus."),
    note("c", L22, "Tongue", "The apex of the tongue is its free anterior tip. It touches the incisors."),
    note("d", L22, "Palate", "The soft palate hangs from the hard palate."),
    ref("r1", "The apex of the heart points to the left hip and rests on the diaphragm."),
]


class TermSearcher(QSearcher):
    """The ordinary fake search plus the REAL keyword_groups / access_filter over the same chunks."""
    keyword_groups = Searcher.keyword_groups
    access_filter = Searcher.access_filter
    note_lectures = Searcher.note_lectures
    _stem_sets = Searcher._stem_sets
    group_key = staticmethod(Searcher.group_key)

    def __init__(self, chunks, **kw):
        super().__init__(chunks, **kw)
        self.bm25 = SimpleNamespace(get_scores=lambda q: np.ones(len(self.chunks)))

    def search(self, question, k=5, allowed_lectures=None):
        """Like the real search, access is decided by access_filter (notes AND dissection guides follow the grants)."""
        from src.retrieval.search import Hit, SearchResult
        self.queries.append((question, k))
        self.calls.append(allowed_lectures)
        _, mask = self.access_filter(allowed_lectures)
        keep = [c for i, c in enumerate(self.chunks) if mask is None or mask[i]]
        hits = [Hit(c, 0.03, 0.03, self.cosine, 1.0, 1, 1) for c in keep]
        return SearchResult(question, self.found and bool(hits), hits, self.cosine if hits else 0.0,
                            "" if self.found else "best cosine 0.50 < 0.68")


def rt(chunks, answer=None, helper=(), web=None, **kw):
    runtime = service.Runtime(searcher=TermSearcher(chunks, **kw), next_of={}, client=SeqClient(answer or reply("x"), helper),
                              model="claude-sonnet-5-5", web_lookup=web)
    return runtime


def cite(c):
    return f"[{qa.cite_for(c)}]"


@pytest.fixture(autouse=True)
def web_on(monkeypatch):
    monkeypatch.setenv("WEB_FALLBACK", "on")
    monkeypatch.delenv("WEB_ALLOW_WIKIPEDIA", raising=False)      # the default is ON (approved 2026-10-19)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)


def ask(runtime, q, allowed=None, **kw):
    return service.ask(q, "", True, allowed, runtime=runtime, ctx=EMPTY, log=False, **kw)


# ---------------------------------------------------------------------------------------------------------------
# 1a: term lookup
# ---------------------------------------------------------------------------------------------------------------

def term_reply():
    lines = ["Apex appears in:",
             f"Boundaries (Lecture 05): the apex of the axilla is the cervico-axillary canal {cite(CHUNKS[0])}",
             f"Femoral Triangle (Lecture 08): the apex is where the sartorius crosses the adductor longus {cite(CHUNKS[1])}",
             f"Tongue (Lecture 22): the apex of the tongue is its free anterior tip {cite(CHUNKS[2])}",
             term_lookup.TERM_CLOSING]
    return reply("\n".join(lines))


@pytest.mark.parametrize("q", ["apex", "what is apex?", "What is the apex?", "define apex"])
def test_a_bare_term_gets_a_term_lookup_grouped_by_section_with_citations(q):
    runtime = rt(CHUNKS, term_reply())
    res = ask(runtime, q)
    assert res["status"] == "answered" and res["mode"] == "term" and res["term_places"] >= 3
    assert res["answer_text"].splitlines()[0] == "Apex appears in:"
    assert res["answer_text"].splitlines()[-1] == term_lookup.TERM_CLOSING
    assert [c["matched"] for c in res["citations"]] == [True, True, True] and res["n_unmatched"] == 0
    assert res["tier"] == "term"
    sent = runtime.client.answering()[0]
    body = json.dumps(sent)
    assert "appears in:" in body and "Femoral Triangle" in body and runtime.searcher.queries == []   # no ordinary search ran


def test_term_lookup_never_shows_more_than_six_places_and_puts_the_notes_before_openstax():
    many = [note(f"n{i}", f"Lecture {i:02d} - L{i}", f"Sec{i}", "The apex is here.") for i in range(8)] + [ref("r", "apex of heart")]
    found = TermSearcher(many).keyword_groups(["apex"], None, 6)
    assert len(found["hits"]) == 6 and found["n_groups"] == 9
    assert all(h.chunk["source_type"] == "notes" for h in found["hits"])
    assert len({h.chunk["lecture"] for h in found["hits"]}) == 6            # a different lecture each: distinct meanings first


def test_openstax_only_fills_the_places_the_notes_leave_empty():
    found = TermSearcher(CHUNKS).keyword_groups(["apex"], None, 6)
    assert [h.chunk["source_type"] for h in found["hits"]] == ["notes"] * 3 + ["open_text"]


def test_a_term_that_names_one_section_gets_the_ordinary_answer():
    chunks = [note("a", L8, "Sartorius", "The sartorius flexes the hip."), note("b", L8, "Femoral Triangle", "Sartorius forms a border.")]
    assert term_lookup.decide(TermSearcher(chunks), "sartorius").use == "normal"
    assert term_lookup.decide(TermSearcher(chunks), "What does the sartorius do?").use == "normal"


def test_real_questions_are_not_term_lookups():
    s = TermSearcher(CHUNKS)
    for q in ("What are the walls of the middle ear?", "where is the apex of the tongue", "How do I find the apex?"):
        assert term_lookup.decide(s, q).use == "normal", q


def test_a_term_found_in_one_place_only_falls_back_to_the_term_lookup_when_the_search_finds_nothing():
    chunks = [note("c", L22, "Tongue", "The frenulum anchors the tongue.")]
    runtime = rt(chunks, reply(f"Frenulum appears in:\nTongue (Lecture 22): it anchors the tongue {cite(chunks[0])}\n{term_lookup.TERM_CLOSING}"),
                 found=False, cosine=0.4)
    res = ask(runtime, "frenulum")
    assert res["status"] == "answered" and res["mode"] == "term" and res["citations"][0]["matched"]


def test_a_bare_term_with_no_match_anywhere_is_still_refused_and_never_searches_the_web():
    calls = []
    runtime = rt(CHUNKS, helper=["OTHER"], web=lambda q: calls.append(q), found=False, cosine=0.3)
    res = ask(runtime, "amoxicillin")
    assert res["status"] == "not_found" and res["reason"] == "not_anatomy" and res["answer_text"] == service.NOT_ANATOMY_MSG
    assert calls == [] and runtime.client.answering() == []


def test_a_follow_up_still_resolves_through_the_rewrite():
    runtime = rt([note("h", "Lecture 03 - Heart", "Chambers", "The apex of the heart is formed by the left ventricle.")],
                 reply("x"), helper=["apex of the heart chambers"])
    history = [{"question": "Describe the heart", "answer": "The heart has four chambers."}]
    res = ask(runtime, "What is its apex?", history=history)
    assert res["followup"] == "rewritten" and res["search_query"] == "apex of the heart chambers"
    assert res["mode"] == "normal" and runtime.searcher.queries[0][0] == "apex of the heart chambers"


def test_term_lookup_respects_the_lectures_a_student_may_open():
    found = TermSearcher(CHUNKS).keyword_groups(["apex"], [L5])
    assert {h.chunk["lecture"] for h in found["hits"]} == {L5, "Chapter 1"} and found["n_groups"] == 2


def test_the_term_lookup_answer_for_a_student_has_no_instructor_detail():
    runtime = rt(CHUNKS, term_reply())
    out = service.ask_for_student("apex", "", True, None, runtime=runtime, ctx=EMPTY, log=False)
    assert out["view"]["term"] is True and sv.leaks(out["view"]) == []


# ---------------------------------------------------------------------------------------------------------------
# 1b: the web, last
# ---------------------------------------------------------------------------------------------------------------

P1 = {"id": "web-1", "title": "MeSH: Circle of Willis", "site": "NLM MeSH", "site_id": "mesh",
      "url": "https://www.ncbi.nlm.nih.gov/mesh/68002941", "retrieved": "2026-10-19",
      "text": "Circle of Willis: A polygonal anastomosis at the base of the brain formed by the internal carotid and the cerebral arteries."}
P2 = {"id": "web-2", "title": "Brain Aneurysm", "site": "MedlinePlus", "site_id": "medlineplus",
      "url": "https://medlineplus.gov/brainaneurysm.html", "retrieved": "2026-10-19",
      "text": "An aneurysm is a bulge in the wall of an artery."}
WEB_CITE = "[Web: MeSH: Circle of Willis (NLM MeSH)]"
WEB_REPLY = reply(f"The circle of Willis is a polygonal anastomosis of arteries at the base of the brain {WEB_CITE}.\n{CLOSING}",
                  basis="web")


def web_runtime(chunks=(), answer=WEB_REPLY, helper=("ANATOMY",), passages=(P1,), calls=None, **kw):
    calls = calls if calls is not None else []

    def lookup(q):
        calls.append(q)
        return web_fallback.WebResult(passages=list(passages), seconds=0.4)
    return rt(list(chunks) or [ref("r", "The heart pumps blood.")], answer, helper, web=lookup, **{"found": False, "cosine": 0.4, **kw}), calls


def test_the_web_is_asked_only_after_the_notes_and_openstax_found_nothing():
    runtime, calls = web_runtime()
    res = ask(runtime, "What is the circle of Willis?")
    assert calls == ["What is the circle of Willis?"] and res["status"] == "answered" and res["mode"] == "web"
    assert res["web"] and res["tier"] == "web" and res["basis"] == "web" and res["citations"][0]["matched"]
    assert res["web_urls"] == [P1["url"]]


def test_the_web_is_never_asked_when_the_notes_cover_it():
    chunks = [note("a", L5, "Walls", "The walls are the muscles of the axilla.")]
    covered = reply(f"The walls are muscles {cite(chunks[0])}.\n{CLOSING}")
    calls = []
    runtime = rt(chunks, covered, web=lambda q: calls.append(q))
    res = ask(runtime, "what are the walls of the axilla?")
    assert res["status"] == "answered" and not res["web"] and calls == []


def test_clinical_advice_and_non_anatomy_questions_never_search_the_web():
    for scope, reason in (("CLINICAL", "clinical_advice"), ("OTHER", "not_anatomy")):
        runtime, calls = web_runtime(helper=(scope,))
        res = ask(runtime, "what dose of amoxicillin for an ear infection?")
        assert calls == [] and res["status"] == "not_found" and res["reason"] == reason and not res["web"]
    assert service.CLINICAL_MSG in (ask(web_runtime(helper=("CLINICAL",))[0], "how do I treat a sprain?")["answer_text"],)


def test_an_unsure_scope_check_does_not_search_the_web():
    runtime, calls = web_runtime(helper=("maybe?",))
    res = ask(runtime, "what is the circle of Willis?")
    assert calls == [] and res["status"] == "not_found"


def test_the_web_stays_off_when_switched_off(monkeypatch):
    monkeypatch.setenv("WEB_FALLBACK", "off")
    runtime, calls = web_runtime()
    res = ask(runtime, "What is the circle of Willis?")
    assert calls == [] and res["status"] == "not_found" and res["answer_text"] == service.NOT_FOUND_MSG


def test_no_access_is_never_answered_from_the_web():
    other = note("o", "Lecture 12 - Posterior Leg", "Walls", "The walls are the muscles of the leg.")
    calls = []
    runtime = rt([other], reply("x"), helper=("ANATOMY",), web=lambda q: calls.append(q))
    res = ask(runtime, "walls of the leg", allowed=[L5])
    assert res["status"] == "access_limited" and calls == []


def test_timeout_or_error_falls_back_to_the_ordinary_not_covered_message():
    for lookup in (lambda q: web_fallback.WebResult(error="timeout"), lambda q: web_fallback.WebResult(passages=[], seconds=6.0)):
        runtime = rt([ref("r", "heart")], reply("x"), ["ANATOMY"], web=lookup, found=False, cosine=0.3)
        res = ask(runtime, "What is the circle of Willis?")
        assert res["status"] == "not_found" and res["answer_text"] == service.NOT_FOUND_MSG and not res["web"]
        assert runtime.client.answering() == []


def test_a_web_answer_the_passages_do_not_support_becomes_not_covered():
    unsupported = reply("The circle of Willis has seven branches [Web: Some Other Page (NLM MeSH)].\n" + CLOSING, basis="web")
    runtime, calls = web_runtime(answer=unsupported)
    res = ask(runtime, "What is the circle of Willis?")
    assert res["status"] == "not_found" and res["answer_text"] == service.NOT_FOUND_MSG and not res["web"]
    declined = reply("The pages do not cover it.", covered=False, basis="not_covered", decline_reason="not_in_sources")
    runtime, calls = web_runtime(answer=declined)
    assert ask(runtime, "What is the circle of Willis?")["status"] == "not_found"


def test_the_student_sees_the_label_the_sources_and_nothing_that_leaks():
    runtime, calls = web_runtime(passages=(P1, P2))
    out = service.ask_for_student("What is the circle of Willis?", "", True, None, runtime=runtime, ctx=EMPTY, log=False)
    view = out["view"]
    assert view["web"] and view["web_label"] == "From the web, not in Dr. Inglis's notes or OpenStax. Check with your instructor."
    src = view["sources"][0]
    assert (src["title"], src["site"], src["source_url"], src["retrieved"]) == ("MeSH: Circle of Willis", "NLM MeSH", P1["url"], "2026-10-19")
    assert view["citations"][0]["short"] == "Web · NLM MeSH" and view["trust"]["web"] is True
    assert any("Web pages used" in t for t, _ in sv.built_lines(view["built"])[0])
    assert sv.leaks(view) == [], sv.leaks(view)
    assert out["instructor"] is None


def test_a_web_answer_is_logged_with_its_pages(tmp_path):
    runtime, _ = web_runtime()
    service.ask("What is the circle of Willis?", "", True, None, runtime=runtime, ctx=EMPTY, user="student1")
    entry = usage.read_log()[-1]
    assert entry["web"] is True and entry["web_urls"] == [P1["url"]] and entry["answered_from_notes"] is False
    s = usage.summary()
    assert len(s["chat"]["web"]) == 1 and len(s["chat"]["unanswered"]) == 1


def test_the_flag_button_works_on_a_web_answer(tmp_path):
    runtime, _ = web_runtime()
    view = service.ask_for_student("What is the circle of Willis?", "", True, None, runtime=runtime, ctx=EMPTY, log=False)["view"]
    urls = [s["source_url"] for s in view["sources"]]
    assert student_report.report_error("student1", "q", view["answer_text"], [c["cite"] for c in view["citations"]],
                                       student_report.REASONS[0], "wrong page", web_urls=urls)
    flag = json.loads(qa.FLAGS_PATH.read_text().splitlines()[-1])
    assert flag["type"] == "student_report" and flag["web"] is True and flag["web_urls"] == [P1["url"]]


def test_a_citation_to_a_web_page_that_was_not_fetched_is_dropped_not_shown():
    wrong = reply(f"Arteries form a ring [Web: Never Fetched (MedlinePlus)].\nIt sits at the base of the brain {WEB_CITE}.\n{CLOSING}", basis="web")
    runtime, _ = web_runtime(answer=wrong)
    res = ask(runtime, "What is the circle of Willis?")
    assert res["n_unmatched"] == 0 and "Never Fetched" not in res["answer_text"] and res["status"] == "answered"


# ---------------------------------------------------------------------------------------------------------------
# the allowlist and the fetcher
# ---------------------------------------------------------------------------------------------------------------

def test_the_allowlist_is_enforced_for_every_url():
    for ok in ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", "https://wsearch.nlm.nih.gov/ws/query",
               "https://medlineplus.gov/carpaltunnelsyndrome.html", "https://www.ncbi.nlm.nih.gov/mesh/68005269"):
        assert web_sources.url_allowed(ok), ok
    for bad in ("https://example.com/x", "http://medlineplus.gov/x", "https://evil.medlineplus.gov.example.com/x",
                "https://en.wikipedia.org.evil.com/wiki/Femur", "https://fr.wikipedia.org/wiki/Femur", "https://www.ncbi.nlm.nih.gov/pubmed/123", "https://api.tavily.com/search",
                "https://medlineplus.gov.evil.com/"):
        assert not web_sources.url_allowed(bad), bad
        with pytest.raises(web_sources.NotAllowed):
            web_sources.check(bad)


def test_wikipedia_is_on_by_default_en_only_and_can_be_switched_off(monkeypatch):
    assert web_sources.url_allowed("https://en.wikipedia.org/w/api.php") and web_sources.url_allowed("https://en.wikipedia.org/wiki/Femur")
    assert not web_sources.url_allowed("https://de.wikipedia.org/w/api.php") and not web_sources.url_allowed("https://commons.wikimedia.org/x")
    assert [s["short"] for s in web_sources.enabled_sites()] == ["NLM MeSH", "MedlinePlus", "Wikipedia"]
    monkeypatch.setenv("WEB_ALLOW_WIKIPEDIA", "off")
    assert not web_sources.url_allowed("https://en.wikipedia.org/w/api.php")


def test_tavily_stays_off_without_a_key(monkeypatch):
    assert not web_sources.url_allowed("https://api.tavily.com/search")
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    assert web_sources.url_allowed("https://api.tavily.com/search") and "en.wikipedia.org" in web_sources.tavily_domains()


class FakeResp:
    def __init__(self, data=None, text=""):
        self._d, self.text = data, text

    def json(self):
        return self._d


WIKI_FULL = ("The circle of Willis is a circulatory anastomosis that supplies blood to the brain and surrounding structures.\n\n"
             "== Structure ==\nIt is formed by the internal carotid arteries, the anterior and posterior cerebral arteries and the "
             "anterior and posterior communicating arteries, which join at the base of the brain.\n\n== References ==\nSmith 2001.")
WIKI_SEARCH = [
    {"index": 1, "title": "Willis (disambiguation)", "pageprops": {"disambiguation": ""}, "extract": "Willis may refer to a name of an artery."},
    {"index": 2, "title": "Willis Carto", "extract": "Willis Carto was an American political activist and publisher.", "categories": [{"title": "Category:Activists"}]},
    {"index": 3, "title": "Circle of Willis", "extract": "The circle of Willis is a circulatory anastomosis that supplies blood to the brain.",
     "categories": [{"title": "Category:Arteries of the head and neck"}, {"title": "Category:Human anatomy"}]}]


class FakeHttp:
    """Records every URL asked for; answers MeSH and MedlinePlus the way the real services do."""

    def __init__(self, delay=0.0, fail=False, wiki=True):
        self.urls, self.delay, self.fail, self.wiki, self.requests = [], delay, fail, wiki, []

    def get(self, url, params=None, timeout=4.0):
        web_sources.check(url)
        self.urls.append(url)
        self.requests.append((url, dict(params or {})))
        time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("HTTP 500")
        if "wikipedia" in url:
            if not self.wiki:
                return FakeResp({"query": {"pages": []}})
            if "titles" in (params or {}):               # the full page text
                return FakeResp({"query": {"pages": [{"title": params["titles"], "extract": WIKI_FULL}]}})
            return FakeResp({"query": {"pages": WIKI_SEARCH}})
        if "esearch" in url:
            return FakeResp({"esearchresult": {"idlist": ["68002941"]}})
        if "esummary" in url:
            return FakeResp({"result": {"uids": ["68002941"], "68002941": {
                "ds_scopenote": "A polygonal anastomosis at the base of the brain formed by the internal carotid arteries.",
                "ds_meshterms": ["Circle of Willis", "Willis Circle"]}}})
        xml = ('<nlmSearchResult><list><document rank="0" url="https://medlineplus.gov/brainaneurysm.html">'
               '<content name="title">Brain &lt;span&gt;Aneurysm&lt;/span&gt;</content>'
               '<content name="FullSummary">An aneurysm in the circle of Willis is a bulge in an artery wall.</content>'
               '</document></list></nlmSearchResult>')
        return FakeResp(text=xml)


def test_lookup_asks_wikipedia_first_then_mesh_and_medlineplus_only_from_allowed_hosts(tmp_path):
    http = FakeHttp()
    res = web_fallback.lookup("What is the circle of Willis?", http=http, cache_dir=tmp_path)
    assert [p["site"] for p in res.passages] == ["Wikipedia", "NLM MeSH", "MedlinePlus"] and res.error == ""
    assert all(web_sources.url_allowed(u) for u in http.urls) and all(len(p["text"]) <= 1500 for p in res.passages)
    assert res.passages[1]["url"] == "https://www.ncbi.nlm.nih.gov/mesh/68002941" and res.passages[0]["retrieved"]


def test_lookup_returns_at_most_three_passages_of_about_1500_characters(tmp_path):
    long = "word " * 1000
    assert len(web_fallback.trim(long)) <= 1500 + 4
    http = FakeHttp()
    assert len(web_fallback.lookup("circle willis", http=http, cache_dir=tmp_path).passages) <= 3


def test_lookup_is_cached_for_seven_days(tmp_path):
    from datetime import datetime, timedelta, timezone
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    first = FakeHttp()
    web_fallback.lookup("circle of Willis", http=first, now=t0, cache_dir=tmp_path)
    again = FakeHttp()
    res = web_fallback.lookup("circle of Willis", http=again, now=t0 + timedelta(days=6), cache_dir=tmp_path)
    assert res.cached and again.urls == [] and res.passages
    later = FakeHttp()
    res = web_fallback.lookup("circle of Willis", http=later, now=t0 + timedelta(days=8), cache_dir=tmp_path)
    assert not res.cached and later.urls


def test_lookup_gives_up_after_the_total_timeout_and_never_raises(tmp_path):
    t0 = time.monotonic()
    res = web_fallback.lookup("circle of Willis", http=FakeHttp(delay=2.0), cache_dir=tmp_path, timeout=0.5)
    assert time.monotonic() - t0 < 1.5 and res.passages == [] and "timeout" in res.error


def test_lookup_swallows_server_errors_and_does_not_cache_them(tmp_path):
    res = web_fallback.lookup("circle of Willis", http=FakeHttp(fail=True), cache_dir=tmp_path)
    assert res.passages == [] and res.error and list(tmp_path.iterdir()) == []


def test_a_passage_that_does_not_mention_the_question_is_dropped(tmp_path):
    res = web_fallback.lookup("pterygopalatine ganglion", http=FakeHttp(), cache_dir=tmp_path)
    assert res.passages == []


def test_default_http_refuses_a_url_outside_the_list():
    with pytest.raises(web_sources.NotAllowed):
        web_fallback.Http().get("https://example.com/")


def test_scope_check_reads_the_one_word_reply():
    class C:
        def __init__(self, text):
            self.text = text
            self.messages = SimpleNamespace(create=self.create)

        def create(self, **kw):
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=self.text)],
                                   usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    assert qry.scope_check(C("ANATOMY"), "q")[0:3:2] == ("anatomy", True)
    assert qry.scope_check(C("CLINICAL."), "q")[0] == "clinical_advice"
    assert qry.scope_check(C("OTHER"), "q")[0] == "not_anatomy"
    assert qry.scope_check(C("¯\\_(ツ)_/¯"), "q")[2] is False


# ---- Wikipedia ---------------------------------------------------------------------------------------------------

def test_a_disambiguation_page_and_a_non_anatomy_page_are_rejected(tmp_path):
    res = web_fallback.lookup("circle willis", http=FakeHttp(), cache_dir=tmp_path)
    wiki = [p for p in res.passages if p["site"] == "Wikipedia"]
    assert [p["title"] for p in wiki] == ["Circle of Willis"]           # not "Willis (disambiguation)", not "Willis Carto"
    assert wiki[0]["url"] == "https://en.wikipedia.org/wiki/Circle_of_Willis" and wiki[0]["license"] == "Wikipedia, CC BY-SA 4.0"


def test_the_page_text_is_the_intro_plus_the_best_section_within_1500_characters(tmp_path):
    p = web_fallback.lookup("circle willis", http=FakeHttp(), cache_dir=tmp_path).passages[0]
    assert p["text"].startswith("The circle of Willis is a circulatory anastomosis") and "Structure:" in p["text"]
    assert "internal carotid arteries" in p["text"] and "Smith 2001" not in p["text"] and len(p["text"]) <= 1504
    long = "Intro sentence about the nerve. " * 40 + "\n\n== Course ==\n" + "The nerve runs along the bone. " * 80
    assert len(web_fallback.best_section(long, ["nerve", "course"])) <= 1504


def test_the_request_to_wikipedia_carries_no_personal_data(tmp_path):
    http = FakeHttp()
    web_fallback.lookup("circle of Willis", http=http, cache_dir=tmp_path)
    assert web_fallback.USER_AGENT == "AnatoVision/1.0 (UB CDA 650 course project)"
    wiki = [(u, p) for u, p in http.requests if "wikipedia" in u]
    assert wiki and all(u.startswith("https://en.wikipedia.org/") for u, _ in wiki)
    blob = json.dumps(wiki).lower()
    assert "@" not in blob and "student" not in blob and "gmail" not in blob
    import requests
    assert web_fallback.Http().s.headers["User-Agent"] == web_fallback.USER_AGENT
    assert "anirudh" not in web_fallback.USER_AGENT.lower() and "@" not in web_fallback.USER_AGENT


def test_wikipedia_times_out_into_the_other_sources_or_nothing(tmp_path):
    res = web_fallback.lookup("circle willis", http=FakeHttp(delay=2.0), cache_dir=tmp_path, timeout=0.4)
    assert res.passages == [] and "timeout" in res.error


def test_wikipedia_off_means_no_wikipedia_request(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_ALLOW_WIKIPEDIA", "off")
    http = FakeHttp()
    res = web_fallback.lookup("circle willis", http=http, cache_dir=tmp_path)
    assert not any("wikipedia" in u for u in http.urls) and "Wikipedia" not in {p["site"] for p in res.passages}


WIKI_P = {"id": "web-w", "title": "Circle of Willis", "site": "Wikipedia", "site_id": "wikipedia", "license": "Wikipedia, CC BY-SA 4.0",
          "url": "https://en.wikipedia.org/wiki/Circle_of_Willis", "retrieved": "2026-10-20",
          "text": "The circle of Willis is a circulatory anastomosis that supplies blood to the brain."}
WIKI_REPLY = reply(f"The circle of Willis is a ring of arteries that supplies blood to the brain [Web: Circle of Willis (Wikipedia)].\n{CLOSING}", basis="web")


def test_a_wikipedia_answer_has_the_wikipedia_label_and_attribution_and_no_leaks():
    runtime, _ = web_runtime(answer=WIKI_REPLY, passages=(WIKI_P,))
    out = service.ask_for_student("What is the circle of Willis?", "", True, None, runtime=runtime, ctx=EMPTY, log=False)
    view = out["view"]
    assert view["web"] and view["web_label"] == "From Wikipedia, not in Dr. Inglis's notes or OpenStax. Check with your instructor."
    src = view["sources"][0]
    assert (src["title"], src["source_url"], src["retrieved"], src["license"]) == ("Circle of Willis", WIKI_P["url"], "2026-10-20", "Wikipedia, CC BY-SA 4.0")
    assert sv.leaks(view) == []
    from app.views import pane
    html = pane.web_credit_html(src)
    assert "Wikipedia, CC BY-SA 4.0" in html and "retrieved 2026-10-20" in html and WIKI_P["url"] in html


def test_a_mesh_only_web_answer_keeps_the_general_web_label():
    runtime, _ = web_runtime()
    view = service.ask_for_student("What is the circle of Willis?", "", True, None, runtime=runtime, ctx=EMPTY, log=False)["view"]
    assert view["web_label"].startswith("From the web,")
