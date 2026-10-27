"""Guide mode: stations, cards, and the session rules. No API calls: the model is faked."""
from types import SimpleNamespace

import pytest

from src.modes import guide
from src.modes.guide import NO_CONSEQUENCE, Session, Station

N = 5


def card(i, **over):
    base = {"station": f"S{i}", "identify_these": [f"thing{i}a", f"thing{i}b"],
            "what_you_should_see": [f"see{i}a", f"see{i}b"], "landmarks_relations": [], "clinical_if_stated": [],
            "wrong_if_stated": [], "variation_if_stated": [], "doubtful_used": []}
    base.update(over)
    return base


def meta(**over):
    return {"review": [], "doubtful": [], "verified": [], **over}


def make(verdicts=None, cards=None, metas=None, flag_logger=None):
    """Session over N stations; verdicts = list of judge answers returned in order."""
    stations = [Station(n=i, name=f"Station name {i}", sections=[]) for i in range(1, N + 1)]
    calls = []
    answers = list(verdicts or [])

    def judge(c, text):
        calls.append(text)
        if not answers:
            raise AssertionError("judge called unexpectedly")
        return answers.pop(0)

    s = Session(lecture="Lecture 99", stations=stations, cards=cards or {i: card(i) for i in range(1, N + 1)},
                metas=metas or {i: meta() for i in range(1, N + 1)}, judge=judge, flag_logger=flag_logger)
    s.judge_calls = calls
    return s


def started(**kw):
    s = make(**kw)
    s.start()
    s.handle("more fat")          # body type
    return s


def yes(feedback="Good."):
    return {"match": "yes", "feedback": feedback, "related_consequences": []}


def partial(feedback="Missing thing.", related=()):
    return {"match": "partial", "feedback": feedback, "related_consequences": list(related)}


def text(lines):
    return "\n".join(lines)


# ---- start ------------------------------------------------------------------------------------------------

def test_banner_text():
    assert guide.BANNER == "SAMPLE MODE: built from the lecture's own order, not a dissection procedure."


def test_asks_body_type_then_lists_stations():
    s = make()
    assert "body type" in text(s.start())
    out = text(s.handle("more fat, less muscle"))
    assert "Which station are you at?" in out and "Station name 1" in out and "Station name 5" in out


# ---- never skip ahead -------------------------------------------------------------------------------------

def test_starting_at_station_4_without_1_to_3_is_checked_then_sent_back():
    s = started()
    out = text(s.handle("I'm at station 4"))
    assert out.startswith("Before station 4 you should have identified:") and out.rstrip().endswith("Have you?")
    for k in (1, 2, 3):
        assert f"S{k} " in out and f"thing{k}a" in out
    out = text(s.handle("not sure"))
    assert "Go back to station 1" in out and "Station 1/5" in out
    assert s.current == 1 and not s.completed


def test_yes_to_the_check_marks_earlier_stations_and_opens_the_station():
    s = started()
    s.handle("station 3")
    out = text(s.handle("yes, I have"))
    assert "Station 3/5" in out and s.completed == {1, 2}


def test_i_have_not_counts_as_no():
    s = started()
    s.handle("4")
    assert "Go back to station 1" in text(s.handle("I have not"))


def test_next_needs_a_match_or_a_recheck():
    s = started(verdicts=[partial(), yes()])
    s.handle("1")
    assert "Describe what you see first" in text(s.handle("next"))
    s.handle("a wrong or partial description")
    assert "Not yet" in text(s.handle("next")) and s.current == 1
    assert "Station 1/5" not in text(s.handle("next"))
    out = text(s.handle("I rechecked it"))
    assert 1 in s.completed
    assert "Station 2/5" in text(s.handle("next"))


def test_match_then_next_advances():
    s = started(verdicts=[yes("You named both structures.")])
    s.handle("1")
    out = text(s.handle("thing1a and thing1b"))
    assert out.startswith("This matches the notes.") and "Type next for station 2" in out
    assert "Station 2/5" in text(s.handle("next"))


@pytest.mark.parametrize("phrase", ["skip to the last station", "jump to station 5", "go to station 4", "5"])
def test_cannot_skip_ahead(phrase):
    s = started()
    s.handle("1")
    out = text(s.handle(phrase))
    assert "can't skip ahead" in out
    assert s.current == 1 and 1 not in s.completed


def test_going_back_is_allowed_but_not_forward_past_the_first_missing():
    s = started(verdicts=[yes(), yes()])
    s.handle("1"); s.handle("d"); s.handle("next"); s.handle("d")      # stations 1 and 2 done, at station 2
    assert "Station 1/5" in text(s.handle("back"))
    assert "Station 3/5" in text(s.handle("go to station 3"))          # first missing is 3: allowed
    assert "can't skip ahead" in text(s.handle("skip to the last station"))


def test_descriptions_that_mention_numbers_are_not_jumps():
    s = started(verdicts=[yes()])
    s.handle("1")
    s.handle("it attaches to 5 fingers and the last one is the little finger")
    assert s.judge_calls and "last one" in s.judge_calls[0]
    assert s.current == 1


# ---- partial / no: what the notes say ---------------------------------------------------------------------

def test_no_consequence_sentence_is_exact_when_the_card_has_none():
    s = started(verdicts=[partial()])
    s.handle("1")
    out = text(s.handle("something"))
    assert NO_CONSEQUENCE in out and "The notes say you should see: see1a" in out
    assert NO_CONSEQUENCE == "The notes don't state a consequence for this. Ask your instructor."


def test_consequence_is_shown_only_when_the_judge_ties_it_to_the_mistake():
    cards = {i: card(i) for i in range(1, N + 1)}
    cards[1] = card(1, wrong_if_stated=["Fractures are common after punches"])
    cards[2] = card(2, clinical_if_stated=["Carpal tunnel syndrome"])
    s = started(cards=cards, verdicts=[partial(related=[0]), partial(related=[0])])
    s.handle("1")
    out = text(s.handle("x"))
    assert "What the notes say can go wrong: Fractures are common after punches" in out and NO_CONSEQUENCE not in out
    s.handle("rechecked"); s.handle("next")
    out = text(s.handle("y"))
    assert "Clinical note in the lecture: Carpal tunnel syndrome" in out and NO_CONSEQUENCE not in out


def test_unrelated_consequence_is_not_shown_even_if_the_card_has_one():
    cards = {i: card(i) for i in range(1, N + 1)}
    cards[1] = card(1, wrong_if_stated=["Tight carpal joints after cast removal"],
                    clinical_if_stated=["Metacarpal fractures are common"])
    s = started(cards=cards, verdicts=[partial(related=[]), partial()])      # judge: nothing relates / key left empty
    s.handle("1")
    out = text(s.handle("six carpal bones in three rows"))
    assert NO_CONSEQUENCE in out and "cast removal" not in out and "fractures" not in out
    out = text(s.handle("another wrong try"))
    assert NO_CONSEQUENCE in out


def test_a_judge_that_omits_or_garbles_the_field_shows_no_consequence():
    cards = {i: card(i, wrong_if_stated=["Something goes wrong"]) for i in range(1, N + 1)}
    s = started(cards=cards, verdicts=[{"match": "no", "feedback": "Wrong."},
                                       {"match": "no", "feedback": "Wrong.", "related_consequences": [7, -1, "0"]}])
    s.handle("1")
    assert NO_CONSEQUENCE in text(s.handle("a"))
    assert NO_CONSEQUENCE in text(s.handle("b"))


def test_judge_is_given_numbered_consequences():
    seen = {}

    def create(**kw):
        seen.update(kw)
        out = '{"match":"partial","feedback":"f","related_consequences":[1]}'
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=out)],
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))

    c = card(1, wrong_if_stated=["w0"], clinical_if_stated=["c1"])
    v = guide.judge_description(SimpleNamespace(messages=SimpleNamespace(create=create)), "m", c, "desc")
    msg = seen["messages"][0]["content"]
    assert '"n": 0' in msg and "w0" in msg and '"n": 1' in msg and "c1" in msg and "<student_description>" in msg
    assert v["related_consequences"] == [1]
    assert guide.consequence_items(c) == [("wrong", "w0"), ("clinical", "c1")]


def test_judge_failure_does_not_advance():
    s = started()
    s.judge = lambda c, t: (_ for _ in ()).throw(RuntimeError("boom"))
    s.handle("1")
    out = text(s.handle("my description"))
    assert "couldn't check" in out and 1 not in s.completed


def test_station_with_nothing_to_identify_completes_itself():
    cards = {i: card(i) for i in range(1, N + 1)}
    cards[1] = card(1, identify_these=[], what_you_should_see=[])
    s = started(cards=cards)
    out = text(s.handle("1"))
    assert "nothing to identify" in out and 1 in s.completed
    assert "Station 2/5" in text(s.handle("next"))


# ---- short replies, body type, flags ----------------------------------------------------------------------

def test_every_reply_is_at_most_six_lines():
    cards = {i: card(i, identify_these=[f"item {i}-{j} " + "x" * 40 for j in range(12)],
                     landmarks_relations=["landmark " * 12], variation_if_stated=["thick in obese individuals"])
             for i in range(1, N + 1)}
    metas = {i: meta(review=[{"id": "U1", "lecture": "L", "breadcrumb": "B", "quote": "q", "issue": "i " * 90,
                              "severity": "high"}]) for i in range(1, N + 1)}
    s = started(cards=cards, metas=metas, verdicts=[partial(), yes()])
    replies = [s.handle(x) for x in ["5", "no", "describe", "rechecked", "next", "skip to the last station", "list"]]
    for r in replies[:-1]:                      # `list` is exempt
        assert len(r) <= guide.MAX_LINES, r


def test_body_type_is_mentioned_only_where_the_notes_discuss_variation():
    cards = {i: card(i) for i in range(1, N + 1)}
    cards[2] = card(2, variation_if_stated=["Camper's fascia is very thick in obese individuals"])
    s = make(cards=cards, verdicts=[yes()])
    s.start(); s.handle("more fat, less muscle")
    out1 = text(s.handle("1"))
    assert "more fat" not in out1 and "variation" not in out1
    s.handle("done"); out2 = text(s.handle("next"))
    assert "variation (more fat, less muscle)" in out2 and "very thick in obese" in out2


def test_flags_are_logged_once_per_station():
    seen = []
    metas = {i: meta() for i in range(1, N + 1)}
    metas[1] = meta(review=[{"id": "U1", "lecture": "L", "breadcrumb": "B", "quote": "q", "issue": "std",
                             "severity": "high"}],
                    doubtful=[{"id": "D1", "lecture": "L", "breadcrumb": "B", "quote": "d", "issue": "std",
                               "severity": "medium", "reason": "r"},
                              {"id": "D2", "lecture": "L", "breadcrumb": "B", "quote": "unused", "issue": "std",
                               "severity": "medium", "reason": "r"}])
    cards = {i: card(i) for i in range(1, N + 1)}
    cards[1] = card(1, doubtful_used=["D1"])
    s = started(cards=cards, metas=metas, flag_logger=lambda kind, item, q: seen.append((kind, item["id"])))
    s.handle("1"); s.handle("back"); s.handle("1")
    assert sorted(seen) == [("note_line_doubtful", "D1"), ("note_line_under_review", "U1")]


# ---- stations and cards from the real notes ---------------------------------------------------------------

def sec(order, path, text, lecture="Lecture 99 - Test"):
    return {"lecture_title": lecture, "lecture_id": "L99-test", "order": order, "section_path": path,
            "breadcrumb": " > ".join([lecture] + path), "text_clean": text}


def test_stations_follow_the_lectures_order_and_tiny_ones_merge():
    rows = [sec(1, ["Overview"], "o" * 300), sec(2, ["Bones"], "tiny"), sec(3, ["Bones", "Carpals"], "c" * 300),
            sec(4, ["Muscles", "Thenar", "FPB"], "m" * 150), sec(5, ["Muscles", "Thenar", "APB"], "m" * 150),
            sec(6, ["Nerves", "Median"], "n" * 300)]
    st = guide.build_stations(rows)
    assert [s.name for s in st] == ["Overview", "Bones: Carpals", "Muscles: Thenar", "Nerves: Median"]
    assert [s.n for s in st] == [1, 2, 3, 4]
    assert [len(s.sections) for s in st] == [1, 2, 2, 1]


def test_real_lecture_09_stations():
    title, rows = guide.find_lecture("Lecture 09", guide.load_sections())
    assert title == "Lecture 09 - The Hand"
    st = guide.build_stations(rows)
    assert 15 <= len(st) <= 30 and st[0].name == "Overview"
    orders = [s["order"] for station in st for s in station.sections]
    assert orders == sorted(orders) and len(orders) == len(rows)       # nothing lost, nothing reordered
    assert all(sum(len(s["text_clean"]) for s in x.sections) >= guide.MIN_STATION_CHARS for x in st[:-1])


def test_ambiguous_lecture_name_is_an_error():
    with pytest.raises(ValueError, match="matches"):
        guide.find_lecture("Lecture 14", guide.load_sections())


def test_station_input_masks_tags_and_corrects(monkeypatch):
    from src import verified
    ctx = {"confirmed": [{"lecture": "Lecture 99 - Test", "breadcrumb": "Lecture 99 - Test > A", "claim_quote": "wrong line",
                          "issue": "std", "severity": "high"}],
           "doubtful": [{"lecture": "Lecture 99 - Test", "breadcrumb": "Lecture 99 - Test > A", "claim_quote": "iffy line",
                         "issue": "std", "severity": "low", "verification": {"verdict": "doubtful", "reason": "r"}}],
           "fixes": [{"id": "vf-1", "lecture": "Lecture 99 - Test", "breadcrumb": "Lecture 99 - Test > A",
                      "notes_quote": "fixed line", "correction": "right line", "decision": "confirm_error",
                      "by": "TEST", "date": "2026-10-06"}]}
    st = Station(1, "A", [sec(1, ["A"], "- wrong line\n- iffy line\n- fixed line\n- fine line")])
    text_, m = guide.station_input(st, ctx)
    assert "wrong line" not in text_ and "[LINE UNDER REVIEW U1]" in text_
    assert "iffy line [flagged for review D1]" in text_
    assert "fixed line" not in text_ and "right line [Verified by TEST, 2026-10-06]" in text_
    assert [r["id"] for r in m["review"]] == ["U1"] and [d["id"] for d in m["doubtful"]] == ["D1"]


def fake_client(calls):
    def create(**kw):
        calls.append(kw)
        card_json = '{"station":"A","identify_these":["x"],"what_you_should_see":["y"],"landmarks_relations":[],' \
                    '"clinical_if_stated":[],"wrong_if_stated":[],"variation_if_stated":[],"doubtful_used":[]}'
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=card_json)],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))
    return SimpleNamespace(messages=SimpleNamespace(create=create))


def test_cards_are_extracted_once_and_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(guide, "CACHE_DIR", tmp_path)
    calls = []
    client = fake_client(calls)
    ctx = {"confirmed": [], "doubtful": [], "fixes": []}
    st = Station(1, "A", [sec(1, ["A"], "- some notes text")])
    c1, _, cached1, _ = guide.extract_card(client, "m", "L99", st, ctx)
    c2, _, cached2, _ = guide.extract_card(client, "m", "L99", st, ctx)
    assert (cached1, cached2, len(calls)) == (False, True, 1) and c1 == c2
    assert list(tmp_path.glob("L99__*.json"))
    st2 = Station(1, "A", [sec(1, ["A"], "- changed notes text")])      # new text -> a new card, not a stale one
    guide.extract_card(client, "m", "L99", st2, ctx)
    assert len(calls) == 2
    system = calls[0]["system"]
    assert "Never use general knowledge" in system and "never add steps, cuts" in system


def test_scripted_runner_returns_a_transcript():
    s = make(verdicts=[yes()])
    out = []
    transcript = guide.run_session(s, ["more fat", "1", "my description", "quit"], out=out.append)
    assert transcript[0].startswith("Which cadaver") and "> my description" in transcript
    assert s.stage == "done" and 1 in s.completed


# ---- never cut a word in half ----------------------------------------------------------------------------

TEXTS = ["Distal-most region of the upper appendage, palmar region found anteriorly, dorsal region posteriorly",
         "The ulna does not directly articulate with the carpal bones. The wrist (radiocarpal) joint is formed by the radius.",
         "Flexor Digiti Minimi Brevis lies superficial and lateral (inside border) in the hypothenar eminence",
         "Superficialissimumabcdefghijklmnopqrstuvwxyz and then more words follow after it",
         "short", "", "a b c d e f g h i j k l m n o p q r s t u v w x y z " * 6]


@pytest.mark.parametrize("n", [5, 12, 20, 34, 60, 105, 150])
@pytest.mark.parametrize("original", TEXTS)
def test_clip_never_cuts_mid_word(original, n):
    out = guide.clip(original, n)
    first_word = len(original.split()[0]) if original.split() else 0
    assert len(out) <= max(n + 1, first_word + 1)          # no longer than asked (+ellipsis), unless one word is longer
    flat = " ".join(original.split())
    if out == flat:
        return
    base = out[:-1] if out.endswith("…") else out
    assert flat.startswith(base), (out, flat)
    after = flat[len(base):len(base) + 1]
    assert after == "" or not after.isalnum(), f"cut inside a word: {out!r}"          # next char is not a letter/digit


def test_take_and_replies_use_whole_words():
    items = ["Distal-most region of the upper appendage", "Opposable digit", "Palmar region found anteriorly"]
    out = guide.take(items, 2, 20)
    assert "(+1 more)" in out
    for piece in out.split(" (+")[0].split("; "):
        stem = piece.rstrip("…")
        assert any(i.startswith(stem) and (len(i) == len(stem) or not i[len(stem)].isalnum()) for i in items)


def test_session_lines_do_not_end_mid_word():
    long_item = "Distal-most region of the upper appendage and the palmar surface of the whole hand " * 3
    cards = {i: card(i, identify_these=[long_item] * 3, what_you_should_see=[long_item] * 3,
                     landmarks_relations=[long_item]) for i in range(1, N + 1)}
    s = started(cards=cards, verdicts=[partial("Feedback " * 60)])
    for reply in (s.handle("3"), s.handle("no"), s.handle("my description")):
        for line in reply:
            for part in line.split("…")[:-1]:
                assert not part or not part[-1].isalnum() or " " in part[-40:], line   # a word ends right before "…"


# ---- GuideSession: the web UI's entry point (same rules, structured results) -----------------------------

def web(verdicts=None):
    from src.modes.guide import GuideSession
    stations = [Station(n=i, name=f"Station name {i}", sections=[]) for i in range(1, N + 1)]
    answers = list(verdicts or [])
    g = GuideSession(lecture="Lecture 99", stations=stations, cards={i: card(i, wrong_if_stated=[f"going wrong {i}"]) for i in range(1, N + 1)},
                     metas={i: meta() for i in range(1, N + 1)}, judge=lambda c, t: answers.pop(0), model="claude-sonnet-5-5")
    g.stage = "station"
    return g


def statuses(r):
    return [s["status"] for s in r["state"]["stations"]]


def test_step_returns_state_and_progress():
    g = web([{"match": "yes", "feedback": "Good.", "related_consequences": []}])
    r = g.step("station 1")
    assert r["state"]["current"] == 1 and r["state"]["card"]["identify_these"] == ["thing1a", "thing1b"]
    assert r["state"]["progress"] == 0 and statuses(r)[0] == "current"
    r = g.step("thing1a and thing1b")
    assert r["detail"]["verdict"] == "yes" and r["state"]["done"] == [1] and r["state"]["progress"] == 1 / N
    assert r["state"]["can_advance"] is True and [e["kind"] for e in r["events"]] == ["judge"]
    assert g.step("next")["state"]["current"] == 2


def test_stepper_locks_every_station_after_the_first_missing_one():
    g = web()
    r = g.step("station 1")
    assert statuses(r) == ["current", "locked", "locked", "locked", "locked"]
    assert statuses(g.step("rechecked")) == ["current", "open", "locked", "locked", "locked"]


def test_skipping_ahead_is_refused_and_recorded():
    g = web()
    g.step("station 1")
    r = g.step("station 4")
    assert r["state"]["current"] == 1 and any(e["kind"] == "no_skip" for e in r["events"])
    assert "can't skip ahead" in " ".join(r["lines"])


def test_check_stage_then_sent_back_to_the_first_missing_station():
    g = web()
    r = g.step("station 3")
    assert r["state"]["stage"] == "check" and r["state"]["check"]["pending"] == 3 and r["events"][0]["kind"] == "check"
    r = g.step("no")
    assert r["state"]["current"] == 1 and any(e["kind"] == "no_skip" for e in r["events"])
    assert statuses(r)[1:] == ["locked"] * 4


def test_check_yes_completes_the_earlier_stations():
    g = web()
    g.step("station 3")
    r = g.step("yes")
    assert r["state"]["current"] == 3 and r["state"]["done"] == [1, 2] and statuses(r) == ["done", "done", "current", "locked", "locked"]


def test_consequence_is_shown_only_when_tied_to_the_mistake():
    g = web([{"match": "no", "feedback": "Wrong.", "related_consequences": []},
             {"match": "partial", "feedback": "Some.", "related_consequences": [0]}])
    g.step("station 1")
    d = g.step("a hand")["detail"]
    assert d["verdict"] == "no" and d["consequence"] == NO_CONSEQUENCE and d["consequence_stated"] is False
    d = g.step("a different thing")["detail"]
    assert d["verdict"] == "partial" and d["consequence_stated"] is True and "going wrong 1" in d["consequence"]


def test_step_cost_comes_from_the_judge_usage():
    g = web()
    g.step("station 1")

    def judge(c, t):
        g.usage["input_tokens"] += 1000
        g.usage["output_tokens"] += 100
        return {"match": "no", "feedback": "x", "related_consequences": []}

    g.judge = judge
    r = g.step("anything")
    assert r["tokens"] == {"input": 1000, "output": 100} and r["cost"] == pytest.approx(0.003)
    assert g.step("rechecked")["cost"] == 0
