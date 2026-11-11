"""Write docs/api_examples.json: one example response per endpoint of docs/api_contract.md. Real shapes (every example is validated against the
API's own response model, and a test does it again), fake text.

    .venv/bin/python scripts/build_api_examples.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic import TypeAdapter  # noqa: E402

from app_api import schemas as S  # noqa: E402

T = "2026-10-20T14:03:11Z"
NOTES = {"n": 1, "type": "notes", "title": "Lecture notes", "subtitle": "Lecture 08, Anterior and Medial Thigh › Femoral Triangle", "lecture_id": "L08-anterior-and-medial-thigh",
         "url": None, "snippet": "Boundaries: inguinal ligament (superior), sartorius (lateral), adductor longus (medial). Fake example text.", "retrieved_at": None, "license": None}
OPENSTAX = {"n": 2, "type": "openstax", "title": "OpenStax Anatomy & Physiology 2e, section 11.6", "subtitle": "Appendicular Muscles of the Pelvic Girdle and Lower Limbs",
            "lecture_id": None, "url": "https://openstax.org/books/anatomy-and-physiology-2e/pages/11-6-appendicular-muscles-of-the-pelvic-girdle-and-lower-limbs",
            "snippet": "Fake example passage about the muscles of the thigh.", "retrieved_at": None, "license": "CC BY-NC-SA 4.0"}
WIKI = {"n": 3, "type": "wikipedia", "title": "Wikipedia: Femoral triangle", "subtitle": "Wikipedia", "lecture_id": None, "url": "https://en.wikipedia.org/wiki/Femoral_triangle",
        "snippet": "Fake example intro of a Wikipedia page.", "retrieved_at": "2026-10-20", "license": "CC BY-SA 4.0"}
GUIDE = {"n": 1, "type": "guide", "title": "Dissection guide", "subtitle": "Class 10, slide 4", "lecture_id": "L09-the-hand", "url": None,
         "snippet": "Fake example station text from a dissection guide slide.", "retrieved_at": None, "license": None}
ANSWER = {"id": "c0ffee:1", "role": "assistant", "created_at": T, "kind": "answer", "timing_ms": 8421,
          "markdown": "**The femoral triangle** lies in the upper medial thigh [1].\n\n- Its roof is the fascia lata [1].\n- Its floor includes the pectineus [2].",
          "sources": [NOTES, OPENSTAX], "footer": {"basis_line": None, "access_note": None}}
ASK_FOOTER = {**ANSWER, "id": "c0ffee:3", "sources": [OPENSTAX, WIKI], "markdown": "Fake answer from the textbook [2] and Wikipedia [3].",
              "footer": {"basis_line": "Based on OpenStax and Wikipedia, not Dr. Inglis's notes.", "access_note": None}}
USER_MSG = {"id": "c0ffee:0", "role": "user", "created_at": T, "kind": "answer", "markdown": "What are the boundaries of the femoral triangle?", "sources": [],
            "footer": None, "timing_ms": 0}
ITEM = {"stem": "", "lead_in": "Which nerve passes through the carpal tunnel?", "selection_mode": "single",
        "options": [{"id": c, "text": f"Fake option {c}"} for c in "ABCDE"]}
RESULT_Q = {"n": 1, "stem": "", "lead_in": ITEM["lead_in"], "options": ITEM["options"], "selected": ["B"], "answer_ids": ["B"], "correct": True,
            "explanation": "Fake explanation of why B is correct.", "alternatives": {c: f"Fake reason {c} is wrong." for c in "ACDE"},
            "evidence": [{"id": "c1", "label": "Lecture 09 - The Hand > Nerves", "tier": "Course material", "url": None, "visible": True,
                          "text": "Fake passage: the median nerve passes through the carpal tunnel.", "license": None}],
            "label": "AI-checked (two models agreed and sources were checked). Not reviewed by Dr. Inglis.", "review_status": "unreviewed",
            "spans": [{"source_id": "c1", "span": "the median nerve passes through the carpal tunnel"}]}
REVIEW_ITEM = {"id": "a1b2c3d4e5f6", "type": "confirmed_factual", "status": "open", "lecture": "Lecture 16 - Posterior Thigh and Popliteal Fossa",
               "section": "Popliteal Fossa › Contents › Popliteal Artery", "original_text": "Continuation of femoral nerve past the adductor hiatus",
               "ai_note": "Fake note: this should say artery, not nerve.\nWhat the reference says: fake text.", "sources": [{**NOTES, "n": 1}, {**OPENSTAX, "n": 2}]}

A = TypeAdapter
EXAMPLES = {
    ("POST", "/api/auth/login"): (A(S.UserOut), {"user": {"id": "student1", "name": "Student One", "role": "student"}}),
    ("POST", "/api/auth/logout"): (A(S.Ok), {"ok": True}),
    ("GET", "/api/auth/me"): (A(S.MeOut), {"user": {"id": "inglis", "name": "Dr. Inglis", "role": "instructor"}, "preview": {"profile": "student1", "name": "Student One"}}),
    ("GET", "/api/scope"): (A(S.ScopeOut), {"lectures": [{"id": "L09-the-hand", "title": "Lecture 09 - The Hand", "granted": True}],
                                            "guides": [{"id": "class-10", "class_number": 10, "title": "The Hand", "lecture_ids": ["L09-the-hand"], "granted": True}]}),
    ("GET", "/api/chats"): (A(list[S.ChatItem]), [{"id": "c0ffee", "title": "What are the boundaries of the femoral triangle?", "updated_at": T}]),
    ("POST", "/api/chats"): (A(S.ChatItem), {"id": "c0ffee", "title": "New chat", "updated_at": T}),
    ("GET", "/api/chats/{id}"): (A(S.ChatOut), {"id": "c0ffee", "title": "Femoral triangle", "messages": [USER_MSG, ANSWER]}),
    ("PATCH", "/api/chats/{id}"): (A(S.TitleOut), {"id": "c0ffee", "title": "Femoral triangle"}),
    ("DELETE", "/api/chats/{id}"): (A(S.Ok), {"ok": True}),
    ("POST", "/api/ask"): (A(S.Message), ASK_FOOTER),
    ("GET", "/api/ask/status/{id}"): (A(S.AskStatus), {"stage": "writing"}),
    ("POST", "/api/messages/{id}/flag"): (A(S.Ok), {"ok": True}),
    ("GET", "/api/guides"): (A(list[S.GuideItem]), [{"id": "class-10", "class_number": 10, "title": "The Hand", "region": "Upper limb", "station_count": 12, "granted": True}]),
    ("GET", "/api/guides/{id}/stations"): (A(list[S.Station]), [{"index": 0, "title": "Fake first words of the first step", "steps": ["Fake step one.", "Fake step two."],
                                                                 "slides": [3, 4], "image_only": False}]),
    ("POST", "/api/guides/{id}/stations/{index}/check"): (A(S.CheckOut), {"verdict": "partly", "feedback_markdown": "You named the carpal bones; the guide also asks for the thenar muscles.",
                                                                          "sources": [GUIDE]}),
    ("GET", "/api/lectures/{id}/stations"): (A(list[S.Station]), [{"index": 0, "title": "Fake station name", "steps": ["Fake line from the notes."], "slides": [], "image_only": False}]),
    ("POST", "/api/quiz/build"): (A(S.JobOut), {"job_id": "9f8e7d6c5b4a3210"}),
    ("GET", "/api/quiz/jobs/{id}"): (A(S.JobStatus), {"done": True, "have": 5, "requested": 5, "note": "new question accepted",
                                                      "result": {"status": "ready", "reason": "", "quiz_id": "q123456789ab", "have": 5, "requested": 5, "message": ""}}),
    ("GET", "/api/quiz/latest"): (A(S.LatestQuiz | None), {"id": "q123456789ab", "status": "open", "length": 5, "answered": 2}),
    ("POST", "/api/quiz/{id}/accept"): (A(S.Ok), {"ok": True}),
    ("DELETE", "/api/quiz/{id}"): (A(S.Ok), {"ok": True}),
    ("GET", "/api/quiz/{id}"): (A(S.OpenQuiz), {"quiz_id": "q123456789ab", "length": 5, "current": 1, "answered": 1, "questions": [ITEM] * 5, "selections": {"0": ["B"]}}),
    ("PUT", "/api/quiz/{id}/answers/{index}"): (A(S.AnsweredOut), {"ok": True, "answered": 2}),
    ("PUT", "/api/quiz/{id}/current"): (A(S.Ok), {"ok": True}),
    ("POST", "/api/quiz/{id}/submit"): (A(S.Results), {"quiz_id": "q123456789ab", "score": 4, "length": 5, "submitted": T, "questions": [RESULT_Q]}),
    ("GET", "/api/quiz/{id}/results"): (A(S.Results), {"quiz_id": "q123456789ab", "score": 4, "length": 5, "submitted": T, "questions": [RESULT_Q]}),
    ("GET", "/api/quiz/history"): (A(list[S.HistoryItem]), [{"id": "q123456789ab", "score": 4, "length": 5, "submitted": T, "title": "Femoral triangle", "web": False}]),
    ("DELETE", "/api/quiz/history/{id}"): (A(S.Ok), {"ok": True}),
    ("GET", "/api/guides/{id}/stations/{index}/body-tip"): (A(S.BodyTipOut), {"body_type": "more_fat", "lines": [{"text": "The guide has you clear the fat first, so expect more of it with this body type.", "general": False}, {"text": "General tip, not from your notes: structures may lie deeper.", "general": True}]}),
    ("GET", "/api/guide-history"): (A(list[S.GuideHistoryItem]), [{"id": "guide:class-17", "kind": "guide", "ref": "class-17", "title": "Class 17 · The Hip and Knee Joints", "station": 2, "count": 19, "updated_at": T, "body_type": "more_fat", "notice": None}]),
    ("PUT", "/api/guide-history"): (A(S.Ok), {"ok": True}),
    ("DELETE", "/api/guide-history/{id}"): (A(S.Ok), {"ok": True}),
    ("GET", "/api/admin/web-quizzes"): (A(S.WebQuizPage), {"items": [{"id": "q123456789ab", "student": "student1", "title": "Waldeyer's ring", "status": "submitted", "score": 3, "length": 5, "web_questions": 5, "sources": [{"title": "Web: Waldeyer's tonsillar ring (Wikipedia)", "url": "https://en.wikipedia.org/wiki/Waldeyer%27s_tonsillar_ring", "license": "CC BY-SA 4.0"}], "created_at": T}], "total": 1}),
    ("GET", "/api/admin/stats"): (A(S.StatsOut), {"questions_7d": 42, "flagged_open": 3, "web_answers_7d": 5,
                                                  "review_counts": {"confirmed_factual": 90, "doubtful": 32, "wording": 442, "typo": 169, "start_here": 14}}),
    ("GET", "/api/admin/review"): (A(S.ReviewList), {"items": [REVIEW_ITEM], "total": 733}),
    ("POST", "/api/admin/review/{id}"): (A(S.Ok), {"ok": True}),
    ("GET", "/api/admin/questions"): (A(S.QuestionList), {"items": [{"id": "5d41402abc", "student": "student1", "question": USER_MSG["markdown"], "kind": "answer", "web": False,
                                                                     "flagged": False, "created_at": T, "message": ANSWER}], "total": 1}),
    ("GET", "/api/admin/students"): (A(list[S.StudentItem]), [{"id": "student1", "name": "Student One", "username": "student1", "lecture_ids": ["L09-the-hand"], "guide_ids": ["class-10"]}]),
    ("PUT", "/api/admin/students/{id}/access"): (A(S.Ok), {"ok": True}),
    ("POST", "/api/admin/preview"): (A(S.Ok), {"ok": True}),
    ("POST", "/api/admin/preview/exit"): (A(S.Ok), {"ok": True}),
}


def build():
    out = {}
    for (method, path), (model, data) in EXAMPLES.items():
        model.validate_python(data)
        out[f"{method} {path}"] = data
    return out


if __name__ == "__main__":
    target = ROOT / "docs" / "api_examples.json"
    target.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {target} ({len(EXAMPLES)} examples)")
