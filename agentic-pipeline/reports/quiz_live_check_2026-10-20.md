# Quiz: isolated live checks (2026-10-20)

Generation `google/gemma-4-31B-it`, independent verifier `openai/gpt-oss-120b`, both through BullsAI. All runs used temporary storage (`scripts/quiz_live_check.py` with a scratch SQLite file, or the sandbox app `scripts/sandbox_main.py`); the real users, flags, question log, chats, Guide sessions and verified fixes were not touched. This is an internal check of the pipeline, **not** an accuracy measurement: two models agreeing and spans being found in a source does not prove an item is correct, and none of these items was reviewed by Dr. Inglis.

| Case | Request | Outcome | Notes |
|---|---|---|---|
| Lecture 09, 5 questions (service) | materials, n=5 | **ready**, 5 of 5, 25 s, 23 model calls | 6 drafts, 1 rejected (structure) |
| Lectures 09 + 11, 10 questions (service) | materials, n=10 | **ready**, 10 of 10, 101 s, 78 calls | 19 drafts; 8 rejected at the audit (a "why this alternative fails" reason went beyond the cited span), 1 duplicate |
| Lecture 09, 5 questions (browser, full attempt) | student with all grants | **ready** (76 s), answered, reviewed, submitted, results shown | the first browser build of the same request, before span matching ignored punctuation, ended with only 3 of 5 passing and correctly started nothing |
| Lectures 09 + 11, 10 questions (browser) | student with all grants | **ready**, submitted, results shown | |
| Wikipedia fallback, "popliteal fossa", 5 (service and browser) | student with **no** grants | **ready**, 5 of 5: 3 web passages + 2 OpenStax passages | the course tier is closed to this student, OpenStax alone was too thin, so Wikipedia was asked; results show the OpenStax link and the web source label |
| "cubital fossa", 5 | no grants | **failed**, 4 of 5 passed | no quiz started, no padding |
| "pterygopalatine fossa", 5 (browser) | no grants | **failed**, 2 of 5 passed | no quiz started |
| "ligament of Struthers", 5 | no grants | **failed**: not enough source material (2 web passages) | made no draft call at all |
| "xylophone orchestra tuning" | no grants | refused: not an anatomy topic | 0.4 s, no model call beyond the scope check |

Screenshots (1440 and 390 px, no horizontal overflow at either width): `reports/ui_screenshots/part9/`
`A01..A05` 5-question attempt (setup, question, saved selection after Back, review, results); `B01..B03` 10-question attempt; `C02..C03` Wikipedia/OpenStax-grounded quiz and its results with the highlighted supporting spans and source link; `D02` insufficient-evidence failure; `E01..E02` professor view of an item with evidence.

## What the gates rejected in practice
Structure: a stem word repeated only in the key (clang clue), spans that were not in the passage, wrong number of alternative reasons. Solvers: a second defensible option named by Gemma or gpt-oss. Audit: reasons such as "not the central bands" with no support in the cited text. In the 10-question service run 9 of 19 drafts were rejected.

## Limits found
- The NBME checks are mechanical (vague words, none/all of the above, negative stems, absolute terms, length, clang, convergence). They do not judge whether the options are all one kind: an accepted item ("Where does flexor pollicis longus insert?") mixed a structure, a space and two bony sites among its options.
- Pass rates vary between runs of the same request (3 of 5 and 5 of 5 on Lecture 09), so a build can honestly fail and need a second try; the budget is at most 3 drafts per requested question, each with at most one repair call.
- Wikipedia returns at most three short passages, so thin topics fail. Topics are matched by their own words, so a loosely related passage is never used.
- Model agreement is not proof. Distractor reasons that the sources only support by exclusion can still be weak.
- Item statistics (difficulty, discrimination) are not computed; no difficulty is claimed.
