# Build status

Updated 2026-10-19.

- Stage 1 (keyword answers + trusted-web fallback): **done** (code, 37 mocked tests, live checks; full suite 660 pass). README/CLAUDE.md text comes in the final step.
- Stage 2 (chat history): **done** (SQLite store, sidebar list, rename/delete dialogs, 90-day purge, limits; 21 tests; screenshots in `reports/ui_screenshots/part5/` checked at 1440 and 390 px). Full suite 681 pass.
- Stage 3 (dissection guides): **done** (27 guides, 518 slides, 373 chunks in the index, class map, access, procedural answers; 32 new tests; inventory in `reports/dissection_guides_inventory.md`). Full suite 713 pass. Vision reading of image-only slides skipped: only 29 of 518 slides (5.6%) are image-only.
- Final checks: live evaluation + judge **done** (`reports/live_eval_2026-10-19.md`); README/CLAUDE.md/PROGRESS **done**; app restarted in the background at http://localhost:8501 (login page checked).

Notes: StatPearls pages cannot be fetched by script (reCAPTCHA; E-utilities return only titles), so the keyless NCBI source is NLM MeSH definitions.

**All three stages and the final checks are done.** Blocked / not done: StatPearls text (reCAPTCHA); vision reading of image-only slides (only 29 of 518, skipped by your rule). Full suite: 713 passed, 9 skipped. `flags.jsonl`, `question_log.jsonl`, `users.json` md5 unchanged; `verified_fixes.jsonl` empty.

## 2026-10-20 update
- Wikipedia web source: **done** (default on, first in the web tier, 8 new mocked tests, live check in `reports/web_wikipedia_check.md`).
- Guide map by content only: **done** (20 high, 3 medium, 4 unmatched; indexes rebuilt; unmatched guides grantable in the Access screen; `reports/title_content_mismatches.md`). Full suite: 725 passed, 9 skipped.
- Blocked: nothing. Caveat: Wikimedia returns HTTP 429 to bursts from a generic User-Agent; the tier then silently uses MeSH/MedlinePlus.

## 2026-10-20 (later): answer redesign
- **Done.** Answer first with merged markdown, numbered markers at the end of blocks, compact Sources list (OpenStax links verified, Wikipedia links, notes/guides open in the panel), footer and access line, no banners; coverage check + Wikipedia fill for OpenStax-only answers; exercise sections dropped; click-through via page script + hidden buttons. 744 tests pass, 9 skipped. Live evaluation 24 yes / 2 partly / 0 no (before: 23 / 2 / 1). Screenshots in `reports/ui_screenshots/part6/`.
- **Not done / notes.** The "(flagged for review)" and "Being reviewed" buttons still sit under a block when a line is withheld. A real student's question (17:07 UTC, student1, femoral triangle) reached the real `question_log.jsonl` through the running app while I worked; it is real usage and was kept, so that file's md5 differs from the pre-task baseline by that one line.

## 2026-10-20 (guide on dissection guides)
- **Done.** Guide mode now walks the dissection guides: source picker (Dissection guide by default, "Lecture notes (sample)" second, the sample note only there), stations from slides in order (consecutive same-title slides merge, title/end slides skipped, image-only slides say "See slide N in your lab guide"), numbered steps from the slide text, description judged yes/partly/no against the station text, free Back / Next / jump, "Source: Dissection Guide, Class N, slide M" line at the end, no banners. All 27 guides are grantable items in the Access screen (matched or not); a guide opens for its matched lecture's grant, its own grant, or full access; Q&A search follows the same grants. 764 tests pass, 9 skipped. Live check: `reports/guide_slides_check.md` (18 judgments, judge 15 yes / 3 partly / 0 no, the 3 "partly" are evaluative remarks about the student's description). Screenshots: `reports/ui_screenshots/part7/`.
- **Incident, fixed.** A scripting slip overwrote `src/retrieval/search.py` with a copy of `index.py`; there is no git, so I rebuilt it from the versions seen earlier in this session. All 744 tests that existed before this task passed again, but treat that file as reconstructed (a copy is in the scratchpad).
- **Not done.** Demo grants were not written (no direct edit of users.json): Dashboard > Access > open Student One > "Grant all" > "Yes, grant all" (same for Student Two).

## 2026-10-20 (conversational Guide task) — running log
- Backup of src/app/tests/conftest/requirements/README/CLAUDE.md before edits: `reports/backup_2026-10-20_guide/` (no secrets, no runtime data).
- Stage 1.1 **done**: `embeddings_by_id()` in `src/retrieval/search.py` pairs vectors with the ids Chroma returns (also fixed in `index.py` incremental re-index); 4 shuffled-row regression tests.
- Stage 1.3 **done**: `Searcher.outside_titles()` (local, titles only, no reranker/model) replaces the unfiltered search in `service.ask`; event text corrected; 2 tests (reranker/model inputs recorded).
- Stage 1.4 **done** (intentional change): `data/users.json` — student1 and student2 each granted all 26 lectures + 27 guide labels through `auth.set_allowed_lectures` (same call as the Access screen). Passwords/roles/names untouched (checked). md5 before 6cc9ad7a… after 71e8ab37….
- Stage 1.2 / 2 / 3 / 4: in progress.
- Stage 1.2 **done**: `guide_slides.build_stations` no longer slices (MAX_STEPS removed); the new engine `src/modes/guide_chat.build_steps` keeps every instruction line of every slide (words compared slide by slide over all 27 guides: 0 mismatches over 486 instruction slides), paginating long slides into parts (s13.1, s13.2) that keep their slide number.
- Stage 2 **built**: `src/modes/guide_chat.py` (explicit state, interpreter + writer, validation, templates), `src/guide_store.py` (per-user SQLite, student-safe), `src/guide_service.py`; 37 engine tests.
- Stage 3 **built**: chat UI in `app/views/guide_ui.py` + `GUIDE_CSS` in `app/theme.py`; 10 AppTest tests. Still to do: full suite, screenshots at 1440/390, live evaluation, README/CLAUDE.md, restart.
- **All stages done (2026-10-20).** Full suite 815 passed, 9 skipped. Live evaluation + judge: `reports/guide_chat_eval_2026-10-20.md`; report: `reports/guide_conversation_report_2026-10-20.md`; screenshots `reports/ui_screenshots/part8/` (1440 and 390 px). Protected files: flags.jsonl, question_log.jsonl, chats.db, verified_fixes.jsonl md5 unchanged; users.json changed ONLY by the demo grants (6cc9ad7a... -> 71e8ab37...). App restarted at http://127.0.0.1:8501.

## 2026-10-20 (Guide repair)
- **Done.** (1) Location text now comes from saved state: the model may not say where the student is (validator rejects any "you are/still/now on|at slide N" that differs from the saved slide); side-question and describe replies get an app-written "You're still on slide N." line; cited slides are separate from the position. (2) The app owns the closing question and records what was asked (`asked`: begin_task / report_back / confirm_done / continue): "yes" to "ready to start this step?" presents the step's actions and never advances; a bare "yes" to "tell me when finished" asks for confirmation; only "done"/a confirmed yes records completion, and only "next"/"yes" to "say next" moves on. (3) Earlier-work checks are asked one step at a time (`pending.recap.i`); each yes confirms only that step; a side question re-states the open question; after "I finished slide N" the position stays at N until the recap is done.
- Full suite 829 passed, 9 skipped. Isolated live check (Class 14, Class 17, 26 turns, `reports/guide_chat_repair_check_2026-10-20.md`): 0 contradictions between header, reply wording and cited slides. Screenshots `reports/ui_screenshots/part8/08..10_repair_*` (1440 and 390 px).

## 2026-10-20 (Quiz, first working version) — running log
- Backup before edits: `reports/backup_2026-10-20_quiz/`. NBME writing checklist (page-referenced): `reports/quiz_item_writing_checklist.md` (PDF unchanged, md5 same, not indexed).
- Built: `src/quiz/{items,evidence,generate,store,service}.py`, `app/views/quiz_ui.py`, `app/views/quiz_review.py` (professor tab "Quiz items"), Quiz enabled in nav (`/quiz`), `data/quizzes.db` (git-ignored, isolated in tests/sandbox). 880 tests pass so far; live checks and screenshots still to do.
- **Quiz done (2026-10-20).** Full suite 880 passed, 9 skipped (new: `tests/test_quiz.py`, `tests/test_quiz_ui.py`, `tests/quiz_fakes.py`; 13 existing UI tests adjusted for the enabled Quiz link / extra page). Live checks (isolated): `reports/quiz_live_check_2026-10-20.md`; screenshots `reports/ui_screenshots/part9/` (1440 and 390 px). Checklist: `reports/quiz_item_writing_checklist.md`. Protected files unchanged (flags, question_log, chats.db, users.json, guide_sessions.db md5 equal before/after this task; verified_fixes.jsonl empty; NBME PDF md5 unchanged). App restarted at http://127.0.0.1:8501.
- Known gaps: NBME checks are mechanical (option homogeneity is not enforced), pass rates vary run to run, Wikipedia gives at most 3 short passages, no item statistics, AI agreement is not proof.

## 2026-10-20 (Quiz speed and reliability)
- **Done.** Reuse of saved checked items, partial-success preservation with "Continue preparing", focused evidence bundles, comparable-options audit, absence-reason rejection, outline-path spans, one global call limit with no waves, honest progress and failure wording (insufficient evidence / rejected drafts / AI service). Measurements and inspection: `reports/quiz_speed_reliability_2026-10-20.md` (Lecture 02 cold 5: 88.8 s / 54 calls / 4 of 5 before, 52.7 s / 31 calls / 5 of 5 after; reuse 0 s, 0 calls). Screenshots `reports/ui_screenshots/part10/` (1440 and 390 px). Backup `reports/backup_2026-10-20_quiz_speed/`.
- Not done: a generator-side cache of rejected drafts, more question formats, instructor-set difficulty.
- Full suite 907 passed, 9 skipped; app restarted at http://127.0.0.1:8501.

## 2026-10-20 (all-lecture Quiz audit)
- Live run covered 22 of 26 lectures; BullsAI then answered HTTP 429 "budget exceeded (5.01 of 5.0)", so Lecture 17, 20, 21, 22 are Blocked, not checked. Fixes: heading path now part of notes passages (main cause of the Lecture 06 stall), outline spans of one entry accepted, one repair pass for mixed options, 10 s connect timeout + bounded probe + live failure progress + distinct quota/network/rejection messages. 914 tests pass. Report: `reports/quiz_all_lectures_2026-10-20.md` (+ `.json`). Screenshots `reports/ui_screenshots/part11/`.

## 2026-10-21 (Quiz on Claude)
- BullsAI's key hit its $5 cap, so the Quiz now runs on the Anthropic API: `QUIZ_LLM_PROVIDER=anthropic` in `.env` (Q&A and Guide still use BullsAI). Generator/solver `claude-sonnet-5-5`, independent verifier/auditor `claude-opus-5-5` (override with QUIZ_GEN_MODEL / QUIZ_VERIFIER_MODEL; set the provider to anything else to return to BullsAI). Structured output needed `additionalProperties:false` (fixed in `llm.strict_schema`). Runs now record tokens and an estimated cost. Isolated check, Lecture 06: 5 of 5 in 46.5 s (33 calls, est. $0.39); 10 of 10 extending it in 43.0 s (34 calls, est. $0.40). 914 tests pass.

## 2026-10-21 (everything on Claude)
- BullsAI's key is out of budget, so `.env` now has LLM_PROVIDER=anthropic (Q&A, Guide, helper calls, web coverage check, scope check) with LLM_MODEL=claude-sonnet-5-5 and REWRITE_MODEL=claude-haiku-5-5; the Quiz already used Claude. RERANK=off because the reranker is a BullsAI endpoint. Checked live: femoral-triangle Q&A answered (13.4 s, $0.021), a second Q&A (3.5 s, $0.015), Guide start/yes/side-question OK. 914 tests pass. To go back: set LLM_PROVIDER=bullsai and RERANK=on.
