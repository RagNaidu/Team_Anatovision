# AnatoVision

An AI assistant for Dr. Inglis's anatomy lab (UB School of Medicine, CDA 650). Students use it in the lab and while studying;
it answers from his lecture notes, cites the source of every line, and never silently "corrects" his notes. Full design and
status: [CLAUDE.md](CLAUDE.md). Progress log: [PROGRESS.md](PROGRESS.md).

## Run the web app

```
cd /Users/anirudhramesh_11/Desktop/anatovision
.venv/bin/streamlit run app/main.py
```

It opens in your browser (default http://localhost:8501). The first start takes about 10 seconds while the search index and the
embedding model load; after that every question is fast.

Uses BullsAI (UB's OpenAI-compatible gateway); no Anthropic key is needed. Put these in `.env` (never printed or committed):

```
LLM_PROVIDER=bullsai            # default; "anthropic" is an optional extra path (needs ANTHROPIC_API_KEY, LLM_MODEL)
BULLSAI_API_KEY=...
BULLSAI_BASE_URL=...            # the OpenAI-compatible /v1 URL
BULLSAI_MODEL=google/gemma-4-31B-it   # (also the code default) answers, Guide judge, fact-checker
BULLSAI_REWRITE_MODEL=...       # optional: follow-up rewrite and off-topic check (defaults to BULLSAI_MODEL)
RERANK=on                       # on (default) = BullsAI cross-encoder (BAAI/bge-reranker-v2-m3) reorders the top 25 passages; off = fusion order only
BULLSAI_THINKING=default        # default = leave the gateway's reasoning setting; off = send thinking disabled (the gateway ignored it on long prompts, so answers came back empty)
WEB_FALLBACK=on                 # on (default) | off: the trusted-web last tier, see "Source order" below
WEB_ALLOW_WIKIPEDIA=on          # on (default; approved by Dr. Inglis) | off: Wikipedia is asked first in the web tier
TAVILY_API_KEY=                 # optional: Tavily search restricted to the allowed domains
CHAT_RETENTION_DAYS=90          # chats with no activity for this long are deleted
```

All model calls go through `src/llm.py` (prices per model are in `PRICES` there). BullsAI has no known price, so the
professor screens say "course key, cost not tracked". Check the connection with `.venv/bin/python scripts/test_bullsai.py`.

### First run: accounts

On the first run the app creates `data/users.json` (git-ignored) with one professor and two sample students:

| account | role | password |
|---|---|---|
| `inglis` | professor | `DEMO_PROFESSOR_PASSWORD` if set, otherwise generated |
| `student1`, `student2` | student | `DEMO_STUDENT_PASSWORD` if set, otherwise generated |

If you do not set the variables, random passwords are generated and **printed once in the terminal that started the app**. They are
not written anywhere else (only salted scrypt hashes are stored). To choose your own:

```
DEMO_PROFESSOR_PASSWORD='...' DEMO_STUDENT_PASSWORD='...' .venv/bin/streamlit run app/main.py
```

Sample students start with access to **no** lectures. Sign in as the professor, open Dashboard > Access and tick the files each
student may use. To start over, delete `data/users.json`.

> **Demo-grade login on one machine, not production security.** Accounts live in a local file and the app trusts the process it
> runs in. What is enforced properly: passwords are hashed with a salt (scrypt) and must have at least 10 characters (typed twice
> when set); the professor pages check the role again inside every view; a student who opens the instructor path gets a "That page
> is for instructors" page; and a student's lecture access is enforced inside the search, so notes from lectures they may not use
> never reach the model. The login screen shows a demo notice while `ANATOVISION_DEMO` is on (the default); set
> `ANATOVISION_DEMO=0` to hide it. It is never shown after sign-in.

### Known demo limits

- **Reloading the browser signs you out.** This is deliberate for now. Streamlit keeps the session only in the open browser tab.
  Keeping people signed in across a reload would need a bearer token in the URL or a cookie, and without HTTPS or a session-expiry/
  revocation design that would weaken the login. Q&A chats are now saved on disk (see "Chat history"), so after signing in again a
  student reopens their chat from the sidebar list; the Guide is not saved. Real use needs UB single sign-on, which solves this properly.
- **Chat history is per user and kept 90 days.** The instructor question log (`data/question_log.jsonl`) is a separate file: deleting
  a chat does not remove the question from it. Chats are stored on this machine in `data/chats.db`, unencrypted, as the student-safe
  rendering of each answer.
- **Web fallback sends the question's keywords (not the username) to the National Library of Medicine** (NLM MeSH through NCBI E-utilities,
  and MedlinePlus). StatPearls pages cannot be read by a program (a reCAPTCHA blocks them, and E-utilities return only titles), so the
  keyless NCBI source is MeSH: short, authoritative definitions, not full articles. Web answers are thin by nature.
- **Dissection guides are not fact-checked.** They are Dr. Inglis's slides, indexed as they are; the professor Notes library marks them
  "not fact-checked yet". The class-to-lecture map is automatic (content only): four guides are unmatched and three are medium confidence (see
  `reports/dissection_guides_inventory.md`); lecture files whose title does not match their content are listed in `reports/title_content_mismatches.md`.
- Slides that are only a picture (29 of 518) have no readable text, so they cannot be found by search; the figure labels (A, B, C) on
  other slides are dropped.
- No HTTPS, no session expiry, lockout after 5 failed sign-ins is kept in memory only.
- Students cannot change their own password yet: the professor sets it (Dashboard > Access).
- Student questions are stored with usernames in `data/question_log.jsonl`. Each line has a `kind`: `chat_answer`, `guide_step`,
  `professor_preview` or `factcheck`. Professor previews are never counted as student usage.
- The question box is limited to 600 characters. Streamlit ignores a paste that is longer than the limit, so shorten it first.
- A student's screens get only the student-safe data built in `src/student_view.py` (no fact-check text, scores, cost or model
  name). A line the fact-check withheld is replaced by "Dr. Inglis is reviewing this line. Check with him before relying on it."
  and the AI's suggested replacement statement is no longer shown to students (the professor still sees it in the dashboard).

### Source order

Verified fix (Dr. Inglis) > **his lecture notes and his dissection guides (the same tier)** > OpenStax > trusted web.

- **Term lookup.** A bare term ("apex", "what is thenar?", "nerve supply") is not a full question, so it is not refused and not
  answered with "apex of what?". If it appears word-for-word (any plural form) in text the student may open, the answer lists the
  places it appears, grouped by section (up to 6, different lectures first, notes and guides before OpenStax), one line each with its
  citation, and ends "Ask about a specific one for more detail." A term that is the heading of one section ("sartorius") still gets the
  ordinary answer, and a term that appears nowhere ("amoxicillin") is still refused. The 0.68 relevance rule is unchanged for full questions.
- **Dissection guides.** The 27 PowerPoint guides are indexed one slide per chunk (very short consecutive slides are merged), cited as
  "Dissection Guide, Class 17, slide 12" (Class 33 has two guides, so its cites carry the title). A "how do I ..." question retrieves 8
  passages and is answered as ordered steps, one per line, each with its slide. Each guide is matched to a lecture **by content only**
  (file titles and class numbers are ignored: embeddings pick 3 candidates, gpt-oss-120b judges twice with the titles hidden, a conflict check
  settles two guides claiming one lecture): `data/dissection_guides_map.json`, with the evidence terms; a student may use a guide when they may use its lecture
  (a guide matched to two lectures opens for either); a guide matched to no lecture (Class 25, 26, 28 and The Orbit today) is listed in the Access screen as "Dissection Guide, Class N" and can be
  granted to a student on its own; otherwise only instructors and students who may open every lecture see it. To rebuild after the slides change: `.venv/bin/python -I scripts/guides_build.py` then `.venv/bin/python -m src.retrieval.index`.
- **Web fallback (`WEB_FALLBACK=on|off`, default on).** Asked only when the notes, guides and OpenStax found nothing, nobody's access is
  the reason, and the question is clearly about anatomy (never treatment, dosing or diagnosis, never off-topic: those are refused with no
  search). Allowed sites, listed in one file, `src/web_sources.py`: **Wikipedia** (en.wikipedia.org only, asked first: intro plus the most relevant
  section, disambiguation, people and non-anatomy pages rejected, credited "Wikipedia, CC BY-SA 4.0"), then **NLM MeSH** (eutils.ncbi.nlm.nih.gov)
  and **MedlinePlus** (wsearch.nlm.nih.gov, medlineplus.gov) as a supplement. Requests carry the generic User-Agent "AnatoVision/1.0 (UB CDA 650
  course project)" and no personal data. `WEB_ALLOW_WIKIPEDIA=off` turns Wikipedia off. If `TAVILY_API_KEY` is set,
  Tavily searches only those domains and its results are dropped unless the page URL is on the list. Up to 3 passages of about 1,500
  characters, 6 seconds in total, cached 7 days in `data/web_cache/`; any error or empty result silently becomes the ordinary "not covered"
  message. The model may use only the fetched text; an answer it cannot support becomes "not covered". The student sees "From Wikipedia, not
  in Dr. Inglis's notes or OpenStax. Check with your instructor." ("From the web, ..." when only MeSH/MedlinePlus text was used) above the answer, and title, site, link and date in the Sources tab. Web
  answers are logged with `web: true` and their URLs; the professor Usage tab counts them and lists them (filter), and "Report an error" works on them.
- **Chat history (Q&A).** "New chat" at the top of the Q&A sidebar, then your chats grouped Today / Yesterday / Previous 7 days / Older;
  click to reopen (sources and "How this answer was built" included, no model call), "⋯" to rename or delete (permanent, with a confirm).
  50 chats per user, 200 messages per chat. A professor previewing as a student saves nothing. Chats unused for `CHAT_RETENTION_DAYS`
  (90) are deleted when the app starts and when someone signs in.

### How an answer looks

The answer comes first, as smooth markdown (an opening sentence, bold lead-ins such as **Boundaries** and **Contents**, merged bullets,
numbered steps), with small numbered markers [1] [2] at the end of a paragraph or bullet (one per source, never the same marker on
consecutive lines). Under it, a compact **Sources** list: OpenStax entries link to the exact section page on openstax.org (all URLs are
verified by `scripts/verify_openstax_urls.py`; an unverified one links to the book's contents page), Wikipedia entries link to the page,
Dr. Inglis's notes and guides have no public link and open in the right-hand panel. Clicking a marker (or a notes/guide line) opens that
source in the Sources tab. One quiet line may follow ("Based on OpenStax and Wikipedia, not Dr. Inglis's notes.") and, if the student lacks
the lecture, a short access line. When the textbook alone would answer only part of a question, a coverage check fetches Wikipedia for the
missing part. Refusals and "not covered" keep their box.

### What is where

- **Pages:** `/chat` (Ask the lab), `/guide`, and `/dashboard` (professor only; a student who opens it gets "That page is for instructors"). Each page has its own browser-tab title.
- **Student view** (sidebar: Guide, Q&A, Quiz "coming soon"; body type, answer length, lecture scope). Answers carry numbered chips with a short
  label ("1 · Notes · L08"); a chip opens the passage in the Sources pane with only the supporting line highlighted. On a phone or tablet the
  pane opens as a bottom sheet with a Close button. "Report an error" under each answer sends a flag to Dr. Inglis. The Guide asks the student
  to describe what they see first; the notes appear after they check, or when they choose "Show the notes" (logged).
- **Professor dashboard:** Review queue (one card per item, details behind "Show details", a Decide panel that stays open, a typo-only bulk action
  with a confirmation), Verified fixes (before/after, Undo with a confirmation), Notes library, Access (Grant all / Revoke all ask first),
  Usage (cost per day, stacked by type, with a table), Settings. The "Student reports" tab lists what students reported.
  Ctrl/Cmd+Enter in the correction box never records a decision. "View as student" shows a coloured bar with an "Exit preview" button.
- **Spending cap**: default $2 per session, editable in Settings. When reached, the app says so (without any dollar amounts) and stops calling the model. Cost and the model name are shown to the professor only.
- The original notes in `data/raw/notes/` are never edited. Uploads are kept as versions in `data/raw/notes_uploaded/`.
- Student questions are logged in `data/question_log.jsonl` (with the username) so the professor can see gaps in the notes. Keep that in mind for privacy.

## Quiz

`/quiz` (students; professors see "Quiz as student" and a **Quiz items** tab). A student picks 5 or 10 questions (default 5) from the lectures and guides they may open, or types an anatomy topic. Questions are single-best-answer (4 options, the schema already stores a list of answer ids for a later multiple-answer mode).
Sources, in order: verified fixes > course notes and dissection guides > OpenStax > the approved web (Wikipedia first, only when the earlier tiers are too thin). Nothing comes from model memory, and course text outside the grant is never read.
Every question must pass all gates before a quiz starts: local NBME-style checks (`reports/quiz_item_writing_checklist.md`), every key/explanation/"why the others fail" cites a real passage id and an exact span found verbatim in it, Gemma solves the item blind (no key), gpt-oss-120b solves it blind and then audits the explanations against the cited spans. Any failure rejects the draft; a quiz is never padded. If a 10-question quiz has only 5 passing questions the student gets an explicit offer to take 5.
Keys, explanations and sources stay in `data/quizzes.db` on the server and are shown only after the **whole** quiz is submitted. Attempts are per user and resume after signing in again. The professor can inspect the evidence and approve or reject each item; students can choose "Only approved questions", which never substitutes unapproved ones.
**Reuse and partial success:** every question that passes is saved. Building the same request again first reuses saved questions whose cited passages still have exactly the same text, that the student may still open, that are not rejected (or are approved, for approved-only), and that carry the current checks version; it generates only the missing number. If only some pass, they stay saved and "Continue preparing" looks only for the rest; a quiz still starts only when all 5 or 10 are in hand. Web-based questions are always rebuilt. Each question is written from a focused bundle (the passage it tests plus related passages for realistic alternatives), the audit also rejects options that mix kinds, and reasons that rest on a passage merely not mentioning something are rejected.
**Labels are honest:** "AI-checked" means two models agreed and the spans were verified, not that the item is correct or approved by Dr. Inglis.
Live check: `scripts/quiz_live_check.py`; report: `reports/quiz_live_check_2026-10-20.md`.

## Look and feel ("Vellum & Petrol")

All colours, type sizes, spacing and shared components live in `app/theme.py` (tokens are defined once, as CSS variables on `:root`);
`.streamlit/config.toml` carries the same colours for Streamlit's own widgets. Views never write colours, fonts or pixel sizes:
they call `theme.alert()`, `theme.chip_html()`, `theme.badge_html()`, `theme.button_row()`, `theme.section()` and friends.

- Contrast report for every colour pair: `.venv/bin/python -m app.contrast` (tests fail if a text pair drops under 4.5:1 or a control/icon pair under 3:1).
- A very small script in `theme.inject()` gives Streamlit's icon-only buttons (sidebar toggle, send, password eye) accessible names, marks
  the current page in the sidebar (`aria-current`), opens the sidebar again on wide screens, and focuses the password box after a failed sign-in.
  It only sets attributes and focus; nothing leaves the page.
- Page paths: `/chat` (Ask the lab), `/guide`, `/dashboard` (professor; a student gets "That page is for instructors"). Each sets its own tab title.
- Screenshots of the main screens at 1440, 961 and 390 px: `reports/ui_screenshots/part2/`.

## Command line (still works exactly as before)

```
.venv/bin/python -m src.modes.qa --ask "What are the walls of the middle ear?"
.venv/bin/python -m src.modes.guide --lecture "Lecture 09"
.venv/bin/python -m src.verified list
```

## Tests

```
.venv/bin/python -m pytest -q        # 554 pass, 9 skipped by design; no API calls, no cost
```
