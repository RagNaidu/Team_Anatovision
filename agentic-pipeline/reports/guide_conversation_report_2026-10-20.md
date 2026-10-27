# Conversational Guide: implementation and evaluation (2026-10-20)

Internal check only. Not medical validation, not deployed, no accuracy figure.

## What changed
- **Retrieval:** `embeddings_by_id()` pairs Chroma vectors with the ids Chroma returns (also in the incremental re-index). 4 regression tests use a collection that returns rows in a different order (cosines, BM25-champion promote/not-promote, found decision, reranker path).
- **Restricted text:** the unfiltered search in `service.ask` is replaced by `Searcher.outside_titles()` (local; titles only; no reranker, no model). Tests record reranker and model inputs for a restricted student: no ungranted text. Event wording corrected.
- **Guide truncation:** no slicing. Every instruction line of all 486 instruction slides in the 27 guides is kept (word comparison slide by slide, 0 mismatches); 57 long slides are paginated into parts (e.g. Class 17 slide 13 = s13.1, s13.2), each with its slide number. Class 8 slide 11 and Class 28 slide 15 are covered by the same all-guides check.
- **Conversation:** `src/modes/guide_chat.py` (explicit state; the model's JSON is validated against real step ids; the app alone moves position/marks work), `guide_service.py`, `guide_store.py` (per-user, per-guide, student-safe, 90-day retention), chat UI in `app/views/guide_ui.py`.
- **Demo access (intentional change):** student1 and student2 now hold all 26 lectures + 27 guide labels, granted with `auth.set_allowed_lectures`. users.json md5 6cc9ad7a... -> 71e8ab37.... Passwords, roles, names unchanged. Other accounts and future accounts are still restricted.
- `python-pptx` added to requirements.txt.

## Tests
815 passed, 9 skipped (baseline 764). New: guide engine 39, guide UI 10, retrieval/service 6.

## Live evaluation (`reports/guide_chat_eval_2026-10-20.md`, `.json`)
Class 14 and Class 17, 19 scripted turns (start, join midway, earlier step not done, confirm and continue, side question, vague/wrong observation, location correction). Generation gemma-4-31B-it; judge gpt-oss-120b. No gateway failures. Isolated: no saved sessions, question log, flags or chats.
Found and fixed by the first run: a vague "knee joint" was guessed (now clarified when several slides tie), recaps jumped back to old slides (now stop at handled work), "your description matches" was said when the student described nothing, "you mentioned rotation" was attributed to the student.
Second run, judge verdicts: factual support 10 supported, 4 minor_unsupported, 5 template replies (n/a); conversation 14 good, 5 partly, 0 poor (19 turns). Per-turn detail is in the file.
**Disagreements / limits, honestly:** the judge marks "You're at slide N" as unsupported (it is navigation, not a claim) and calls "partly matches the guide" a confirmation (the brief allows that wording); a judge once misread "quadratus" as "quadriceps". Recap questions can bundle up to 3 earlier slides, which the judge dislikes. Two guides, scripted turns, one run: this says nothing about real students. A vague observation that the model reads as "unexpected" gets the instructor wording rather than a restatement of the slide.

## UI (screenshots in `reports/ui_screenshots/part8/`, checked at 1440 and 390 px, no horizontal overflow)
`01_picker`, `02_welcome`, `03_midway`, `04_conversation` (demo student, Class 14); `05_no_access` (no grants); `06_guide_only_picker`, `07_guide_only_midway` (guide grant only, no lecture grant, Class 17 midway entry). Sticky header with position and progress, outline expander, source markers that open the slide text, Start/Continue/Back/Show guide passage, explicit Change guide and Start over (confirmed). Controls are disabled while a turn runs (one queued job), failed turns show Try again.
A CSS bug found on the way: the main stylesheet ends inside an unclosed @media block, which swallowed later rules; it is now closed explicitly.

## Not done / unverified
- Lecture notes are not used inside Guide; unanswered side questions point to the instructor or Ask the lab.
- Image-only slides are never read (no vision step).
- Persistence is a local SQLite file, no encryption; reload signs the user out (existing behaviour), sign in again to resume. No keyboard-only walkthrough beyond native controls and AppTest; contrast not re-measured for the new CSS (it reuses existing tokens).
- Quiz stays "Coming soon". Not verified with real students or by Dr. Inglis.
