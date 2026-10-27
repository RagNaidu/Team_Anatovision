# PROGRESS

## 2026-10-06: Task A (clean up + parse notes)
Done
- Deleted `data/processed/_tmp_junk`, `data/raw/notes_unzipped_tmp`, and the 8 `.~lock.*` files in `data/processed/text`. `data/raw/notes` and `.env` untouched.
- `.venv` (Python 3.12, miniforge; 3.11 not installed) and `requirements.txt` created, packages installed.
- `src/ingest/parse.py` -> `data/processed/sections.jsonl` (546 sections, 26 files). Run: `.venv/bin/python -m src.ingest.parse`.
  - Three layouts detected per file: bullets (pandoc export), outline (I./A./1./a.), script (slides).
  - Source text is not corrected; only whitespace is normalised.

Known limits (see the report shown to the user)
- (Fixed in A2.) The .txt copies lost Word heading levels; hierarchy now comes from the original .docx heading styles.
- (Fixed in A2.) Parent headings with no text now live in their children's `section_path`.
- ANA407 Class 28 file is named "Posterior Abdominal Wall" but its content is GI-tract histology and digestive organs. Flagged, not changed.
- Lecture numbers repeat across files (14 x2, 15 x2, 16 x4), so `lecture_id` = number + title slug.
- Lecture 14 (Anterior Triangle of the Neck) is a .doc with no heading styles; outline fallback gives 13 sections, max 1768 chars.

Next
- Review A2 parse output with the user.
- Then (not started): embeddings + hybrid index, QA mode.

## 2026-10-06: Task A2
- parse.py now reads Heading 1-4 + list levels from the original .docx (full ancestor `section_path`, `breadcrumb`, `text_clean`, long sections split <=2500 chars); the 8 .doc files use the outline fallback (no heading styles, LibreOffice not installed); `tests/test_parse.py` added (175 pass).

## 2026-10-06: Task B (open reference text)
- OpenStax A&P 2e CNXML downloaded to `data/raw/open_text/` (commit 5ae32b3, official GitHub repo); `src/ingest/openstax.py` -> `data/processed/openstax_sections.jsonl` (1,579 sections, 28 chapters, ~493k words, all 197 page URLs checked). **Licence is CC BY-NC-SA 4.0, not CC BY 4.0 as CLAUDE.md says**: needs a decision (NonCommercial + ShareAlike). See `data/raw/open_text/ATTRIBUTION.md`.

## 2026-10-06: Task C (fact-checker, first run only)
- `src/audit/factcheck.py` built (BM25 -> 3 OpenStax refs -> Claude JSON flags, cached in `data/processed/audit_cache/`); run on Lecture 16b only: 15 flags (both sanity targets caught, 1 clear false positive), $0.17 per pass. NOT run on other lectures (waiting for go-ahead; est. ~$8-10 for all 562 sections). Reports: `reports/factcheck_lecture-16b-middle-ear.{md,json}`. Not yet written to `data/flags.jsonl`.

## 2026-10-06: Task C2 (fact-check all lectures): INCOMPLETE, blocked on API credit
- Prompt v3 (accepted-standard-names rule) + factual verification pass + 3-section report built. Run stopped when the **Anthropic API credit balance ran out** during Lecture 12: 316 of 562 sections checked (13 lectures complete: ANA407, 01-11, 16b; Lecture 12 half), $4.71 spent, 410 flags in `reports/factcheck_all.md/.json` (marked INCOMPLETE). Verifier flaw found (2 of the top 10, Lecture 06 cubital fossa, are false positives marked 'confirmed'); verifier prompt changed to ver2, untested. **Next: top up API credit, rerun `.venv/bin/python -m src.audit.factcheck --all` (resumes from cache; est. ~$4-5 more).** `data/flags.jsonl` untouched.

## 2026-10-06: Task C3 (fact-check finished)
- Verifier ver2 tested on 10 known items (both cubital-fossa items -> wrong, 4 known errors -> confirmed), then `--all` resumed: **562/562 sections, 0 errors, $8.40 at list price ($3.89 billed this session)**. 733 items for review: 90 factual (confirmed), 474 worth a second look (incl. 32 doubtful), 169 typos; 13 dropped by the second check, 194 below confidence 0.6. Severity rule applied in code (high only for confirmed factual; 25 high). `reports/factcheck_all.md` has a 'Start here' list (14 of the 25 high items). All AI-generated and unreviewed; `data/flags.jsonl` still untouched. **Next: Dr. Inglis reviews the report; his answers go into `verified_fixes`.**

## 2026-10-06: Task D (Q&A mode CLI)
- Built `src/retrieval/index.py` (4,264 chunks, bge-small -> Chroma + BM25 table), `src/retrieval/search.py` (RRF + notes boost x1.25, not-found if best cosine < 0.68), `src/modes/qa.py` (Claude answers only from retrieved chunks; confirmed fact-check lines are masked + logged to `data/flags.jsonl`; notes-vs-OpenStax conflicts logged; one-short-OpenStax-quote guard). Run: `.venv/bin/python -m src.modes.qa`. `tests/test_search.py` added (196 pass overall). Test run saved in `reports/qa_test_output.txt`. **Known gap: fact-check items the verifier called only 'doubtful' (32, incl. the middle-ear 'internal carotid in the inferior wall' line) are NOT masked, so Q&A still states them as fact; decision needed.** Not built yet: GUIDE/QUIZ modes, web fallback.

## 2026-10-06: Task E1 (doubtful items, verified fixes, scope guard)
- Q&A now uses the 32 'doubtful' fact-check lines with '(flagged for review, see fact-check)' and logs `note_line_doubtful`. New `src/verified.py` (`list`, `resolve <n> --decision confirm_error|notes_correct|reword ... [--apply-all-same-quote]`, `unresolve <fix-id>`) writes `data/verified_fixes.jsonl`; a verified fix is the top-priority source for its line (cited '[Verified by <by>, <date>]', original wording never repeated; `notes_correct` stops flagging). Loop tested end to end with a TEST fix, then removed and reopened. Clinical-advice questions (treatment/diagnosis/dosing) are declined by a model-level scope rule. `tests/test_verified.py` added (212 tests pass). `data/flags.jsonl`: 10 open flags awaiting Dr. Inglis; `verified_fixes.jsonl` empty. Notes files untouched. Not supported yet: resolving notes-vs-OpenStax conflict flags.

## 2026-10-06: Task E2 (guide walkthrough, brief answers, citation fix)
- `src/modes/guide.py` (SAMPLE MODE): stations from a lecture's own order (top 2 heading levels; groups under 200 chars merged), one cached Claude card per station in `data/processed/guide_cache/` (strictly from the notes; fact-check masks/doubtful tags/verified fixes applied), body type first, earlier-stations check, never skip ahead, judge yes/partial/no, replies <= 6 lines. Lecture 09 = 22 stations; scripted run in `tests/scripts/guide_lecture09.txt`, transcript in `reports/guide_transcript_lecture09.txt`. Q&A now defaults to `--brief` (<= 5 lines, closing line; `--long` = old format). Verified-fix citations now show the recorded `by` (code corrects wrong names). `tests/test_guide.py`, `tests/test_brief.py` added (all tests pass). Not built: GUIDE for lectures other than Lecture 09 untested live, QUIZ, web fallback.

## 2026-10-06: Task F (demo prep)
- Guide: a consequence is shown only when the judge ties it to the specific mistake, else "The notes don't state a consequence for this. Ask your instructor."; text is cut only at word/sentence boundaries (a first-word bug in `clip` fixed). Q&A reloads fixes/flags every question (live resolve works in an open session). `reports/demo_runbook.md` written from a real end-to-end rehearsal of steps b-g (cost $0.054; state restored: `verified_fixes.jsonl` empty, flag #8 open). CLAUDE.md updated with Tasks C, D, E1, E2. 301 tests pass. Not touched: `data/raw/notes`, `.env`.

## 2026-10-07: Task G (Streamlit UI: student chat + professor dashboard)
- Run: `.venv/bin/streamlit run app/main.py` (see README.md). 394 tests pass, 9 skipped (301 old + 93 new: citations, service, access, auth, review, upload, guide web session, AppTest smoke tests).
- Stage 1: `src/service.py` (`ask()` returns structured result + REAL events), `src/citations.py` (chip parser, matching, highlight), `qa.answer_question` records events, `Searcher.search(allowed_lectures=...)`. Stage 2: `GuideSession` (step/state) + stepper UI. Stage 3: `src/review.py` + dashboard review queue and ledger (decisions call `verified.resolve`). Stage 4: `src/auth.py` (scrypt, roles, grants), login, per-role navigation, access enforced in the search. Stage 5: `src/notes_upload.py` (versioned upload, re-parse, incremental re-index, optional paid fact-check), usage log, settings, spending cap.
- Changed in existing code (all additive, CLI output unchanged): `search.py` (optional `allowed_lectures`), `qa.py` (EventLog, optional `events`/`allowed_lectures`, `texts_out`, extra keys in the returned dict), `guide.py` (`GuideSession`, `card_cache_path`, `count_cached`, structured `last` result, events), `verified.py` (wording/typo flag types are resolvable), `index.py` (`update_lecture`, `uploaded` field), `parse.py` (`orig=` argument, re-applies uploads), `qa` fact-check loaders read `src/reports.py` (merges per-file reports of uploaded lectures).
- Next: QUIZ mode, web fallback, weekly email digest, UB single sign-on, notes-vs-OpenStax conflict resolution.


## 2026-10-08: UI audit, Part 1 (student-safe views, answer logic, sessions)
- New `src/student_view.py` (student-safe projection; `leaks()` used by tests), `src/query.py` (follow-up rewrite, list questions, off-topic check). Changed: `service.py` (`ask_for_student`, 600-char limit, per-case not-covered messages, lecture-named access message), `qa.py` (student prompt variant, conversation context, list mode, `decline_reason`), `citations.py` (numbers per distinct passage + supporting line), `usage.py` (`kind` split), `auth.py` (10-char passwords + confirm, `ANATOVISION_DEMO`), all of `app/views/*`.
- Reload fix: NOT built (would need a bearer token + stored chats); sidebar warning + README "Known demo limits" instead.
- 455 tests pass, 9 skipped. `data/verified_fixes.jsonl` empty, `data/flags.jsonl` unchanged. Next: Part 2-4 of the audit (visual).

## 2026-10-08: UI audit, Part 2 (look, structure, accessibility)
- `app/theme.py` rewritten ("Vellum & Petrol": tokens once, one icon system, shared components); `app/contrast.py` (WCAG table, `python -m app.contrast`); `.streamlit/config.toml` matches the tokens. Guide is now its own page (/guide); mode switcher = real nav links; login card + fixed message slot; button rows instead of narrow columns; loading skeleton with a "taking longer" line; student asking /dashboard after sign-in lands on the instructors page.
- Root cause of the missing sidebar toggle: the old CSS hid Streamlit's whole toolbar, which contains the "open sidebar" button.
- Checked in Chrome at 1440/961/390 (screenshots in `reports/ui_screenshots/part2/`); browser audit clean on 36 screens. 528 tests pass, 9 skipped.

## 2026-10-18: UI audit, Part 3 (student chat and Guide)
- Chat: chips show passage number + short label, one supporting line per sentence is highlighted (indentation kept), Sources pane = "Used in this answer" cards (whole card clickable) + collapsed "Also looked at", trust line, "Report an error" (-> data/flags.jsonl as `student_report`, never shown back to students), non-blocking body-type card, scroll-to-question and a 480+ character counter (small script in theme.inject()).
- Guide: describe first, notes after (or "Show the notes", logged as `guide_peek`), form submit (one click), real station names + prev/next, locked stations explain themselves, success vs warning alerts, de-duplicated notes, no "no consequence" line.
- Tests now never write to the real question log/flags/settings (conftest.py). Browser run + screenshots: reports/ui_screenshots/part3/.

## 2026-10-19: keyword answers + trusted web, chat history, dissection guides
- Stage 1: bare-term lookup, trusted-web fallback (NLM MeSH + MedlinePlus; StatPearls is behind a reCAPTCHA), `src/web_sources.py` allowlist, professor web count. Stage 2: per-user SQLite chat history with 90-day retention, sidebar list, rename/delete, 50/200 limits, screenshots in `reports/ui_screenshots/part5/`. Stage 3: 27 dissection guides (518 slides) ingested, class-to-lecture map, procedural step answers, access follows the matched lecture.
- Live evaluation: `reports/live_eval_2026-10-19.md` (31 questions, judge gpt-oss-120b: 23 yes / 2 partly / 1 no). Tests: 713 pass, 9 skipped. `flags.jsonl`, `question_log.jsonl`, `users.json` and `verified_fixes.jsonl` unchanged (md5 checked).
- Next: Dr. Inglis approves the web sites and checks the guide map; QUIZ mode; fact-check of the guides; weekly email digest.

## 2026-10-20: Wikipedia web source, content-only guide map
- Wikipedia on by default and first in the web tier (`reports/web_wikipedia_check.md`: 6 web answers, judge 6 yes); guide map rebuilt by content (20 high / 3 medium / 4 unmatched), unmatched guides grantable one by one, `reports/title_content_mismatches.md`. 725 tests pass.
