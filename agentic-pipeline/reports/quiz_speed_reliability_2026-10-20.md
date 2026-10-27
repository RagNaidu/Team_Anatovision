# Quiz generation: speed and reliability (2026-10-20)

Real models (Gemma 4 31B generating, gpt-oss-120b verifying, through BullsAI), isolated scratch stores (`scripts/quiz_benchmark.py`, `scripts/quiz_live_check.py`, the sandbox app). The real quiz database, users, flags, logs and chats were not used. Timings are single runs on one evening and vary with gateway load: they are measurements, not guarantees.

## Measured
| Run | Result | Time | Model calls | Drafts | Rejected by stage |
|---|---|---|---|---|---|
| **Before** (real app, Lecture 02, 5) | **4 of 5, no quiz** | 88.8 s | 54 | 15 | audit 6, structure 3, solver_gemma 1, solver_verifier 1 |
| After, Lecture 02 cold, 5 | **5 of 5** | 52.7 s | 31 | 8 | structure 2, mixed_options 1 |
| After, Lecture 02 again (same request) | 5 of 5, all reused | 0.0 s | 0 | 0 | - |
| After, Lecture 09 cold, 5 | 5 of 5 | 49.5 s | 37 | 8 | mixed_options 2, structure 1 |
| After, Lecture 09 again | 5 of 5, all reused | 0.0 s | 0 | 0 | - |
| After, Lecture 02 ask 10 (5 reused, 5 new) | 10 of 10 | 60.0 s | 46 | 12 | structure 3, duplicate 2, audit 1, mixed_options 1 |
| After, Lecture 09 ask 10 (5 reused, 4 new) | 9 of 10: offer (5 now / continue) | 79.1 s | 56 | 15 | mixed_options 5, structure 3, audit 2, duplicate 1 |
| After, Lecture 09 cold 10 (browser, new store) | 10 of 10 | 107 s | 94 | - | mixed_options 7, structure 3, audit 2, solver_verifier 1 |
| After, web topic "cubital fossa", 5 (browser, then service) | 2 of 5 saved, no quiz, "Continue preparing" offered | 39-41 s | 28-30 | 8 | structure 3, mixed_options 2, audit 2 |
Reuse in the browser: a repeated Lecture 09 request reached the first question in about 4 s of page time with 0 model calls. Intermediate run (bundles but before the span-id repair and outline-path spans): Lecture 02 cold 61.2 s, 49 calls, 13 drafts.
Lecture 02: 12 usable passages. Speed-up on the like-for-like cold 5-question build: 88.8 s to 52.7 s (about 40% less), 54 to 31 calls, and the request that used to fail succeeded; one run each, so treat it as indicative.

## What changed and why it helped
- **Reuse first**: saved, already-checked items are reused when the version, grants, selection/topic, review status and the *current text of every cited passage* still match (a changed or newly flagged line retires the item; web items only while the current lookup returns identical text). Only the missing number is generated. Reuse costs no model call.
- **Partial success**: accepted items stay saved; "Continue preparing" re-runs the same request for just the missing ones. No quiz ever starts incomplete and the length never changes silently.
- **Evidence bundles**: each draft gets the passage it is about plus up to three related passages (distinct objectives chosen by a diversity ordering over the whole lecture, strong passages first), so wrong options can be real structures with their own stated facts. Absence-based "why wrong" reasons are rejected locally and by the audit.
- **Comparable options**: the independent audit now also rejects options that answer the lead-in on different dimensions (it rejected 1-7 drafts per build). This is deliberately strict; I did not loosen any factual gate to raise acceptance.
- **Scheduling**: one global limit of 4 model calls in flight, no waves (each candidate is processed as it finishes and new ones start only while they can still fill the quiz), the two blinded solves run together, the audit stays independent and sequential. Concurrency was not increased.
- **A bug the benchmark exposed**: the lecture notes are bulleted outlines and the model quotes "Trapezius / Innervation / Accessory nerve" across skipped lines, so correct spans were rejected as "not found" (the main cause of structure rejections). Spans may now be an *outline path* (each line a child of the previous one, same branch); a heading joined to another heading's fact is still rejected. A span attached to the wrong passage id is corrected only if it is verbatim in exactly one other supplied passage. Outline indentation is now kept in the stored passage text.

## Inspection of accepted questions and rejections
I read the accepted items of the benchmark runs. Mostly sound and comparable (action, origin and insertion questions with same-kind options; "which structure forms the roof of the carpal tunnel", "action of the palmar interossei"). Problems still visible: (1) some options overlap or are nested ("Ulnar nerve" beside "Deep branch of the ulnar nerve"), (2) a couple of distractors are odd in kind ("Base of first digit phalanx" among bases of phalanges), (3) two questions in one run tested the same fact in different words, which led to the same-cited-fact duplicate check. Rejection reasons: audit rejections were mostly reasons the sources did not state ("rhomboids insert...", an artery named in a distractor reason); mixed-option rejections were genuine mixes (muscle vs. bone site vs. action) in most cases I read; structure rejections were clang clues, convergence, and invented spans.

## Limits
- Pass rates still vary: Lecture 09 ask-10 ended 9 of 10 and a web topic ended 2 of 5. A request can need "Continue preparing" more than once, each press bounded to 3 drafts per missing question.
- 31-107 s cold builds are still long; reuse is instant. Most time is the three sequential model steps per candidate (draft, solves, audit) with 4 calls in flight.
- Wikipedia gives at most three short passages, so thin web topics fail honestly.
- The checks are model agreement plus source checking, not proof of correctness; nothing here is instructor-approved.
