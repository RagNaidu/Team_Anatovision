"""Shared fakes for the Quiz tests: a tiny corpus, a fake searcher, and fake model calls that behave according to a Behavior."""
import json
import re
import threading
import time
from types import SimpleNamespace

from src import llm
from src.retrieval.search import Hit, SearchResult

HAND = "Lecture 09 - The Hand"
OTHER = "Lecture 12 - Posterior Leg"
SECRET = "SECRETFACT the tibial nerve supplies the plantar surface of the foot completely"
FACTS = [("Median Nerve", "The median nerve supplies the muscles of the thenar eminence and the first two lumbricals in the hand and it passes through the carpal tunnel."),
         ("Ulnar Nerve", "The ulnar nerve supplies the hypothenar muscles and the adductor pollicis in the hand and it passes superficial to the flexor retinaculum."),
         ("Radial Nerve", "The radial nerve supplies the extensor muscles of the forearm and it gives the posterior interosseous branch below the elbow joint."),
         ("Axillary Nerve", "The axillary nerve supplies the deltoid and the teres minor muscles and it winds around the surgical neck of the humerus bone."),
         ("Musculocutaneous Nerve", "The musculocutaneous nerve supplies the biceps brachii and the brachialis and it pierces the coracobrachialis muscle in the arm."),
         ("Thoracodorsal Nerve", "The thoracodorsal nerve supplies the latissimus dorsi muscle and it runs along the posterior axillary wall with the subscapular vessels."),
         ("Long Thoracic Nerve", "The long thoracic nerve supplies the serratus anterior muscle and it descends on the superficial surface of that muscle at the chest wall."),
         ("Dorsal Scapular Nerve", "The dorsal scapular nerve supplies the rhomboid muscles and the levator scapulae and it passes deep to the levator muscle near the medial border."),
         ("Lateral Pectoral Nerve", "The lateral pectoral nerve supplies the pectoralis major muscle and it arises from the lateral cord of the brachial plexus in the axilla."),
         ("Medial Pectoral Nerve", "The medial pectoral nerve supplies the pectoralis minor muscle and it arises from the medial cord and pierces that small muscle on its way."),
         ("Upper Subscapular Nerve", "The upper subscapular nerve supplies the subscapularis muscle and it arises from the posterior cord of the brachial plexus in the axilla."),
         ("Suprascapular Nerve", "The suprascapular nerve supplies the supraspinatus and infraspinatus muscles and it passes through the suprascapular notch of the scapula.")]
FILL = (" This passage is part of the practical course material for the dissection laboratory, and the same material is covered in the lecture and in the "
        "practical session, so a student should be able to describe it and to point to it on the specimen during the laboratory. Students are expected "
        "to revise it before the practical examination and to relate it to the surface anatomy of the limb.")


def chunk(i, lecture, title, text, kind="notes", guide=""):
    c = {"id": f"c{i}", "source_type": kind, "priority": 2 if kind != "open_text" else 3, "lecture": lecture, "breadcrumb": f"{lecture} > {title}",
         "section_path": [title], "text": text + FILL, "section_number": "", "source_url": "", "uploaded": ""}
    if kind == "dissection_guide":
        c.update({"guide": guide, "class_number": 14, "slides": [i], "slide": i})
    if kind == "open_text":
        c.update({"lecture": "Chapter 11", "breadcrumb": f"OpenStax A&P 2e > Chapter 11 > {title}", "section_number": f"11.{i}", "source_url": "https://openstax.org/x"})
    return c


def corpus():
    ch = [chunk(i, HAND, t, x) for i, (t, x) in enumerate(FACTS)]
    ch.append(chunk(50, OTHER, "Tibial Nerve", SECRET))
    ch.append(chunk(60, "Chapter 11", "Muscle Tissue", "Skeletal muscle fibres contain sarcomeres made of actin and myosin filaments arranged in repeating bands that shorten during contraction.", "open_text"))
    return ch


class FakeSearcher:
    def __init__(self, chunks, found=True):
        self.chunks, self.found, self.calls = chunks, found, []
        self.note_lectures = {c["lecture"] for c in chunks if c["source_type"] == "notes"}

    def search(self, query, k=5, allowed_lectures=None, rerank=True):
        self.calls.append(allowed_lectures)
        ok = [c for c in self.chunks if c["source_type"] == "open_text" or allowed_lectures is None or c["lecture"] in allowed_lectures]
        hits = [Hit(c, 0.03, 0.03, 0.8, 1.0, 1, 1) for c in ok if c["source_type"] != "web"][:k]
        return SearchResult(query, self.found and bool(hits), hits, 0.8 if hits else 0.0, "")


class Behavior:
    def __init__(self, **kw):
        self.gen = "ok"             # ok | bad_span | no_support | negative | error
        self.gemma = "agree"        # agree | wrong | two
        self.verifier = "agree"     # agree | wrong | two | error
        self.audit = "ok"           # ok | unsupported | error
        self.audited = set()
        self.bad = []               # nerve names whose items the generator-side solver gets wrong
        self.prompts, self.models, self.n_calls = [], [], 0
        self.delay, self.cur, self.max_cur, self.lock = 0.0, 0, 0, threading.Lock()
        self.__dict__.update(kw)


def passage_of_prompt(user):
    m = re.search(r'<passage id="([^"]+)" source="[^"]*" role="primary">\n(.*?)\n</passage>', user, re.S)
    return m.group(1), m.group(2)


def make_draft(pid, text, mode):
    first = re.split(r"(?<=\.)\s", text)[0]
    key = "the " + re.search(r"The ((?:[a-z]+ )+?nerve)", text, re.I).group(1).lower()
    others = [o for o in ("the ulnar nerve", "the radial nerve", "the femoral nerve", "the sciatic nerve", "the tibial nerve") if o != key][:3]
    span = " ".join(first.split()[:9]) if mode != "bad_span" else "this sentence is not in the passage at all"
    sup = [{"source_id": pid, "span": span}]
    d = {"objective": "nerve supply", "stem": "", "lead_in": ("Which nerve supplies " + " ".join(re.split(r"supplies ", first)[-1].split()[:7]) + "?") if mode != "negative" else "Which nerve is NOT described in the passage?",
         "options": [key, *others], "key_index": 0, "explanation": f"The passage states: {first}", "key_support": sup,
         "explanation_support": [] if mode == "no_support" else sup,
         "alternatives": [{"index": i + 1, "why_wrong": f"The passage names a different structure ({key}).", "support": sup} for i in range(3)]}
    return d


def install(monkeypatch, beh, where=("src.quiz.generate.llm.complete_json",)):
    def fake(client, system, messages, max_tokens, schema, model=None):
        with beh.lock:
            beh.cur += 1
            beh.max_cur = max(beh.max_cur, beh.cur)
        try:
            if beh.delay:
                time.sleep(beh.delay)
            return fake_inner(client, system, messages, max_tokens, schema, model)
        finally:
            with beh.lock:
                beh.cur -= 1

    def fake_inner(client, system, messages, max_tokens, schema, model=None):
        with beh.lock:
            beh.n_calls += 1
        user = messages[0]["content"]
        beh.prompts.append(user)
        beh.models.append(model)
        if system.startswith("You write ONE"):
            if beh.gen == "error":
                raise llm.LLMError("down")
            pid, text = passage_of_prompt(user)
            mode = beh.gen
            if mode == "bad_span_once":
                mode = "ok" if "<problems>" in user else "bad_span"
            return make_draft(pid, text, mode), {"input_tokens": 1, "output_tokens": 1}
        if system.startswith("You answer a multiple-choice"):
            mode = beh.gemma if model and "gemma" in model else beh.verifier
            prim = re.search(r'role="primary">\n(.*?)\n</passage>', user, re.S).group(1).lower()
            if mode == "agree" and any(b in prim for b in beh.bad):
                mode = "wrong"
            if mode == "error":
                raise llm.LLMError("down")
            opts = dict(re.findall(r"^([A-E])\. (.+)$", user, re.M))
            m = re.search(r"The ((?:[a-z]+ )+?nerve)", user[user.index("<evidence>"):], re.I)
            key = next((i for i, t in opts.items() if m and t == "the " + m.group(1).lower()), None)
            ans = key if mode in ("agree", "two") else next(i for i in opts if i != key)
            also = [next(i for i in opts if i != key)] if mode == "two" else []
            return {"answer_id": ans, "also_defensible": also, "evidence_ids": [], "reason": "from the passage"}, {"input_tokens": 1, "output_tokens": 1}
        if system.startswith("You audit"):
            if beh.audit == "error":
                raise llm.LLMError("down")
            ids = re.findall(r"^ALTERNATIVE ([A-E]):", user, re.M)
            ok = beh.audit == "ok"
            lead = re.search(r"<question>\n(.*?)\n[A-E]\. ", user, re.S).group(1)
            with beh.lock:
                first = lead not in beh.audited
                beh.audited.add(lead)
            comparable = beh.audit != "mixed" and not (beh.audit == "mixed_once" and first)
            return {"key_supported": ok or beh.audit in ("mixed", "mixed_once"), "explanation_supported": ok or beh.audit in ("mixed", "mixed_once"),
                    "alternatives": [{"id": i, "supported": ok or beh.audit in ("mixed", "mixed_once"), "note": ""} for i in ids],
                    "options_comparable": comparable, "odd_options": [] if comparable else ["B"],
                    "unsupported_claims": [] if ok else ["the explanation adds a fact"]}, {"input_tokens": 1, "output_tokens": 1}
        raise AssertionError("unexpected prompt")
    monkeypatch.setattr("src.quiz.generate.llm.complete_json", fake)
    return beh


def runtime(chunks=None, found=True):
    from src import service
    s = FakeSearcher(chunks if chunks is not None else corpus(), found)
    return service.Runtime(searcher=s, next_of={}, client=object(), model="google/gemma-4-31B-it", rewrite_model="google/gemma-4-31B-it")


EMPTY_CTX = {"confirmed": [], "doubtful": [], "fixes": []}
