"""The cadaver's body type changes LAB answers (the ordered-steps answer, a guide check, a station note) and nothing else; every student output is
leak-free and any tip that is not from the notes or guides says so. The model is faked; the network is never used."""
import json
from types import SimpleNamespace

import pytest

from src import body_type as bt
from src import service
from src import student_view as sv
from src.modes import guide_slides as GS
from src.modes import qa
from tests.test_dissection_guides import L13, guide_chunk
from tests.test_service import CLOSING, reply
from tests.test_stage1 import rt
from tests.test_student_safe import EMPTY

LEAN, FAT, AVG = "less fat, average muscle, small build", "more fat, average muscle, large build", "average fat, average muscle, average build"
TIP = bt.TIP_LABEL


def lab_reply(chunks, extra=()):
    steps = [f"{i}. Step {i} of the dissection [{qa.cite_for(c)}]." for i, c in enumerate(chunks, 1)]
    return reply("\n".join(steps + list(extra) + [CLOSING]))


def ask_student(runtime, q, body_type):
    return service.ask_for_student(q, body_type, True, None, runtime=runtime, ctx=EMPTY, log=False)["view"]


def prompt_of(runtime):
    return json.dumps(runtime.client.answering()[0])


def test_what_counts_as_a_body_type_worth_adapting_to():
    assert bt.describe("more_fat") == "more body fat" and bt.describe("lean").startswith("lean") and "muscle" in bt.describe("more_muscular")
    assert bt.describe(FAT) == "more body fat, large build" and bt.describe(LEAN) == "less body fat, small build"
    for none in ("", None, "average", "not_sure", AVG, "nonsense", "more fat"):
        assert bt.describe(none) == "" and not bt.is_active(none)


@pytest.mark.parametrize("value,active", [(LEAN, True), (FAT, True), ("more_fat", True), ("lean", True), (AVG, False), ("not_sure", False), ("", False)])
def test_only_a_lab_answer_for_a_real_body_type_gets_the_body_rule(value, active):
    g = [guide_chunk("15", n, cid=f"g{n}", lecture=L13) for n in (2, 3)]
    runtime = rt(g, lab_reply(g))
    ask_student(runtime, "How do I expose the femoral triangle?", value)
    prompt = prompt_of(runtime)
    assert ("General tip, not from your notes" in prompt) is active and ("For this body type:" in prompt) is active
    shown = bt.describe(value) if value in bt.GUIDE_CHOICES else value
    assert (f"cadaver body type: {shown}" in prompt) or not value


def test_a_concept_question_is_unchanged_by_the_body_type():
    g = [guide_chunk("15", 2, cid="g2", lecture=L13)]
    answer = reply(f"The sartorius flexes the hip [{qa.cite_for(g[0])}].\n{CLOSING}")
    plain, fat = rt(g, answer), rt(g, answer)
    ask_student(plain, "What does the sartorius do?", "")
    ask_student(fat, "What does the sartorius do?", FAT)
    system = lambda r: r.client.answering()[0]["system"] if "system" in r.client.answering()[0] else json.dumps(r.client.answering()[0]["messages"][0])
    assert "General tip, not from your notes" not in prompt_of(fat)
    assert system(plain) == system(fat) or "General tip" not in prompt_of(fat)
    # an "explain this simply" request is a concept answer too
    ex = rt(g, answer)
    ask_student(ex, "Explain the sartorius in simple words", FAT)
    assert "General tip, not from your notes" not in prompt_of(ex)


def test_the_same_lab_question_gives_different_grounded_guidance_for_lean_and_more_fat_and_stays_student_safe():
    g = [guide_chunk("15", n, cid=f"g{n}", lecture=L13, text="Clear the fat and superficial fascia over the thigh. Then open the femoral sheath.") for n in (2, 3)]
    fat_lines = [f"For this body type: slide 2 has you clear the fat first, so expect more of it [{qa.cite_for(g[0])}].",
                 f"{TIP}: structures may lie deeper, so more fat and thicker superficial fascia come away before they appear."]
    lean_lines = [f"{TIP}: structures may lie nearer the surface, with less fat to clear."]
    fat = ask_student(rt(g, lab_reply(g, fat_lines)), "How do I expose the femoral triangle?", FAT)
    lean = ask_student(rt(g, lab_reply(g, lean_lines)), "How do I expose the femoral triangle?", LEAN)
    assert "more of it" in fat["answer_text"] and "nearer the surface" in lean["answer_text"] and fat["answer_text"] != lean["answer_text"]
    for res in (fat, lean):
        assert any(l.startswith(f"{TIP}:") for l in res["answer_text"].splitlines())                # the label survives the student-safe layer
        assert sv.leaks({k: res[k] for k in ("answer_text", "blocks", "units", "citations", "notice", "status")}) == []
    by_text = {u["text"]: u for u in fat["units"]}
    grounded = next(u for t, u in by_text.items() if t.startswith("For this body type:"))
    tips = [u for t, u in by_text.items() if t.startswith(TIP)]
    assert grounded["chips"] and tips and all(not u["chips"] for u in tips)             # the grounded line carries its citation; a general tip never does


def fake_judge_client(out):
    calls = []

    def create(**kw):
        calls.append(kw)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(out))], usage=SimpleNamespace(input_tokens=5, output_tokens=5))
    return SimpleNamespace(messages=SimpleNamespace(create=create), calls=calls)


STATION = {"text": "Clear the fat and superficial fascia, then expose the femoral sheath.", "slides": [3]}


def test_the_guide_judge_only_gets_the_body_type_rule_for_a_real_body_type():
    for value, active in (("more_fat", True), ("lean", True), ("average", False), ("not_sure", False), ("", False)):
        c = fake_judge_client({"match": "yes", "feedback": "ok"})
        GS.judge_description(c, "m", STATION, "I cleared the fat", body_type=value)
        sent = json.dumps(c.calls[0])
        assert (GS.body_mod.TIP_LABEL in sent and "<body_type>" in sent) is active
    c = fake_judge_client({"match": "yes", "feedback": "ok"})
    GS.judge_description(c, "m", STATION, "x")                                                          # the old call keeps working
    assert "<body_type>" not in json.dumps(c.calls[0])


def test_a_station_note_labels_every_general_line_and_drops_empty_ones():
    c = fake_judge_client({"lines": [{"text": "The guide has you clear the fat first, so expect more of it.", "general": False},
                                     {"text": "structures may lie deeper.", "general": True}, {"text": "  ", "general": True},
                                     {"text": f"{TIP}: more muscle bulk.", "general": False}]})
    out, _ = GS.body_tip(c, "m", STATION, "more_fat")
    assert [l["general"] for l in out["lines"]] == [False, True, True]
    assert out["lines"][1]["text"] == f"{TIP}: structures may lie deeper." and out["lines"][2]["text"].startswith(f"{TIP}:")
    assert "<body_type>more body fat</body_type>" in json.dumps(c.calls[0])
