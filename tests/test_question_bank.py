"""The question bank: versions, import with any column layout, item-writing checks, statistics, exam-secure protection, quiz integration and what students can receive.
Everything runs on throw-away databases (conftest points the bank at tmp); no model is called (the quiz uses the shared fakes)."""
import io
import json
import random

import pytest

from src import student_view as sv
from src.qbank import checks, importer, integrate, sample, service as bs, stats as bstats
from src.qbank import store as S
from src.quiz import generate, service
from src.quiz.store import QuizStore
from tests.quiz_fakes import EMPTY_CTX, HAND, Behavior, install, runtime

GOOD = {"stem": "", "lead_in": "Which nerve passes through the carpal tunnel?", "options": [{"id": i, "text": t} for i, t in zip("ABCD", ["Median nerve", "Ulnar nerve", "Radial nerve", "Axillary nerve"])],
        "answer": "A", "explanation": "It runs with the flexor tendons.", "lecture": HAND, "region": "Upper limb", "tags": ["nerves"], "source": "instructor", "status": "approved", "use": "practice"}


def q(bank, **kw):
    return bank.create({**GOOD, **kw}, "Dr. Inglis")


@pytest.fixture
def bank(tmp_path):
    return S.BankStore(tmp_path / "bank.db")


# ---- the real bank is never touched ------------------------------------------------------------------------------------------

def test_the_default_bank_path_is_redirected_in_every_test():
    assert "default_bank" in str(S.DB_PATH)


# ---- versions, restore, comments, bulk ------------------------------------------------------------------------------------------

def test_every_edit_is_a_version_and_a_version_can_be_restored(bank):
    a = q(bank)
    assert a["version"] == 1
    b = bank.update(a["id"], {"lead_in": "Which nerve runs through the carpal tunnel?"}, "Dr. Inglis", "wording")
    assert b["version"] == 2 and bank.update(a["id"], {}, "x")["version"] == 2           # no change = no new version
    vs = bank.versions(a["id"])
    assert [v["version"] for v in vs] == [2, 1] and vs[1]["data"]["lead_in"] == GOOD["lead_in"]
    assert [d["field"] for d in S.diff_data(vs[1]["data"], vs[0]["data"])] == ["lead_in"]
    r = bank.restore(a["id"], 1, "Dr. Inglis")
    assert r["version"] == 3 and r["data"]["lead_in"] == GOOD["lead_in"] and "restored version 1" in bank.versions(a["id"])[0]["note"]
    bank.add_comment(a["id"], "Dr. Inglis", "check the explanation")
    assert bank.comments(a["id"])[0]["text"] == "check the explanation"


def test_bad_questions_are_refused(bank):
    for bad in ({"lead_in": ""}, {"options": GOOD["options"][:1]}, {"answer": "E"}, {"status": "weird"},
                {"options": [{"id": "A", "text": "Same"}, {"id": "B", "text": "same"}]}):
        with pytest.raises(S.BankError):
            q(bank, **bad)


def test_bulk_changes_and_tags(bank):
    ids = [q(bank, lead_in=f"Which nerve number {i}?")["id"] for i in range(3)]
    assert bank.bulk(ids, {"status": "retired"}, by="x") == 3 and bank.bulk(ids, add_tags=["hand", "Nerves"], by="x") == 3
    d = bank.get(ids[0])["data"]
    assert d["status"] == "retired" and d["tags"] == ["nerves", "hand"]            # "Nerves" was already there (case-insensitive)
    bank.bulk(ids, remove_tags=["hand"], by="x")
    assert bank.get(ids[0])["data"]["tags"] == ["nerves"]


def test_listing_filters_search_and_counts(bank):
    q(bank, lead_in="Which nerve supplies the deltoid?", options=[{"id": "A", "text": "Axillary nerve"}, {"id": "B", "text": "Radial nerve"}], tags=["shoulder"], region="Upper limb")
    q(bank, lead_in="Which artery supplies the thigh?", options=[{"id": "A", "text": "Femoral artery"}, {"id": "B", "text": "Popliteal artery"}], status="draft", use="exam_secure", region="Lower limb", lecture="Lecture 08")
    rows = bs.listing(bank, {"q": "deltoid"})
    assert rows["total"] == 1 and rows["items"][0]["tags"] == ["shoulder"]
    assert bs.listing(bank, {"use": "exam_secure"})["total"] == 1 and bs.listing(bank, {"region": "Lower limb", "status": "draft"})["total"] == 1
    c = bs.listing(bank, {})["counts"]
    assert (c["total"], c["draft"], c["approved"], c["exam_secure"]) == (2, 1, 1, 1)


# ---- import --------------------------------------------------------------------------------------------------------------------

ODD = ("Item;What is asked;1;2;3;4;Right one;Why;Chapter\n"
       "1;Which nerve passes through the carpal tunnel?;Median nerve;Ulnar nerve;Radial nerve;Axillary nerve;Median nerve;It runs with the flexor tendons.;Lecture 09 - The Hand\n"
       "2;Which muscle abducts the thumb?;Abductor pollicis brevis;Adductor pollicis;Palmaris brevis;Opponens digiti minimi;3;;Lecture 09 - The Hand\n"
       "3;Broken row;Only one option;;;;A;;\n")


def test_an_odd_spreadsheet_layout_is_mapped_previewed_and_imported_with_the_safe_defaults(bank):
    p = bs.preview_import(bank, "odd.csv", ODD.encode())
    assert p["headers"][:3] == ["Item", "What is asked", "1"] and p["n_rows"] == 3
    m = p["mapping"]
    assert "lead_in" not in m and "answer" not in m and m["option_a"] == "1" and m["option_d"] == "4" and m["explanation"] == "Why"      # guessed from the headers
    assert bs.preview_import(bank, "", b"", m, p["import_id"])["ready"] == 0                          # nothing can be created until the question and answer are mapped
    m.update(lead_in="What is asked", answer="Right one", lecture="Chapter")                          # the instructor fixes the mapping in the preview
    p2 = bs.preview_import(bank, "", b"", m, p["import_id"])
    assert p2["ready"] == 2 and p2["problems"][0]["row"] == "3" and p2["questions"][1]["answer"] == "C"       # "3" = the third option
    out = bs.commit_import(bank, p["import_id"], m, "draft", "exam_secure", True, "Dr. Inglis")
    assert out["created"] == 2 and len(out["problems"]) == 1
    rows = bank.all()
    assert {r["data"]["status"] for r in rows} == {"draft"} and {r["data"]["use"] for r in rows} == {"exam_secure"} and {r["data"]["source"] for r in rows} == {"imported"}
    first = next(r for r in rows if "carpal" in r["data"]["lead_in"])
    assert first["data"]["answer"] == "A" and first["data"]["lecture"] == "Lecture 09 - The Hand"            # the answer was the TEXT of an option
    with pytest.raises(S.BankError):
        bs.commit_import(bank, p["import_id"], m, "draft", "exam_secure", True, "x")                          # the parsed file is deleted after the commit


def test_export_then_import_round_trips_and_formulas_are_neutralised(bank):
    q(bank, explanation="=HYPERLINK(\"http://x\")")
    csv_text = S.export_csv(bank.all())
    assert "'=HYPERLINK" in csv_text
    other = S.BankStore(bank.path.parent / "other.db")
    p = bs.preview_import(other, "export.csv", csv_text.encode())
    assert p["mapping"]["lead_in"] == "lead_in" and p["mapping"]["option_a"] == "option_a" and p["ready"] == 1


def test_xlsx_docx_and_template_imports(bank):
    import docx
    x = importer.template_xlsx()
    h, rows = importer.read_table("t.xlsx", x)
    assert h[0] == "Question (lead-in)" and rows[0][2] == "Median nerve"
    d = docx.Document()
    for line in ["1. Which nerve passes through the carpal tunnel?", "A. Median nerve", "B. Ulnar nerve", "C. Radial nerve", "Answer: A", "Explanation: It runs with the tendons.",
                 "2. Which muscle abducts the thumb?", "A. Adductor pollicis", "B. Abductor pollicis brevis", "Answer: B"]:
        d.add_paragraph(line)
    b = io.BytesIO()
    d.save(b)
    p = bs.preview_import(bank, "q.docx", b.getvalue())
    assert p["ready"] == 2 and p["questions"][1]["answer"] == "B"
    for name, data in (("x.exe", b"MZ"), ("x.xlsx", b"not a zip"), ("x.csv", b"")):
        with pytest.raises(S.BankError):
            importer.read_table(name, data)


def test_near_duplicates_are_flagged_and_identical_ones_skipped(bank):
    q(bank, options=[{"id": i, "text": t} for i, t in zip("ABCD", ["Median nerve", "Ulnar nerve", "Radial nerve", "Musculocutaneous nerve"])])
    csv_text = importer.template_csv()                                                  # the template question is the same as the one in the bank
    p = bs.preview_import(bank, "t.csv", csv_text.encode())
    assert p["duplicates"] == 1
    out = bs.commit_import(bank, p["import_id"], p["mapping"], "draft", "exam_secure", True, "x")
    assert out["skipped_duplicates"] == 1 and out["created"] == 0


# ---- the AI / rule checks (flags only) ------------------------------------------------------------------------------------------

def flaws(**kw):
    return {f["code"] for f in checks.nbme_flaws(S.normalize({**GOOD, **kw}))}


def test_item_writing_flaws_are_flagged_and_a_clean_question_is_not():
    assert flaws() == set() or flaws() <= {"convergence"}
    assert "negative" in flaws(lead_in="Which nerve does NOT pass through the carpal tunnel?")
    assert "all_none" in flaws(options=[{"id": "A", "text": "Median nerve"}, {"id": "B", "text": "None of the above"}])
    assert "absolutes" in flaws(options=[{"id": "A", "text": "Median nerve"}, {"id": "B", "text": "Always the ulnar nerve"}])
    assert "vague" in flaws(options=[{"id": "A", "text": "Median nerve"}, {"id": "B", "text": "Usually the ulnar nerve"}])
    assert "longest_key" in flaws(options=[{"id": "A", "text": "The median nerve together with its palmar cutaneous branch"}, {"id": "B", "text": "Ulnar"}, {"id": "C", "text": "Radial"}])
    assert "grammar" in flaws(lead_in="The nerve in the carpal tunnel is an", options=[{"id": "A", "text": "Median nerve"}, {"id": "B", "text": "Ulnar nerve"}, {"id": "C", "text": "Axillary nerve"}], answer="C")
    assert "lead_in_open" in flaws(lead_in="The carpal tunnel contains")


def test_flags_never_change_status_or_text(bank):
    a = q(bank, lead_in="Which nerve does NOT pass through the carpal tunnel?")
    bs.run_local_checks(bank, a["id"])
    b = bank.get(a["id"])
    assert b["data"] == a["data"] and any(f["code"] == "negative" for f in b["flags"]) and b["data"]["status"] == "approved"
    bank.dismiss_flag(a["id"], "nbme", "negative")
    assert bank.get(a["id"])["flags"][0]["dismissed"] is True and S.row_of(bank.get(a["id"]))["flagged"] is False


def test_the_answer_key_check_flags_a_mismatch(monkeypatch):
    from src import llm
    d = S.normalize(GOOD)
    rt = runtime()
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: ({"answer_id": "B", "reason": "Ulnar passage"}, {}))
    f = checks.key_check(d, rt.searcher, object(), "m")
    assert [x["code"] for x in f] == ["key_mismatch"] and "chose B" in f[0]["message"]
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: ({"answer_id": "A", "reason": ""}, {}))
    assert checks.key_check(d, rt.searcher, object(), "m") == []


# ---- statistics ----------------------------------------------------------------------------------------------------------------------

def test_discrimination_math():
    assert bstats.point_biserial([1, 1, 0, 0], [4, 3, 1, 0]) > 0.9
    assert bstats.point_biserial([0, 0, 1, 1], [4, 3, 1, 0]) < -0.9
    assert bstats.point_biserial([1, 1, 1], [1, 2, 3]) is None                                  # nobody missed it: undefined


def _attempts(n, good_item_correct):
    out = []
    for i in range(n):
        strong = i % 2 == 0
        out.append({"item_ids": ["bank:q-1:v1"], "selections": {0: ["A"] if (strong == good_item_correct) else ["B"]}, "score": 4 if strong else 1, "length": 5})
    return out


ITEM = {"answer_ids": ["A"], "options": [{"id": "A", "text": "Median nerve"}, {"id": "B", "text": "Ulnar nerve"}]}


def test_stats_flag_only_with_enough_attempts_and_never_retire(bank):
    few = bstats.compute(_attempts(8, False), lambda i: ITEM, {})["q-1"]
    assert few["n"] == 8 and few["discrimination"] is None and few["flags"] == []
    mid = bstats.compute(_attempts(14, False), lambda i: ITEM, {})["q-1"]
    assert mid["discrimination"] < 0 and mid["flags"] == [] and mid["enough"]                         # 14 < 20: shown, not flagged
    neg = bstats.compute(_attempts(30, False), lambda i: ITEM, {})["q-1"]
    assert [f["code"] for f in neg["flags"]] == ["negative_discrimination"] and neg["distractors"][1]["picks"] == 15
    ok = bstats.compute(_attempts(30, True), lambda i: ITEM, {})["q-1"]
    assert ok["discrimination"] > 0.9 and ok["flags"] == []
    easy = bstats.compute([{"item_ids": ["bank:q-1:v1"], "selections": {0: ["A"]}, "score": 5 if i else 1, "length": 5} for i in range(30)], lambda i: ITEM, {})["q-1"]
    assert "too_easy" in [f["code"] for f in easy["flags"]]


def test_stats_come_from_submitted_real_quizzes_only(bank, tmp_path):
    qs = QuizStore(tmp_path / "quizzes.db")
    a = q(bank)
    its = [integrate.to_quiz_item(a)] + [integrate.to_quiz_item(q(bank, lead_in=f"Which nerve number {i}?")) for i in range(4)]
    qs.save_items(its)
    for user in ("s1", "s2", "preview:prof"):
        qid = qs.create_quiz(user, [i["item_id"] for i in its], 5, {}, "open")
        qs.select(user, qid, 0, ["A"])
        qs.finish(user, qid, 1)
    st = bs.stats_map(bank, qs)[a["id"]]
    assert st["n"] == 2 and st["p_correct"] == 1.0                                              # the preview quiz is left out
    assert bs.detail.__name__ == "detail"


# ---- exam-secure and the similarity guard ----------------------------------------------------------------------------------------------

def test_similarity_guard():
    d = S.normalize(GOOD)
    twin = checks.text_of({**d, "lead_in": "Which nerve passes through the carpal tunnel region?"})
    assert checks.secure_too_close(d, [twin]) and not checks.secure_too_close(d, ["Which artery supplies the thigh? Femoral artery Popliteal artery Obturator Gluteal"])
    assert checks.near_duplicates(d, [("x", d)])[0][0] == "x"


def make_bank_for_quiz():
    bank = S.BankStore()
    ids = {}
    ids["served"] = q(bank, lead_in="Which nerve supplies the thenar muscles?", options=[{"id": i, "text": t} for i, t in zip("ABCD", ["Recurrent branch of the median nerve", "Deep branch of the ulnar nerve", "Posterior interosseous nerve", "Axillary nerve"])])["id"]
    ids["draft"] = q(bank, lead_in="Which nerve DRAFTSECRET supplies the first lumbrical?", status="draft")["id"]
    ids["secure"] = q(bank, lead_in="Which nerve SECURESECRET supplies the hypothenar muscles?", use="exam_secure")["id"]
    ids["retired"] = q(bank, lead_in="Which nerve RETIREDSECRET supplies the extensors?", status="retired")["id"]
    ids["imported"] = q(bank, lead_in="Which nerve IMPORTSECRET supplies the interossei?", source="imported", status="draft", use="exam_secure")["id"]
    return bank, ids


def served_bank_ids(st, qid):
    return {st.item(i).get("bank_id") for i in st.get_quiz("s1", qid)["item_ids"]} - {None}


def test_a_students_quiz_only_ever_contains_approved_practice_bank_questions(monkeypatch):
    install(monkeypatch, Behavior())
    bank, ids = make_bank_for_quiz()
    for reviewed_only in (False, True):
        st = QuizStore()
        rt = runtime()
        out = service.new_quiz("s1", [HAND], {"mode": "materials", "n": 5, "selected": [HAND], "reviewed_only": reviewed_only}, rt, store=st, ctx=EMPTY_CTX, rng=random.Random(2), web_lookup=None, ver_model="openai/gpt-oss-120b")
        if reviewed_only:
            assert out["status"] == "failed"                                                   # only one approved practice question: "never replaced by unreviewed ones"
            continue
        assert out["status"] == "ready"
        assert served_bank_ids(st, out["quiz_id"]) == {ids["served"]}
        blob = json.dumps(service.open_view("s1", out["quiz_id"], [HAND], store=st))
        assert not any(w in blob for w in ("DRAFTSECRET", "SECURESECRET", "RETIREDSECRET", "IMPORTSECRET"))
        assert sv.leaks(service.open_view("s1", out["quiz_id"], [HAND], store=st)) == []
        res = service.results("s1", service.submit("s1", out["quiz_id"], [HAND], store=st)["quiz_id"], [HAND], store=st) if False else None
    rows = {r["data"]["lead_in"] for r in bank.all() if r["data"]["source"] == "ai"}
    assert rows, "new AI questions are saved to the bank as drafts"
    assert all(r["data"]["status"] == "draft" and r["data"]["use"] == "practice" for r in bank.all() if r["data"]["source"] == "ai")


def test_changing_a_questions_status_takes_it_out_of_the_next_quiz(monkeypatch):
    install(monkeypatch, Behavior())
    bank, ids = make_bank_for_quiz()
    bank.update(ids["served"], {"use": "exam_secure"}, "Dr. Inglis")
    st = QuizStore()
    out = service.new_quiz("s1", [HAND], {"mode": "materials", "n": 5, "selected": [HAND]}, runtime(), store=st, ctx=EMPTY_CTX, rng=random.Random(2), web_lookup=None, ver_model="openai/gpt-oss-120b")
    assert served_bank_ids(st, out["quiz_id"]) == set()
    # an AI question the instructor makes exam-secure or retires is not reused either
    ai = next(r for r in bank.all() if r["data"]["source"] == "ai")
    bank.update(ai["id"], {"status": "retired"}, "Dr. Inglis")
    assert integrate.ai_item_ok(st.item(ai["quiz_item_id"]), False, bank) is False


def test_ai_questions_too_close_to_an_exam_secure_question_are_replaced(monkeypatch):
    install(monkeypatch, Behavior())
    first = QuizStore()
    out = service.new_quiz("s1", [HAND], {"mode": "materials", "n": 5, "selected": [HAND]}, runtime(), store=first, ctx=EMPTY_CTX, rng=random.Random(2), web_lookup=None, ver_model="openai/gpt-oss-120b")
    made = [first.item(i) for i in first.get_quiz("s1", out["quiz_id"])["item_ids"]]
    bank = S.BankStore()
    for it in made[:3]:                                                                          # the instructor's secret exam holds near-copies of three of them
        q(bank, lead_in=it["lead_in"], options=[{"id": o["id"], "text": o["text"]} for o in it["options"]], answer=it["answer_ids"][0], use="exam_secure", status="approved", lecture="")
    assert generate.SECURE_SIMILARITY == checks.SECURE_LIMIT
    secure = integrate.secure_texts(bank)
    assert len(secure) == 3
    fresh = QuizStore(first.path.parent / "fresh.db")
    again = service.new_quiz("s2", [HAND], {"mode": "materials", "n": 5, "selected": [HAND]}, runtime(), store=fresh, ctx=EMPTY_CTX, rng=random.Random(2), web_lookup=None, ver_model="openai/gpt-oss-120b")
    got = [fresh.item(i) for i in fresh.get_quiz("s2", again["quiz_id"])["item_ids"]] if again["quiz_id"] else []
    for it in got:
        assert not checks.secure_too_close(S.normalize({"lead_in": it["lead_in"], "stem": it["stem"], "options": it["options"], "answer": it["answer_ids"][0]}), secure)


def test_style_examples_come_only_from_approved_practice_questions_and_can_be_switched_off(monkeypatch):
    beh = install(monkeypatch, Behavior())
    bank, ids = make_bank_for_quiz()
    ex = integrate.style_examples({"mode": "materials", "selected": [HAND]}, [HAND], bank)
    assert len(ex) == 1 and "thenar" in ex[0] and not any(w in " ".join(ex) for w in ("DRAFTSECRET", "SECURESECRET", "RETIREDSECRET"))
    service.new_quiz("s1", [HAND], {"mode": "materials", "n": 5, "selected": [HAND]}, runtime(), store=QuizStore(), ctx=EMPTY_CTX, rng=random.Random(2), web_lookup=None, ver_model="openai/gpt-oss-120b")
    assert any("<style_examples>" in p for p in beh.prompts)
    beh.prompts.clear()
    service.new_quiz("s1", [HAND], {"mode": "materials", "n": 5, "selected": [HAND], "different_style": True}, runtime(), store=QuizStore(), ctx=EMPTY_CTX, rng=random.Random(2), web_lookup=None, ver_model="openai/gpt-oss-120b")
    assert not any("<style_examples>" in p for p in beh.prompts)


def test_bank_candidates_respect_the_students_access():
    bank = S.BankStore()
    a = q(bank, lecture="Lecture 12 - Posterior Leg")
    assert integrate.bank_candidates({"mode": "materials", "selected": ["Lecture 12 - Posterior Leg"]}, [HAND], bank) == []
    assert len(integrate.bank_candidates({"mode": "materials", "selected": ["Lecture 12 - Posterior Leg"]}, ["Lecture 12 - Posterior Leg"], bank)) == 1
    assert a["id"]


# ---- the sample set (fake, for tests and demos only) ------------------------------------------------------------------------------------

def test_the_fifteen_sample_questions_are_fake_and_marked(bank):
    qs = sample.sample_questions()
    assert len(qs) == 15 and len({x["region"] for x in qs}) == 3 and all(x["sample"] and "sample" in x["tags"] for x in qs)
    for x in qs:
        bank.create(x, "sample")
    assert all(r["data"]["sample"] for r in bank.all())


# ---- the API: instructor only ---------------------------------------------------------------------------------------------------------------

def test_every_bank_route_is_403_for_a_student_and_the_instructor_can_use_them(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app_api.main import create_app
    from app_api.routers import auth as auth_router
    from src import auth
    monkeypatch.setattr(auth, "USERS_PATH", tmp_path / "users.json")
    auth.save_users({"prof": auth.new_record("Prof", "professor", "password-long-1"), "s1": auth.new_record("S1", "student", "password-long-1", [HAND])})
    monkeypatch.setenv("ANATOVISION_API_SESSIONS_PATH", str(tmp_path / "sessions.db"))
    auth_router._fails.clear()
    auth._fails.clear()
    app = create_app(warm_runtime=False)
    body = {**GOOD, "note": ""}
    with TestClient(app) as c:
        def login(u):
            assert c.post("/api/auth/login", json={"username": u, "password": "password-long-1"}).status_code == 200
        login("s1")
        routes = [("get", "/api/admin/bank"), ("get", "/api/admin/bank/q-1"), ("post", "/api/admin/bank", body), ("put", "/api/admin/bank/q-1", body), ("get", "/api/admin/bank/export.csv"),
                  ("get", "/api/admin/bank/template.csv"), ("get", "/api/admin/bank/template.xlsx"), ("post", "/api/admin/bank/bulk", {"ids": [], "action": "approve"}),
                  ("post", "/api/admin/bank/q-1/restore", {"version": 1}), ("post", "/api/admin/bank/q-1/comments", {"text": "x"}), ("post", "/api/admin/bank/q-1/check"),
                  ("post", "/api/admin/bank/import/commit", {"import_id": "x", "mapping": {}}), ("post", "/api/admin/bank/q-1/recheck")]
        for method, url, *b in routes:
            r = getattr(c, method)(url, **({"json": b[0]} if b else {}))
            assert r.status_code == 403, (method, url, r.status_code)
        assert c.post("/api/admin/bank/import/preview", files={"file": ("a.csv", b"a,b\n1,2")}).status_code == 403
        c.post("/api/auth/logout")
        login("prof")
        made = c.post("/api/admin/bank", json=body)
        assert made.status_code == 200, made.text
        qid = made.json()["id"]
        assert made.json()["data"]["use"] == "practice"
        got = c.put(f"/api/admin/bank/{qid}", json={**body, "lead_in": "Which nerve runs through the carpal tunnel?", "note": "wording"}).json()
        assert got["version"] == 2 and [v["version"] for v in got["versions"]] == [2, 1] and got["versions"][0]["changed"] == ["lead_in"]
        assert c.post(f"/api/admin/bank/{qid}/restore", json={"version": 1}).json()["version"] == 3
        assert c.post(f"/api/admin/bank/{qid}/comments", json={"text": "note to self"}).json()["comments"][0]["text"] == "note to self"
        assert c.post("/api/admin/bank/bulk", json={"ids": [qid], "action": "retire"}).json() == {"changed": 1}
        listing = c.get("/api/admin/bank", params={"status": "retired"}).json()
        assert listing["total"] == 1 and listing["counts"]["retired"] == 1
        assert c.get("/api/admin/bank/export.csv").text.startswith("id,stem,lead_in")
        pv = c.post("/api/admin/bank/import/preview", files={"file": ("odd.csv", ODD.encode())}).json()
        assert pv["ready"] == 0 and pv["mapping"]["option_a"] == "1"
        pv = c.post("/api/admin/bank/import/preview", data={"import_id": pv["import_id"], "mapping": json.dumps({**pv["mapping"], "lead_in": "What is asked", "answer": "Right one"})}).json()
        assert pv["ready"] == 2
        done = c.post("/api/admin/bank/import/commit", json={"import_id": pv["import_id"], "mapping": pv["mapping"]}).json()
        assert done["created"] == 1 and done["skipped_duplicates"] == 1            # the carpal-tunnel row is the question already in the bank
        imported = c.get("/api/admin/bank", params={"source": "imported"}).json()
        assert imported["total"] == 1 and {r["status"] for r in imported["items"]} == {"draft"} and {r["use"] for r in imported["items"]} == {"exam_secure"}
        assert c.get("/api/admin/stats").json()["bank_counts"]["total"] == 2
        assert c.get("/api/admin/bank/q-nope").status_code == 404


def test_a_notes_change_marks_the_questions_that_cite_it(tmp_path):
    chunks = [{"section_id": "L09#001:Nerves", "chunk_index": 0, "text": "The median nerve passes through the carpal tunnel."}]
    bank = S.BankStore(tmp_path / "b.db")
    link = {"doc_id": "L09", "section_id": "L09#001:Nerves", "breadcrumb": "Lecture 09 > Nerves", "hash": integrate.section_hash(chunks, "L09#001:Nerves")}
    a = q(bank, links=[link])
    b = q(bank, lead_in="Which nerve supplies the deltoid?")
    assert integrate.recheck_after_swap(chunks, bank) == 0
    changed = [{**chunks[0], "text": "The median nerve passes deep to the flexor retinaculum."}]
    assert integrate.recheck_after_swap(changed, bank) == 1 and "was changed" in bank.get(a["id"])["recheck"] and bank.get(b["id"])["recheck"] == ""
    assert bank.get(a["id"])["data"]["status"] == "approved"                                       # a mark, never a status change
    assert S.row_of(bank.get(a["id"]))["needs_recheck"] is True
    integrate.clear_recheck(a["id"], changed, bank)
    assert bank.get(a["id"])["recheck"] == "" and integrate.recheck_after_swap(changed, bank) == 0
    integrate.recheck_after_swap([], bank)
    assert "no longer in the notes" in bank.get(a["id"])["recheck"]


from tests.test_notes_manager import lab  # noqa: E402,F401  (fixture: a throw-away live data folder)


def test_editing_or_archiving_a_document_in_the_notes_manager_marks_the_questions_that_cite_it(lab):
    from src import notes_manager as NM
    chunks = NM._read_jsonl(lab["index"] / "chunks.jsonl")
    c = next(x for x in chunks if x["doc_id"] == "L01-alpha")
    bank = S.BankStore()
    a = q(bank, links=[integrate.make_link(c, chunks)], lecture="Lecture 01 - Alpha")
    NM.edit_sections("prof", "L01-alpha", [{"index": 0, "text": "The alpha organ is supplied by the gamma artery."}])
    got = bank.get(a["id"])
    assert "was changed" in got["recheck"] and got["data"]["status"] == "approved"
    integrate.clear_recheck(a["id"], NM._read_jsonl(lab["index"] / "chunks.jsonl"), bank)
    assert bank.get(a["id"])["recheck"] == ""
    NM.archive("prof", "L01-alpha")
    assert "no longer in the notes" in bank.get(a["id"])["recheck"]
