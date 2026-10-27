# All-lecture Quiz audit — 2026-10-20

Updated UTC: 2026-10-21T03:13:23.837362+00:00

Local evidence checks are not successful live quizzes or factual accuracy validation.

Lecture files: **26**. Distinct files/titles are used because lecture numbers repeat.

## Shared connection check

- google/gemma-4-31B-it: reachable; 0.5 s;  .
- openai/gpt-oss-120b: reachable; 0.6 s;  .
- After the run, google/gemma-4-31B-it: REFUSED, HTTP 429 the budget of the course's BullsAI key is used up (HTTP 429: budget exceeded).
- After the run, openai/gpt-oss-120b: REFUSED, HTTP 429 the budget of the course's BullsAI key is used up (HTTP 429: budget exceeded).

Live checks stopped part-way: the shared BullsAI gateway answered google/gemma-4-31B-it: HTTP 429 the budget of the course's BullsAI key is used up (HTTP 429: budget exceeded); openai/gpt-oss-120b: HTTP 429 the budget of the course's BullsAI key is used up (HTTP 429: budget exceeded). Cases marked Blocked were NOT run and are not content failures.

## Per-lecture results

Pool capacity is the existing heuristic, not a count of verified questions. Cached items are filtered by current version, sources, scope, and grants.

| Lecture | Usable passages | Usable words | Evidence 5/10 | Cached items eligible before the audit | Live 5 (cold) | Live 10 (after the 5) | Re-run 5 after fixes | Re-run 10 after fixes |
|---|---:|---:|---|---:|---|---|---|---|
| ANA407 Class 28 - The Posterior Abdominal Wall | 16 | 2235 | OK/OK | 0 | **ready** 5/5; 64.6 s; generated 5, reused 0; 49 calls; rejected audit 1, structure 2, mixed_options 1 | **ready** 10/10 (extends the 5-question run); 63.2 s; generated 5, reused 5; 47 calls; rejected duplicate 1, solver_verifier 1, mixed_options 1 | - | - |
| Lecture 01 - The Vertebral Column | 23 | 2910 | OK/OK | 0 | **ready** 5/5; 59.6 s; generated 5, reused 0; 46 calls; rejected solver_verifier 1, audit 1, mixed_options 1 | **ready** 10/10 (extends the 5-question run); 96.6 s; generated 5, reused 5; 57 calls; rejected structure 3, audit 2, mixed_options 1 | - | - |
| Lecture 02 - Muscles of the Back | 12 | 1796 | OK/OK | 0 | **ready** 5/5; 37.2 s; generated 5, reused 0; 25 calls; rejected structure 1 | **ready** 10/10 (extends the 5-question run); 50.3 s; generated 5, reused 5; 33 calls; rejected duplicate 1 | - | - |
| Lecture 03 - Nerves Spinal Cord and Meninges | 12 | 1783 | OK/OK | 0 | **ready** 5/5; 74.6 s; generated 5, reused 0; 52 calls; rejected solver_verifier 1, structure 1, audit 1, mixed_options 1 | **ready** 10/10 (extends the 5-question run); 66.3 s; generated 5, reused 5; 45 calls; rejected audit 3, solver_gemma 1 | - | - |
| Lecture 04 - The Shoulder | 17 | 1651 | OK/OK | 0 | **ready** 5/5; 100.9 s; generated 5, reused 0; 70 calls; rejected audit 1, mixed_options 2, structure 2 | **ready** 10/10 (extends the 5-question run); 103.3 s; generated 5, reused 5; 68 calls; rejected structure 4, mixed_options 1, duplicate 3, audit 2 | - | - |
| Lecture 05 - The Axilla | 12 | 1837 | OK/OK | 0 | **ready** 5/5; 82.5 s; generated 5, reused 0; 49 calls; rejected solver_verifier 1, audit 3, mixed_options 1 | **ready** 10/10 (extends the 5-question run); 51.5 s; generated 5, reused 5; 35 calls; rejected duplicate 1, audit 2 | - | - |
| Lecture 06 - The Brachium | 12 | 873 | OK/OK | 0 | **ready** 5/5; 66.0 s; generated 5, reused 0; 42 calls; rejected audit 2, mixed_options 1, model_error 1 | **offer** 7/10 (extends the 5-question run); 120.2 s; generated 2, reused 5; 86 calls; reason: rejected; rejected audit 3, structure 2, mixed_options 4, solver_verifier 1, model_error 1, solver_gemma 2 | - | - |
| Lecture 07 - The Antebrachium | 33 | 2166 | OK/OK | 0 | **ready** 5/5; 45.9 s; generated 5, reused 0; 37 calls; rejected structure 1, solver_gemma 1, audit 1, solver_verifier 1 | **ready** 10/10 (extends the 5-question run); 53.5 s; generated 5, reused 5; 48 calls; rejected structure 2, audit 1, solver_gemma 1 | - | - |
| Lecture 08 - Anterior and Medial Thigh | 28 | 2357 | OK/OK | 0 | **ready** 5/5; 32.3 s; generated 5, reused 0; 27 calls; rejected structure 1, audit 1 | **offer** 8/10 (extends the 5-question run); 102.1 s; generated 3, reused 5; 77 calls; reason: rejected; rejected structure 4, solver_verifier 1, mixed_options 4, audit 3 | - | - |
| Lecture 09 - The Hand | 25 | 1975 | OK/OK | 0 | **ready** 5/5; 49.6 s; generated 5, reused 0; 25 calls | **ready** 10/10 (extends the 5-question run); 45.8 s; generated 5, reused 5; 39 calls; rejected solver_verifier 1 | - | - |
| Lecture 10 - Anterior and Lateral Leg | 11 | 1068 | OK/OK | 0 | **ready** 5/5; 57.8 s; generated 5, reused 0; 40 calls; rejected structure 2, audit 1, mixed_options 1 | **ready** 10/10 (extends the 5-question run); 72.4 s; generated 5, reused 5; 59 calls; rejected duplicate 5, audit 1, mixed_options 1 | - | - |
| Lecture 11 - Gluteal Region and Posterior Thigh | 13 | 818 | OK/OK | 0 | **ready** 5/5; 42.5 s; generated 5, reused 0; 27 calls | **offer** 9/10 (extends the 5-question run); 82.3 s; generated 4, reused 5; 59 calls; reason: rejected; rejected solver_verifier 1, solver_gemma 1, audit 2, duplicate 4, mixed_options 1, structure 2 | - | - |
| Lecture 12 - Posterior Leg and Plantar Surface of Foot | 27 | 2029 | OK/OK | 0 | **ready** 5/5; 88.1 s; generated 5, reused 0; 70 calls; rejected structure 3, audit 2, mixed_options 2 | **offer** 8/10 (extends the 5-question run); 89.6 s; generated 3, reused 5; 65 calls; reason: rejected; rejected structure 4, solver_verifier 1, solver_gemma 2, mixed_options 2, duplicate 1, audit 2 | - | - |
| Lecture 13 - The Hip and Knee Joints | 13 | 1549 | OK/OK | 0 | **ready** 5/5; 66.3 s; generated 5, reused 0; 41 calls; rejected structure 2, mixed_options 2 | **ready** 10/10 (extends the 5-question run); 97.7 s; generated 5, reused 5; 68 calls; rejected audit 2, mixed_options 3, duplicate 2, structure 1 | - | - |
| Lecture 14 - Anterior Triangle of the Neck | 7 | 821 | OK/OK | 0 | **ready** 5/5; 69.1 s; generated 5, reused 0; 46 calls; rejected structure 5, duplicate 3 | **offer** 8/10 (extends the 5-question run); 85.6 s; generated 3, reused 5; 53 calls; reason: rejected; rejected structure 6, duplicate 3, audit 1 | - | - |
| Lecture 14 - The Pelvic Cavity | 27 | 3189 | OK/OK | 0 | **ready** 5/5; 65.4 s; generated 5, reused 0; 51 calls; rejected structure 2, audit 2, mixed_options 1 | **ready** 10/10 (extends the 5-question run); 56.0 s; generated 5, reused 5; 40 calls; rejected audit 1 | - | - |
| Lecture 15 - Face and Parotid Region | 14 | 1216 | OK/OK | 0 | **ready** 5/5; 66.6 s; generated 5, reused 0; 50 calls; rejected solver_gemma 1, structure 4, audit 1 | **offer** 9/10 (extends the 5-question run); 103.7 s; generated 4, reused 5; 70 calls; reason: rejected; rejected structure 6, audit 1, duplicate 3, mixed_options 1 | - | - |
| Lecture 15 - The Perineum | 13 | 1711 | OK/OK | 0 | **ready** 5/5; 33.7 s; generated 5, reused 0; 27 calls; rejected structure 1 | **offer** 7/10 (extends the 5-question run); 94.0 s; generated 2, reused 5; 73 calls; reason: rejected; rejected solver_verifier 3, structure 2, audit 1, duplicate 3, mixed_options 4 | - | - |
| Lecture 16 - Anterolateral Thoracoabdominal Wall | 65 | 9147 | OK/OK | 0 | **ready** 5/5; 90.4 s; generated 5, reused 0; 63 calls; rejected solver_verifier 1, structure 2, mixed_options 2, solver_gemma 1 | **ready** 10/10 (extends the 5-question run); 72.5 s; generated 5, reused 5; 54 calls; rejected structure 5, audit 1 | - | - |
| Lecture 16 - Posterior Thigh and Popliteal Fossa | 11 | 626 | OK/OK | 0 | **partial** 2/5; 54.6 s; generated 2, reused 0; 39 calls; reason: rejected; rejected structure 7, solver_gemma 1 | **partial** 2/10 (extends the 5-question run); 52.6 s; generated 0, reused 2; 35 calls; reason: rejected; rejected solver_verifier 2, structure 5, audit 1, solver_gemma 1, mixed_options 1 | - | - |
| Lecture 16 - Temporal, Masseteric, and Infratemporal Region | 9 | 1061 | OK/OK | 0 | **ready** 5/5; 34.8 s; generated 5, reused 0; 24 calls; rejected structure 1 | **ready** 10/10 (extends the 5-question run); 72.2 s; generated 5, reused 5; 50 calls; rejected structure 3, duplicate 1, mixed_options 1, audit 1 | - | - |
| Lecture 16b - Middle Ear | 7 | 818 | OK/OK | 0 | **ready** 5/5; 58.5 s; generated 5, reused 0; 52 calls; rejected structure 1, audit 1, solver_gemma 1, mixed_options 1 | **ready** 10/10 (extends the 5-question run); 79.6 s; generated 5, reused 5; 54 calls; rejected duplicate 1, structure 2, mixed_options 1, model_error 2 | - | - |
| Lecture 17 - Cranial Fossa, Dura, Sinuses and Meninges | 10 | 1027 | OK/OK | 0 | Blocked: the budget of the course's BullsAI key is used up (HTTP 429: budget ex | Blocked: the budget of the course's BullsAI key is used up (HTTP 429: budget ex | - | - |
| Lecture 20 - Larynx | 14 | 1093 | OK/OK | 0 | Blocked: the budget of the course's BullsAI key is used up (HTTP 429: budget ex | Blocked: the budget of the course's BullsAI key is used up (HTTP 429: budget ex | - | - |
| Lecture 21 - Nasal Cavity | 7 | 830 | OK/OK | 0 | Blocked: the budget of the course's BullsAI key is used up (HTTP 429: budget ex | Blocked: the budget of the course's BullsAI key is used up (HTTP 429: budget ex | - | - |
| Lecture 22 - Oral Cavity | 11 | 992 | OK/OK | 0 | Blocked: the budget of the course's BullsAI key is used up (HTTP 429: budget ex | Blocked: the budget of the course's BullsAI key is used up (HTTP 429: budget ex | - | - |

## Meaning and limitations

- Evidence OK means the real lecture passed the existing evidence-pool gate, candidate bundles were produced, and no unselected lecture entered them. It does not establish that 5/10 good questions can be generated.
- Live ready means an actual isolated quiz passed the current generation/solver/audit pipeline; it is not instructor or medical validation.
- Blocked means the shared AI connection was unavailable. It is not a failure of that lecture's content.
- Live 5 is a cold request per lecture. Live 10 uses accepted items from that lecture's 5-question request. These are distinct measurements.
- All original runtime stores are protected. New attempts and private keys live only in a temporary audit store.
- Isolated audit store directory: `/var/folders/p5/r_tvln592hgbct33sdy574fc0000gp/T/anatovision_all_lectures_tw5mylcf` (one database per lecture).

## Protected file comparison

- flags.jsonl: unchanged.
- question_log.jsonl: unchanged.
- chats.db: unchanged.
- users.json: unchanged.
- guide_sessions.db: unchanged.
- verified_fixes.jsonl: unchanged.
- quizzes.db: unchanged.

## What the audit found, what was fixed, what is still open

**Connectivity.** With the VPN on, a bounded probe reached both models (Gemma 2.9 s, gpt-oss 0.3 s) and the 26-lecture live run started. Midway (at Lecture 17) **BullsAI began answering HTTP 429 "Budget has been exceeded: current cost 5.01, max budget 5.0"** for both models. That is a spending cap on the course key, not a network or VPN fault, and the audit's own generation used it up. The script stopped as designed. **Lectures 17 (5 and 10), 20, 21 and 22 were not run** (marked Blocked; no generation was attempted after the 429, and no further live calls were made). They need the budget raised before they can be checked.

**Results with the final code (22 of 26 lectures actually run).** 5-question requests: 21 of 22 ready; the exception is Lecture 16 - Posterior Thigh and Popliteal Fossa (2 of 5, an 11-passage / 626-word lecture). 10-question requests (each extends that lecture's own 5-question run, so 5 are reused and 5 are generated): 14 ready; 7 stopped at 7 to 9 questions and were offered "start with 5 / continue preparing" (Lectures 06, 08, 11, 12, 14 Anterior Triangle, 15 Face and Parotid, 15 Perineum) plus Lecture 16 Popliteal Fossa stayed at 2. No quiz was ever padded. A question reaching 10 required extra "Continue preparing" presses in those lectures.

**Causes found, by layer** (baseline Lecture 06 real-app run: 220.5 s, 0 accepted, all gateway errors, before this work):
- *API*: the 90 s connect wait and retry made an unreachable gateway look like an endless "0 of 5". Fixed: 10 s connect timeout, a tiny bounded probe of both models before any drafting (fails in seconds with the real reason: unreachable vs budget exhausted vs refusal), progress lines for each failure, accepted questions kept. The 429 budget error is named as a budget problem, not a network problem.
- *Extraction/evidence (the main shared cause for Lecture 06 and other outline lectures)*: the notes are bulleted outlines whose subject is the heading (e.g. "Coracobrachialis"), and the heading was not part of the passage text. A passage read "- Fusiform muscle ... - Flexes, adducts shoulder", so writers cited the heading from the source label and every such citation was rejected as "not found". The heading path is now part of the passage text with the body nested under it. Lecture 06 went from 2 of 5 (baseline, 4 structure rejections) to 5 of 5.
- *Validation*: spans that list several lines of one outline entry (heading, then facts under it) were rejected because I required a parent-child chain; they are now accepted if every line is verbatim inside the first line's subtree, in order. A heading can still never be joined to another heading's fact (tests).
- *Generation*: options that the independent audit called mixed were rejected outright; they now get one repair pass (the audit's named odd options are replaced by same-kind ones) and are accepted only if the second solve and audit pass.
- *Storage*: no cause found; reuse, partial saves and per-lecture isolation worked (scratch databases only).

**Honest remaining limitations.** Small or sparse lectures (Lecture 16 Popliteal Fossa 626 words; Lecture 06 821 words; Lectures 14 and 15) often cannot reach 10 good questions in one bounded attempt. Rejections that remain are mostly real: reasons the notes do not support, two defensible options, mixed-kind options, near-duplicates. A transient gateway error (`model_error`) cost a few candidates in Lectures 06, 09 and 16b. Elapsed times are 32 to 120 s per request, 25 to 86 calls, with 4 calls in flight.

**Browser check (Lecture 06).** The app's setup, progress, one-question-at-a-time view, answering, review, whole-quiz submit and the results page with explanations and highlighted source passages were driven in a real browser at 1440 and 390 px (screenshots `reports/ui_screenshots/part11/`), and a second identical request reused the saved questions in about 4 s with no model call. **That browser run used the 5 questions the audit had already generated for Lecture 06** (copied into a scratch store): a fresh browser-triggered generation could not be repeated after the budget ran out. An earlier browser generation for Lecture 06, before the heading/span fixes, ended 3 of 5 saved with a "Continue preparing" offer.

**Tests.** `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m pytest -q tests`: 914 passed, 9 skipped. Not claimed: factual correctness of any question, instructor approval, or that the four blocked lectures work.
