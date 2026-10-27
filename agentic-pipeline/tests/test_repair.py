"""Citation repair, the verbatim fix and the thinking setting. No real API call."""
from types import SimpleNamespace

from src import citations as cit
from src import llm
from src.modes import qa

L = "Lecture 08 - Anterior and Medial Thigh"
CHUNKS = [
    {"cite": f"{L} > Anterior and Medial Thigh > The Femoral Triangle", "breadcrumb": f"{L} > The Femoral Triangle",
     "source_type": "notes"},
    {"cite": f"{L} > The Femoral Triangle > Contents", "breadcrumb": f"{L} > The Femoral Triangle > Contents",
     "source_type": "notes"},
    {"cite": "OpenStax A&P 2e §11.6", "breadcrumb": "OpenStax > 11 > 11.6", "source_type": "open_text"},
]


def test_matching_citations_are_untouched():
    a = f"Borders are X. [{L} > The Femoral Triangle]\nAsk for more detail if you need it."
    out, rep = cit.repair_citations(a, CHUNKS)
    assert out == a and rep == {"repaired": [], "dropped": [], "removed": []}


def test_a_citation_that_clearly_means_one_passage_is_repaired():
    a = f"The floor is pectineus. [{L} > Wrong Middle > The Femoral Triangle]"
    out, rep = cit.repair_citations(a, CHUNKS)
    assert out == f"The floor is pectineus. [{L} > Anterior and Medial Thigh > The Femoral Triangle]"
    assert rep["repaired"] and not rep["dropped"] and not rep["removed"]


def test_a_citation_that_matches_nothing_is_dropped_and_so_is_its_claim():
    a = f"Real claim. [{L} > The Femoral Triangle]\nInvented claim. [Lecture 5 - Nope > Nothing]\nAsk for more detail if you need it."
    out, rep = cit.repair_citations(a, CHUNKS)
    assert "Invented" not in out and "Nope" not in out and "Real claim" in out and out.endswith("Ask for more detail if you need it.")
    assert rep["dropped"] == ["Lecture 5 - Nope > Nothing"] and len(rep["removed"]) == 1


def test_a_dropped_citation_next_to_a_good_one_keeps_the_claim():
    a = f"Both. [{L} > The Femoral Triangle] [Lecture 5 - Nope > Nothing]"
    out, rep = cit.repair_citations(a, CHUNKS)
    assert out == f"Both. [{L} > The Femoral Triangle]" and not rep["removed"]


def test_an_ambiguous_citation_is_dropped_not_guessed():
    chunks = CHUNKS + [{"cite": f"{L} > Other > The Femoral Triangle", "breadcrumb": f"{L} > Other > The Femoral Triangle",
                        "source_type": "notes"}]
    out, rep = cit.repair_citations(f"Claim. [{L} > Mystery > The Femoral Triangle]", chunks)
    assert rep["dropped"] and out == ""


def test_sentences_without_any_citation_are_left_alone():
    out, rep = cit.repair_citations(f"Plain line with no source.\n[{L} > The Femoral Triangle] only.", CHUNKS)
    assert "Plain line with no source." in out and not rep["removed"]


# ---- verbatim ----------------------------------------------------------------------------------------------------

OPEN = ("The femoral nerve passes beneath the inguinal ligament and divides into many branches in the thigh. "
        "The femoral artery lies medial to the nerve and gives off the deep femoral artery in the upper thigh region.")


def hits():
    return [SimpleNamespace(chunk={"source_type": "open_text", "text": OPEN})]


def fake_para(text):
    calls = []

    def create(**kw):
        calls.append(kw)
        msg = SimpleNamespace(content=text)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")], model="m",
                               usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), calls


def test_over_long_copying_is_paraphrased_and_the_citation_kept():
    two = ("The femoral nerve passes beneath the inguinal ligament and divides into many branches in the thigh. [OpenStax A&P 2e §11.6]\n"
           "The femoral artery lies medial to the nerve and gives off the deep femoral artery in the upper thigh region. [OpenStax A&P 2e §11.6]")
    assert not qa.copyright_ok(two, hits())[0]
    client, calls = fake_para("The artery sits on the inner side of the nerve and sends a deep branch off high in the thigh.")
    out, usage, notes = qa.fix_verbatim(client, "m", two, hits())
    assert qa.copyright_ok(out, hits())[0] and "[OpenStax A&P 2e §11.6]" in out.splitlines()[1]
    assert len(calls) == 1 and "paraphrased" in notes[0] and usage["input_tokens"] == 5


def test_a_paraphrase_that_still_copies_is_removed_instead():
    two = ("The femoral nerve passes beneath the inguinal ligament and divides into many branches in the thigh. [OpenStax A&P 2e §11.6]\n"
           "The femoral artery lies medial to the nerve and gives off the deep femoral artery in the upper thigh region. [OpenStax A&P 2e §11.6]")
    client, _ = fake_para("The femoral artery lies medial to the nerve and gives off the deep femoral artery in the upper thigh region.")
    out, _, notes = qa.fix_verbatim(client, "m", two, hits())
    assert qa.copyright_ok(out, hits())[0] and len(out.splitlines()) == 1 and "removed" in notes[0]


# ---- thinking setting ---------------------------------------------------------------------------------------------

def test_thinking_is_left_to_the_gateway_by_default_and_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **k: None)
    client, calls = fake_para("ok")
    monkeypatch.delenv("BULLSAI_THINKING", raising=False)
    llm.complete(client, "S", [{"role": "user", "content": "q"}], 10, "m")
    assert "extra_body" not in calls[0]                                   # the safe default leaves the gateway alone
    monkeypatch.setenv("BULLSAI_THINKING", "off")
    llm.complete(client, "S", [{"role": "user", "content": "q"}], 10, "m")
    assert calls[1]["extra_body"] == {"thinking": {"type": "disabled"}}
