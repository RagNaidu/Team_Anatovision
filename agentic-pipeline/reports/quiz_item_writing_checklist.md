# Quiz item-writing checklist

Source: NBME, *Constructing Written Test Questions for the Basic and Clinical Sciences* (4th ed., 2016), `data/raw/assessment_guidelines/NBME Test Writing Guide.pdf` (kept unmodified, outside the anatomy index). Page numbers: **PDF page (printed page)**; PDF page = printed + 8. Only the *writing rules* are used; the manual's clinical examples are not anatomical evidence, and applying the rules does not make an item NBME-approved or instructor-approved.

| # | Rule | Where | Enforced in code (src/quiz/items.py unless noted) |
|---|---|---|---|
| 1 | One best answer: exactly one option is keyed; wrong options may be partly or wholly wrong | PDF 18 (10) | one key index, `answer_ids` list (single today, multi-ready); blind solvers must find no second defensible option |
| 2 | Clear, unambiguous wording; avoid vague terms ("usually", "often", "frequently", "is associated with") | PDF 18, 20 (10, 12) | `VAGUE` word check on stem and options |
| 3 | Closed, focused lead-in; answerable with the options covered ("cover-the-options") | PDF 18, 38 (10, 30) | lead-in must be one question; blind solve is also run, and the lead-in must start with "Which/What/Where/How many" and end with "?" |
| 4 | Options homogeneous, parallel, plausible; one dimension | PDF 18, 21, 38 (10, 13, 30) | 4 options, no duplicates, similar length, same kind of phrase (checked by the verifier) |
| 5 | No "none of the above" / "all of the above" | PDF 21 (13) | `BANNED_OPTIONS` |
| 6 | No negative stems ("EXCEPT", "NOT") | PDF 23 (15) | `NEGATIVE` stem check |
| 7 | No grammatical cues; each option fits the lead-in | PDF 23 (15) | verifier prompt; options may not start with different parts of speech markers ("a", "an") only to fit |
| 8 | No absolute terms ("always", "never", "only") in options | PDF 24 (16) | `ABSOLUTE` option check |
| 9 | Correct option not noticeably longer or more complete | PDF 25 (17) | key length <= 1.5 x the median of the others |
| 10 | No clang clues: a distinctive word of the stem repeated in the key only | PDF 25 (17) | stem/key word-overlap check |
| 11 | No convergence (key shares the most words with the other options) | PDF 26 (18) | convergence check on option word sets |
| 12 | Not unnecessarily complicated: short options, no extraneous stem detail | PDF 19, 22 (11, 14) | option and stem length limits |
| 13 | Test an important concept; favour application over recall of an isolated fact where the evidence supports it | PDF 37 (29) | generation prompt (one testing point per evidence passage; a short scenario only if the source supplies the facts; **no invented clinical detail**) |
| 14 | Review every item for flaws before use | PDF 39 (31) | all of the above plus the two independent solvers |
| - | Item analysis from real responses (difficulty, discrimination) | PDF 29-34 (21-26) | **not done**: no difficulty labels are claimed; attempts are stored so it can be done later |

Anatomy-specific additions (not from the manual): every key, explanation and reason an alternative fails must cite a real source passage and an exact supporting span; withheld or under-review lines are never evidence.
