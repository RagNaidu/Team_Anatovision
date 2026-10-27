# AnatoVision: Anatomy Lab AI (CDA 650, Phase 1)

## What we are building
An AI assistant for Dr. Stuart Inglis's anatomy lab (UB School of Medicine).
Students use it in the lab while dissecting, and also while studying.
It is grounded in Dr. Inglis's lecture notes. It never silently "corrects" his notes.

## Hard rules (never break these)
1. **Answers are always procedural.** Use this pattern:
   where you are -> steps you should have done -> what you should see now
   -> if done wrong: what goes wrong and why it matters clinically
   -> if done right: confirm -> next step.
   Never jump straight to the end result.
2. **Source priority:** Verified fixes (Dr. Inglis) > his lecture notes > open anatomy text > trusted web.
3. **Every answer cites its source** (lecture and section). Web answers are labelled "Not from course notes".
4. **Conflicts are flagged, never auto-fixed.** They go to a review queue, and Dr. Inglis decides.
5. **Ask the cadaver body type at the start** (fat / muscle / build) and adapt guidance to it.
6. Placeholder or sample data must be tagged `source_type: placeholder` so it can be swapped out later.

## Phase 1 architecture

### Part A: Prep (offline, re-run when notes change)
1. Ingest: Word notes (.doc and .docx) from `data/raw/notes/`. Convert .doc to .docx with LibreOffice.
2. Parse: split by headings and steps, keep the order (lecture > section > step).
3. Step map: an LLM extracts a JSON card per step (schema below), and a human reviews it.
4. Audit: check each factual claim against the open reference text, write `reports/audit_<date>.md`, and email it to Dr. Inglis.
5. Index: hybrid search (BM25 + embeddings) plus a `verified_fixes` table.

### Part B: Live (each message)
6. The session starts by asking the cadaver body type and the student's current lecture and step.
7. A router picks a mode: GUIDE (in lab, step-by-step) / QA (studying) / QUIZ (exam prep on lab steps).
8. Retrieve with hybrid search, rerank, then answer with citations in the procedural format.
9. Fallback: if nothing relevant is found, search the web (trusted domains only), compare 2-3 sources, and answer labelled "Not from course notes". This is the only agentic part.
10. If web sources and the notes disagree, add the item to `flags` and send Dr. Inglis a weekly email digest.
11. His reply is stored in `verified_fixes` and becomes the top-priority source.

## Step card schema
```json
{
  "lecture": "Lecture 09 - The Hand",
  "step_id": "L09-S04",
  "order": 4,
  "action": "what to do / where to cut",
  "prerequisites": ["L09-S03"],
  "expected_view": "what the student should see",
  "common_mistakes": ["..."],
  "consequence_if_wrong": "what goes wrong (clinical relevance)",
  "body_type_notes": "how fat / muscle / build changes it",
  "source": {"file": "...", "section": "..."},
  "source_type": "notes | open_text | placeholder | verified",
  "reviewed": false
}
```

## Tech stack (proposed)
- Python 3.11, FastAPI backend
- Parsing: python-docx; LibreOffice headless for .doc files
- Search: Qdrant (local) with hybrid dense + sparse search, or Chroma + rank_bm25; a cross-encoder reranker
- Embeddings: an API embedding model or bge-base (local)
- LLM: Claude API (key in `.env`)
- Web fallback: Tavily or Brave Search API, with a domain allowlist
- Email: SMTP (Gmail app password) for the weekly digest
- UI: Streamlit for the first demo, later a proper web app
- Eval: `eval/golden.jsonl` (Q&As from Dr. Inglis) plus pytest

## Folder layout
```
data/raw/notes/        Dr. Inglis's Word files (never edit these)
data/raw/open_text/    OpenStax A&P 2e (CC BY-NC-SA 4.0, verified) placeholder
data/processed/        parsed sections + step cards (JSON)
src/ingest/  src/stepmap/  src/audit/  src/retrieval/  src/modes/  src/fallback/  src/api/
reports/               audit reports
eval/                  golden test set
```

## Status
- Notes received: Lecture 08-22 (lower limb, head & neck). Procedural dissection notes still to come.
- Lab text: Grant's Atlas is copyrighted, so we are waiting on an open-source alternative from Dr. Inglis. Use OpenStax as a placeholder.
- Build order: ingest -> QA mode -> step map + GUIDE -> QUIZ -> fallback + flags -> UI.

---

## UPDATE 2026-10-06 (this section overrides anything above that conflicts)

- **LLM:** Claude, key is `ANTHROPIC_API_KEY` in `.env`. Never print, log, echo or commit the contents of `.env`.
- **Model:** read from env var `LLM_MODEL` (default `claude-sonnet-5-5`).
- **Embeddings:** local `BAAI/bge-small-en-v1.5` via sentence-transformers (no second API key).
- **Notes:** 26 files (Lecture 01-22 plus ANA407 Class 28) in `data/raw/notes/` (originals, NEVER edit). Plain text copies are in `data/processed/text/`.
- **Ground truth for now:** Dr. Inglis's notes (`source_type: notes`, priority 2) + OpenStax Anatomy & Physiology 2e (`source_type: open_text`, priority 3, placeholder, licence is CC BY-NC-SA 4.0 (verified 2026-10-06): non-commercial only, adaptations stay under the same licence, always credit OpenStax and keep quoted passages short).
- **The notes are descriptive, not step-by-step dissection.** Guide mode waits for his procedural notes. Do not invent procedure steps.
- **No Streamlit yet.** Build a CLI first. UI decision (Streamlit vs website) comes later.
- **Flag only.** Conflicts and suspected errors are never auto-fixed. Log them to `data/flags.jsonl`.
- **Never invent** clinical consequences or citations. Use only what the sources state, otherwise say so.
- Keep a short running log in `PROGRESS.md` (what was done, what is next).
- Do not touch `data/raw/notes/` or `.env`.

---

## UPDATE 2026-10-06 (later): what is built so far (Tasks A to F). This overrides the "Status" and build-order lines above.

Run everything from the repo root with `.venv/bin/python -m ...`. Tests: `.venv/bin/python -m pytest -q` (301 pass, 9 skipped by design).
Never edit `data/raw/notes/`; never print `.env`. Everything an AI produced about the notes is **unreviewed** until Dr. Inglis decides.
New data: `data/flags.jsonl` (review queue), `data/verified_fixes.jsonl` (his decisions), `data/index/` (search index),
`data/processed/audit_cache/` and `guide_cache/` (cached model calls), `reports/` (fact-check, runbook, transcripts).

**Prep (Tasks A, A2, B).** `src/ingest/parse.py` builds `data/processed/sections.jsonl` (562 sections from the originals: heading levels from the .docx,
outline numbering for the 8 .doc files; fields incl. `section_path`, `breadcrumb`, `text`, `text_clean`; LibreOffice is not installed).
`src/ingest/openstax.py` builds `data/processed/openstax_sections.jsonl` (1,579 sections; licence CC BY-NC-SA 4.0, see `data/raw/open_text/ATTRIBUTION.md`).

**Task C: fact-checker** (`src/audit/factcheck.py`). Flag only; the notes are never rewritten. For each notes section it asks Claude to compare it with the
3 most relevant OpenStax sections (BM25), then re-checks every factual flag in a separate "second check" call (confirmed / doubtful / wrong; "wrong" is dropped).
Guards: the quoted notes text must be verbatim, one short OpenStax sentence at most, citations only to the supplied references.
Commands: `-m src.audit.factcheck --lecture "Lecture 16b - Middle Ear"`, `--all` (resumes from `data/processed/audit_cache/`; about $8.40 in total, about $0.015/section), `--cache-only` (rebuild the report with no API calls).
Output: `reports/factcheck_all.md/.json`: a "Start here" list (14 of 25 confirmed high items), then likely factual / second look / typos. Result: 562 sections, 733 items (90 confirmed factual, 32 doubtful factual, 442 wording, 169 typos; 83% are wording/typo).
Limits: AI-generated and unreviewed; the second check can be wrong (it first confirmed two false positives; prompt fixed, tested on 10 items only); 617 of 733 items rest on general anatomy knowledge, not OpenStax; it does not write to `flags.jsonl`.

**Task D: Q&A mode** (`src/retrieval/index.py`, `search.py`, `src/modes/qa.py`). Build the index once: `-m src.retrieval.index` (4,264 chunks, bge-small into Chroma plus BM25).
Hybrid search = RRF, notes boosted x1.25; "not found" if best cosine is under 0.68. Claude answers ONLY from the 5 retrieved chunks, with citations like `[Lecture 09 - The Hand > Nerves of the Hand > Median Nerve]`
or "OpenStax A&P 2e §14.1" (answers from OpenStax alone start with "From reference text (OpenStax), not course notes"). Asks the cadaver body type first; mentions it only where a source discusses variation.
Run: `-m src.modes.qa` (interactive) or `--ask "question"` (repeatable), `--body-type "..."`, `--brief` (default: at most 5 lines, ends "Ask for more detail if you need it.") or `--long` (five-part format).
Rules in code: fact-check lines CONFIRMED as errors are masked and the answer says "this line in the course notes is currently under review" plus a standard statement labelled "general anatomy knowledge, pending Dr. Inglis"
(logged as `note_line_under_review`); notes-vs-OpenStax conflicts are shown with both sides and logged; at most one short verbatim OpenStax sentence (one retry); clinical-advice questions (treatment, diagnosis, dosing) are declined.
Limits: the 0.68 threshold was calibrated on about a dozen queries (heart-attack question missed it by 0.01; the model-level scope rule is the safety net); the notes-vs-OpenStax conflict path has not been exercised live; no web fallback yet.

**Task E1: doubtful items and verified fixes** (`src/verified.py`). The 32 "doubtful" lines are used normally with "(flagged for review, see fact-check)" and logged as `note_line_doubtful`.
Dr. Inglis's replies: `-m src.verified list` (open flags, numbered by line in `flags.jsonl`), `-m src.verified resolve <n> --decision confirm_error|notes_correct|reword --correction "..." --by "Dr. Inglis" [--apply-all-same-quote]`,
`-m src.verified unresolve <fix-id>`. A verified fix is the TOP-priority source for its line (matched per lecture + breadcrumb + quote), cited `[Verified by <by>, <date>]` with the recorded name; the original wording is never repeated;
`notes_correct` stops all flagging/masking of that line. Q&A reloads fixes on every question, so a fix resolved in another terminal shows up in an open session.
Limits: notes-vs-OpenStax conflict flags cannot be resolved with a fix yet; no email digest yet; `data/verified_fixes.jsonl` is empty until he replies (only TEST/DEMO fixes were ever written, then removed).

**Tasks E2 and F: guide walkthrough** (`src/modes/guide.py`). SAMPLE MODE (banner at start): the notes are descriptive, so it walks a lecture's own order, not a dissection procedure, and never invents steps, cuts or consequences.
Stations = sections grouped by the top two heading levels (groups under 200 characters merge into a neighbour). One card per station is extracted once by Claude strictly from the notes (cached in `data/processed/guide_cache/`).
Session: body type, "Which station are you at?", check of the earlier stations (sent back to the first missing one; no skipping ahead), what you should see, the student describes it, Claude judges yes/partial/no.
On partial/no it shows what the notes say; a consequence is shown only if the judge ties it to the specific mistake, otherwise exactly: "The notes don't state a consequence for this. Ask your instructor." Replies are at most 6 lines; text is cut only at word or sentence boundaries.
Same fact-check/doubtful/verified-fix handling as Q&A. Run: `-m src.modes.guide --lecture "Lecture 09" [--body-type "..."] [--script file]` (scripted run for tests: `tests/scripts/guide_lecture09.txt`, `guide_demo.txt`).
Limits: tried live only on Lecture 09 (22 stations); judge verdicts are AI opinions; the first run on a lecture costs about $0.17 for cards.

**Demo:** `reports/demo_runbook.md` has the exact commands, what to say, and real captured outputs for the 10-minute demo.
**Not built yet:** QUIZ mode, web fallback, weekly email digest, UI, procedural dissection steps (waiting on Dr. Inglis's notes), resolving conflict flags, guide mode for other lectures.

---

## UPDATE 2026-10-07: Task G, the web UI (this overrides "No Streamlit yet" above)

**Run:** `.venv/bin/streamlit run app/main.py` (README.md has accounts, env vars, first-run behaviour). Tests: `.venv/bin/python -m pytest -q` (394 pass, 9 skipped).
The UI is a thin layer: `app/` (Streamlit views, theme, nav) over `src/service.py` (`ask()`), `GuideSession` in `src/modes/guide.py`, `src/review.py`, `src/auth.py`, `src/notes_upload.py`, `src/citations.py`, `src/usage.py`, `src/reports.py`. The CLI is unchanged.
Design rules: white page, ink #1B1B1F, hairline rules, Newsreader + Inter; status colours only for meaning (oxblood = under review, amber = flagged/doubtful, green = verified by Dr. Inglis); no emoji, no default Streamlit alerts (use `theme.notice`).

**Built:**
- Student: Q&A with numbered citation chips (each matched to a retrieved chunk; an unmatched citation shows red "citation not found in retrieved sources"), Sources pane (passage, breadcrumb, badge, score, highlighted sentence, OpenStax credit read from ATTRIBUTION.md), status chips (under review / flagged / Verified by), "How this answer was built" timeline of REAL recorded events (`qa.EventLog`; never reconstructed), not-covered card without unrelated chunks, Guide with stepper (done/current/locked) and plain-words verdicts, body type asked first, session cost + model in the footer, per-session spending cap (default $2, `data/settings.json`).
- Professor (separate page, role-checked): review queue from `reports/factcheck_all.json` (Start here 14, Likely factual 90, Second look 474, Typos 169; filters), Confirm error / Notes are correct / Reword via `verified.resolve`, ledger with Undo, notes library + versioned upload (never touches `data/raw/notes`; saved in `data/raw/notes_uploaded/`, re-parse and incremental re-index of that lecture only, "uploaded <date>" badge), optional fact-check of an uploaded file after a cost confirmation (about $0.015/section), access grants per file, usage (`data/question_log.jsonl`), settings, "View as student" (preview as a chosen student, always audience = student).
- Access control: `data/users.json` (git-ignored, salted scrypt). The grant is enforced in `Searcher.search(allowed_lectures=...)`, before anything reaches the model; students see no fact-check detail (verifier reasons, original wording, severity); OpenStax stays open to all, labelled not course notes. A student outside their lectures gets "That isn't in the notes you have access to. Ask your instructor."

**Limits:** demo-grade login on one machine (no HTTPS, in-memory lockout, no session expiry); real use needs UB single sign-on. Quiz is shown but disabled. `.doc` uploads need LibreOffice (not installed): save as .docx. The right pane shows one answer at a time. A chip's status link is "all flagged lines of that kind in the answer", not per sentence. The access-limited message can also appear when the model declines an OpenStax-only answer. The model sometimes adds extra "general anatomy knowledge" lines next to an under-review line (existing Q&A behaviour, not changed). Streamlit does not reload `src/` on edit: restart the server after changing it. Student questions are stored with usernames in `data/question_log.jsonl`.


**UI audit fix rounds (2026-10-08 to 2026-10-18).** Four rounds changed the web UI without changing the pipeline. Part 1: students get only a separate student-safe view
(`src/student_view.py`; no fact-check text, scores, cost or model), follow-up questions use the last turns, list questions retrieve 12 passages, distinct
"not covered" messages, 600-character limit, 10-character passwords, usage split by kind. Part 2: one design system in `app/theme.py` (tokens, icons, components, contrast
table in `app/contrast.py`), Guide became `/guide`, sidebar toggle fixed. Part 3: chips with labels and one highlighted supporting line, Sources pane with
"Used in this answer", trust line, student error reports (`student_report` flags), Guide describe-first with a logged "Show the notes". Part 4: a calmer review queue
(details collapsed, typo-only bulk action, Ctrl+Enter can never decide), ledger before/after with a confirmation on Undo, a "Student reports" tab, preview bar,
phone/tablet bottom sheet, and a withheld line now shows only the neutral sentence. Tests: 579 pass, 9 skipped; none of them write to real data files (`conftest.py`).


## UPDATE 2026-10-19: BullsAI is the provider
- **LLM:** BullsAI (UB's OpenAI-compatible gateway) through the `openai` package; every model call goes through `src/llm.py` (`complete`, `complete_json`: fences and `<think>` text stripped, one retry on bad JSON, then a clear `LLMError`). **No Anthropic key is needed.** This overrides the earlier "Claude / ANTHROPIC_API_KEY / LLM_MODEL" lines.
- **Env (`.env`, never printed):** `LLM_PROVIDER` (default `bullsai`), `BULLSAI_API_KEY`, `BULLSAI_BASE_URL`, `BULLSAI_MODEL`, optional `BULLSAI_REWRITE_MODEL` (helper model, defaults to `BULLSAI_MODEL`).
- **Cost:** BullsAI has no known price, so cost is not tracked ("course key, cost not tracked", professor screens only). Per-model prices live in `PRICES` in `src/llm.py`; a model not listed there costs 0. The per-session spending cap therefore never triggers on BullsAI.
- Fact-check cache keys include the model, so the old Claude results in `data/processed/audit_cache/` are not reused by a BullsAI run.


## UPDATE 2026-10-19 (later): term lookup, web fallback, chat history, dissection guides

Source order is now **verified fixes > notes + dissection guides (same tier, priority 2) > OpenStax > trusted web**. Tests: 713 pass, 9 skipped. Reports: `reports/live_eval_2026-10-19.md`, `reports/dissection_guides_inventory.md`, `reports/build_status.md`.

- **Term lookup** (`src/term_lookup.py`, `Searcher.keyword_groups`). A bare term (4 or fewer meaningful words, in the form of a term, not a question) that appears word-for-word in text the user may open gets "<Term> appears in:" and one line per section (max 6, different lectures first, notes/guides before OpenStax), ending "Ask about a specific one for more detail." Only when the term appears in 2+ places of the course material; one place or a term that is a section heading keeps the ordinary answer (and falls back to the term lookup if that finds nothing); no match anywhere keeps the refusal. The 0.68 rule is unchanged for full questions.
- **Web fallback** (`src/web_sources.py` = the allowlist, `src/web_fallback.py`, `WEB_FALLBACK=on|off`, default on). Last tier, only when notes/guides/OpenStax found nothing, no access reason, and `query.scope_check` says ANATOMY with certainty (never clinical advice or off-topic). Allowed: NLM MeSH via NCBI E-utilities, MedlinePlus; Wikipedia off unless `WEB_ALLOW_WIKIPEDIA=on`; Tavily (domains restricted) only with a key. StatPearls pages are behind a reCAPTCHA and E-utilities return only titles for them, so they are not used. 3 passages x 1,500 characters, 6 s, 7-day cache in `data/web_cache/`; any failure = ordinary "not covered". Answer model mode "web" (`qa.WEB_SYSTEM`): only the fetched text; unsupported answer = "not covered". Student label "From the web, not in Dr. Inglis's notes or OpenStax. Check with your instructor." Logged with `web: true` and `web_urls`; professor Usage tab has a Web-sourced answers count and filter; student reports carry the URLs.
- **Chat history** (`src/chat_store.py`, SQLite `data/chats.db`, git-ignored). Q&A only, per user (every query matches the user in SQL), stores the student-safe view of each answer (never raw text), title = first question cut at a word. Sidebar: New chat, list grouped Today/Yesterday/Previous 7 days/Older, reopen without a model call, rename/delete dialogs. 50 chats/user, 200 messages/chat, `CHAT_RETENTION_DAYS` (90) purge at app start and login. A professor previewing saves nothing. Follow-up context uses only the open chat. `data/question_log.jsonl` is separate and unchanged.
- **Dissection guides** (`src/ingest/guides.py`, `scripts/guides_build.py`, `data/raw/dissection_guides/` git-ignored, originals never modified). 27 .pptx, 518 slides, 29 image-only (not read; no vision step run), no speaker notes, no slide titles; footer, page number and figure letters are dropped; one chunk per slide, short slides merged into the one before; 373 chunks, `source_type: dissection_guide`, cited "Dissection Guide, Class 17, slide 12". Class-to-lecture map `data/dissection_guides_map.json` (title similarity + tf-idf content overlap, never class number = lecture number; editable, `"locked": true` keeps a hand edit): 19 high, 2 medium, 3 low, 3 unmatched (Class 25 Pleural Cavities and Lungs, Class 26 Mediastinum and Heart, Class 33 The Orbit). Access: a guide follows its matched lecture's grant (two lectures: either); unmatched = instructors and full-access students only. Procedural ("how do I ...") questions retrieve 8 passages and answer as ordered steps with slide citations. Guides are **not fact-checked** (the instructor Notes library says so). Rebuild: `scripts/guides_build.py` then `python -m src.retrieval.index`.
- **Test hygiene:** `conftest.py` now also isolates `data/chats.db` and `data/web_cache/` and sets WEB_FALLBACK=off; a test that builds a student answer must do it inside a test (not at import), or it writes the real question log. Live scripts: `scripts/live_ask.py`, `scripts/live_eval.py` (no-logging sandbox), `scripts/sandbox_main.py` (the app on a throw-away data folder).
- **Known gaps:** web answers are thin (MeSH gives 1-3 sentences); a follow-up can miss its slide (Class 14 slide 7 case); OpenStax-only answers for a student whose notes are closed can be tangential; Class 2, 4 and 28 matches are low-confidence; the ANA407 Class 28 notes file is titled Posterior Abdominal Wall but holds the digestive tract.

## UPDATE 2026-10-20: Wikipedia approved, guide map by content only
- **Wikipedia** (en.wikipedia.org, MediaWiki API) is an approved web source, on by default (`WEB_ALLOW_WIKIPEDIA=off` disables), asked FIRST in the web tier; MeSH/MedlinePlus supplement it. Search "<keywords> anatomy", reject disambiguation, people and non-anatomy pages, keep each page's intro (best page also its most relevant section), 1,500 characters, 3 pages, same 6 s / 7-day cache / silent fallback. Generic User-Agent "AnatoVision/1.0 (UB CDA 650 course project)", no personal data. Wikimedia answers 429 to bursts, so calls are spaced 0.7 s and retried once. Label "From Wikipedia, not in Dr. Inglis's notes or OpenStax. Check with your instructor." (generic web label when only MeSH/MedlinePlus text was used); Sources tab shows title, link, date, "Wikipedia, CC BY-SA 4.0". Check: `reports/web_wikipedia_check.md`.
- **Guide map by content only** (`src/ingest/guide_map.py`, `scripts/guides_build.py`; `--title-map` keeps the old method). 20 high, 3 medium, 4 unmatched (Class 25, 26, 28, 33 The Orbit). Class 28 (Posterior Abdominal Wall) is unmatched: the ANA407 Class 28 notes file holds the digestive tract and only Class 27 points at it. An unmatched guide's chunks carry the lecture label "Dissection Guide, Class N", which the Access screen lists as a grantable item. Title/content mismatches for Dr. Inglis: `reports/title_content_mismatches.md`.

## UPDATE 2026-10-20 (later): answer redesign (answer first, markers, Sources list)
- **Layout.** The model writes markdown (opening sentence, bold lead-ins, merged bullets, numbered steps) with `[cite]` text after paragraphs/bullets; validation, repair/drop, verbatim limits and access rules are unchanged and work on those cites. `src/student_view.py` turns them into `blocks` (one per line of the answer) with source numbers: a run of consecutive blocks citing the same sources shows the marker on the last block only; `sources_list` (label, link), `footer` ("Based on OpenStax and Wikipedia, not Dr. Inglis's notes." only when no notes/guide/verified material was used) and `notice` (short access line "Dr. Inglis's notes for this are in Lecture 08, which you don't have yet. Ask him to open it."). No banner or label above an answer; refusal/"not covered" keep their box. The closing line "Ask for more detail..." is validated but not shown. Brief = up to 8 lines.
- **Click-through.** Markers are `<a class="cite" data-cite="msg_unit_n">`; a page script (theme.A11Y_JS) presses the hidden Streamlit button `chip_<msg>_<unit>_<n>` (inside `cites_<msg>`, display:none), whose callback `pane.select` opens that source in the right panel and switches the panel to the Sources tab. Notes/guide lines of the Sources list use the same mechanism; OpenStax/Wikipedia lines are real links.
- **Links.** OpenStax entries link to the section page only if the URL is in `data/processed/openstax_url_check.json` (written by `scripts/verify_openstax_urls.py`; all 197 verified), else to the book's contents page. Wikipedia entries link to the page; the licence line ("Wikipedia, CC BY-SA 4.0") is in the side-panel entry.
- **Coverage check** (`query.coverage_check`, `service.ask` `pre_answer`): when the retrieved text is OpenStax only (no notes/guide/term/steps) and the web is on, Gemma says whether it answers every part; missing parts trigger a Wikipedia-only fetch (`web_fallback.lookup(sources=("wikipedia",), loose=True)`), both are given to the model with a `<coverage_gaps>` note; if Wikipedia is empty or throttled the model says one plain gap sentence. OpenStax Key Terms / Review / Interactive Link / Critical Thinking passages are dropped when a body passage exists (`search.drop_exercises`).
- Wikipedia page text now keeps the intro plus up to two best-matching sections. Evaluation: `reports/live_eval_2026-10-20_redesign.md`. Screenshots: `reports/ui_screenshots/part6/`.

## UPDATE 2026-10-20 (later still): Guide on the dissection guides
- `src/modes/guide_slides.py`: `build_stations(slides, class_label)` (slide order; same real title merges; title/end/empty slides skipped; image-only slide = station "See slide N in your lab guide"; no slide has a title, so a station is named by its first words), `SlideGuideSession` (free goto/next/back, `assess(text)` judged by gemma against the station text only: yes/partial/no + one short feedback). UI in `app/views/guide_ui.py` (source radio: "Dissection guide" default, "Lecture notes (sample)" = the old engine in `guide.py`, unchanged; the sample note shows only there). Student-safe projections `sv.slide_guide_state/turn`.
- Access: `guides.accessible_guides(allowed)`; every guide can be granted as "Dissection Guide, Class N" (Access screen lists all 27; "Grant all" gives everything). Chunks carry `guide` metadata so Q&A search follows a guide grant too. Live check: `reports/guide_slides_check.md`.

## UPDATE 2026-10-20 (last): conversational Guide, correctness fixes, demo access
- **Guide is a conversation** on one dissection guide: `src/modes/guide_chat.py` (explicit JSON state: position, reported-done, missing/unsure, visited, steps already asked about, pending question, history; the model only interprets a message into validated JSON and writes a short reply from the supplied slide text; the app alone moves position, marks things done and checks access), `src/guide_service.py` (open/restore a guide's own session, access re-checked), `src/guide_store.py` (per-user SQLite `data/guide_sessions.db`, student-safe fields only, same retention as chats; a professor preview saves nothing). UI: `app/views/guide_ui.py` (picker, sticky header, chat, outline, source markers, Start/Continue/Back/Show guide passage, explicit Change guide / Start over). The old slide-by-slide judge UI is gone; the lecture-notes sample walkthrough stays. A failed turn keeps the last valid state and shows Try again.
- Every instruction of a guide is kept: `build_steps` paginates a long slide into parts (s13.1, s13.2) with their slide number; nothing is sliced (MAX_STEPS removed from `guide_slides`).
- Retrieval fix: Chroma `get()` does not return rows in request order; `embeddings_by_id()` pairs vectors with returned ids. `Searcher.outside_titles()` is a local, title-only check (no reranker or model) used for the "notes exist outside your access" message.
- Demo access (intentional): student1 and student2 were granted all lectures + all 27 guide labels through `auth.set_allowed_lectures`. Other accounts are unchanged.
- Guide limits: lecture notes are not used inside Guide (a question the slides do not answer goes to the instructor or Ask the lab); image-only slides are never judged; the app cannot see a dissection; a recap question can bundle up to 3 earlier slides. Tests: 815 pass, 9 skipped (see reports/build_status.md). Live check: `reports/guide_chat_eval_2026-10-20.md`.

## UPDATE 2026-10-20 (Quiz)
- **Quiz is on** (`/quiz`): `src/quiz/` (`items.py` schema + NBME-style local checks + span validation + freezing, `evidence.py` access/withheld-line/tier rules and the Wikipedia-first gap fill, `generate.py` draft -> local check -> freeze -> Gemma blind solve -> gpt-oss-120b blind solve -> gpt-oss-120b audit, `store.py` SQLite `data/quizzes.db`, `service.py`), `app/views/quiz_ui.py`, `app/views/quiz_review.py` (professor tab).
- Rules: exactly 5 or 10 questions (default 5), never padded; a 10 request with only 5 passing is an explicit offer. Keys/explanations/evidence are read only by `service.results` after `submit`. `reports/quiz_item_writing_checklist.md` cites the NBME manual by PDF page; the PDF stays unmodified and out of the index. AI agreement is labelled "AI-checked, not reviewed by Dr. Inglis"; only a professor's Approve changes that. verified_fixes.jsonl is still empty.
- Limits: item analysis (difficulty/discrimination) is not done; no difficulty is claimed; all-model checks can agree and still be wrong; a typed topic only uses passages that contain the topic's words; Wikipedia yields at most 3 short passages, so thin topics fail honestly.

## UPDATE 2026-10-20 (Quiz speed and reliability)
- `src/quiz/service.new_quiz` now reuses saved items first (`eligible_items`: same `QUIZ_VERSION`, not rejected / approved-only strict, grants, every cited passage text unchanged against the CURRENT usable text, in scope, no web evidence, no same-fact duplicates) and generates only the missing number. Partial results stay saved; the UI's "Continue preparing" re-runs the same request (bounded: at most 3 drafts per missing question). A quiz is created only with all 5/10; status values: ready | offer | partial | failed with a `reason` (insufficient_evidence | rejected | gateway).
- Generation: focused evidence bundles (`evidence.candidates`: primary passage + related comparison passages, distinct objectives by MMR), one global limit of 4 model calls in flight (`generate.LLM_SLOTS`), no waves (candidates are handled as they finish, started only while they can still fill the quiz), the two blinded solves run together, the audit also checks that options are comparable, absence-based "why wrong" reasons are rejected, outline-path spans are accepted only if they follow the notes' hierarchy.
- Measured, not promised: see `reports/quiz_speed_reliability_2026-10-20.md`.
