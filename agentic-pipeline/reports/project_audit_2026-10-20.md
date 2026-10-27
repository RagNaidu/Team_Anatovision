# AnatoVision project audit — 2026-10-20

Audit of the local project and the Team AnatoVision Trello board. No application code, grants, review decisions, source documents, or credentials were changed. The only project addition is this report.

## Project understanding

AnatoVision supports anatomy study and dissection for UB's anatomy lab. The core product combines source-grounded student Q&A and dissection guidance with an instructor review loop. Instructor decisions take priority; AI flags are suggestions for review, not established errors. It is a local prototype, not a deployed or clinically validated service.

Current source order: verified fixes > lecture notes and dissection guides > OpenStax > approved web passages. Student answers must be supported by supplied material, with citations. Missing evidence should produce a gap or refusal, not a memory-based answer. The separate, older fact-check report includes AI judgments based on general anatomy knowledge; that report is not independent ground truth.

## Trello evidence and scope

The board was read using the existing signed-in Chrome session. Lists and card titles were reviewed across the board; detailed reading covered the three client phase cards, all three meeting-minutes cards, the Toronto library card, and the citation task. This was not a review of every historical activity entry or attachment.

- [Board](https://trello.com/b/DpUFHlW2/team-anatovision): This Week has 4 cards, Doing 5, Blockers 1, Done 33 at the time of inspection. Done contains administrative work as well as product work; its count is not a feature-completion metric.
- This Week: unified knowledge base and retrieval (Sai), connecting Ask Anatomy to that knowledge base (Saandeepa), citation/reference display (Ani).
- Doing: guides files 1–9 (Sai), 10–18 (Ani), 19–27 (Saandeepa), remaining lecture-note review (Sai), Toronto image-library research (Saandeepa).
- Blocker: Dr. Stuart's verified fixes. This matches the empty local verified-fixes file.
- [Initial meeting, September 28](https://trello.com/c/CFhFrWlk/18): Phases 1 and 2 prioritized; Phase 3 deferred. Concise external-source supplementation allowed, disagreements reported for review. Public student access is an eventual objective. NBME item-writing guidance is a client input.
- [October 2 meeting](https://trello.com/c/5FDkj2a8/50): separate student/professor roles, uploads, Course Library, Dissection Guide, RAG grounding, citations, careful handling of insufficient evidence, and evaluation questions.
- [October 8 meeting](https://trello.com/c/nrGaft3B/52): two AnatoVision prototypes were demonstrated (Sai's RAG prototype and Ani's agentic prototype). OpenStax was accepted as a useful supplementary choice, anatomy emphasized over physiology, donor-body images to be removed from shared guides, and reviewed materials to be organized in UB Box. Do not assume this folder represents all code from both prototypes.
- [Phase 1](https://trello.com/c/GUGUr7UV/19): approved-note knowledge system, student Q&A, identifying inaccuracies for correction, website access.
- [Phase 2](https://trello.com/c/Qe81raCz/20): NBME-style assessment generation, approximately 10,000-question bank, selection of 50 questions, and quality validation. This is broader than a small Quiz tab.
- [Phase 3](https://trello.com/c/TkjCfrNp/21): exploration of accurate text-to-anatomical-diagram generation. The later [Toronto library task](https://trello.com/c/jgAY1d8Z/60) identifies RBAI077 as an illustration source. Retrieving historical illustrations is a distinct implementation direction; do not silently equate it with completing diagram generation.
- The board links to `https://github.com/RagNaidu/Team_Anatovision`. This local folder has no Git repository; remote contents and synchronization were not verified.

## Current local implementation

| Area | Evidence/status |
|---|---|
| App | Streamlit, student/professor roles, Vellum & Petrol theme. Started and login screen visually inspected at http://127.0.0.1:8501/ . |
| Model | Configuration resolves to BullsAI, `google/gemma-4-31B-it`. A legacy optional Anthropic adapter remains in code. No live generation or full fact-check was run in this audit. |
| Retrieval | Local bge embeddings + Chroma + BM25 + RRF, course-material boost, grant filters, reranker with fallback, heading/term rescue. |
| Corpus | 26 original lecture-note documents; 562 parsed notes sections; 1,579 OpenStax sections; 27 guide decks / 518 slides. |
| Index | 4,637 records: 585 notes chunks, 373 guide chunks, 3,679 OpenStax chunks. Chroma count agrees with the chunk table. |
| Q&A | Brief/detailed output, follow-ups, keyword lookup, numbered source references, source panel, source links, OpenStax coverage check with Wikipedia supplementation. |
| Guide | New slide-based engine exists and is wired into the default guide UI. Lecture-notes walkthrough remains the sample option. New slide guide permits back/next/jump; it does not retain the old sample engine's no-skipping rule. |
| Access | Guides can be individually granted or opened through matched-lecture access. Map: 20 high, 3 medium, 4 unmatched. Both demo students currently have zero grants. |
| Review | Dashboard and correction/undo mechanisms exist. Fact-check report records 733 review items; verified-fixes file remains zero bytes. |
| History | Per-user SQLite chat history with retention, rename/delete, student-safe saved answers. |
| Not implemented | Functional Quiz/NBME bank, illustration integration/generation, persistent login, UB SSO, deployment, weekly digest, Box synchronization. |

The handoff's two pending tasks are now implemented in code and documented in the later build report: answer layout redesign and Guide on dissection slides. Their earlier live evaluation reports and screenshots exist. This audit freshly ran automated tests and inspected the login screen; it did not repeat authenticated browser flows or live model evaluation.

## Findings to address before further feature work

### 1. High: retrieval assigns similarity scores to the wrong passage IDs

Locations: `src/retrieval/search.py:170–171` and `:285–286`.

Both paths extract only the embeddings from `collection.get(ids=...)`, then zip those embeddings with the requested ID list. The actual collection returns IDs in a different order. The code must pair each embedding with the corresponding returned ID.

Read-only reproduction against the current local index:

- Requesting eight existing IDs in reverse order yielded eight mismatched positions in the returned ID list.
- With reranking disabled, the real query “What are the walls of the middle ear?” assigned the walls passage cosine **0.734**, although its own stored embedding gives **0.834**. The ear-lobe passage was assigned **0.834**, although its own cosine is **0.733**.

This does not swap passage text or citations. It corrupts per-passage relevance scores and can affect the BM25 champion's admission/replacement, heading/guide rescue, and reranking decisions that use those scores. The tests pass despite this mismatch. Fix and add an ID-order regression check before relying on retrieval scores.

### 2. Medium: three guide slides silently lose content at a 10-step cap

Locations: `src/modes/guide_slides.py:67–76`, `:102–110`.

`split_steps` keeps only the first ten steps, and the truncated steps become both the displayed station and the judge's reference text. Exact reproduction using the same cleaning and sentence-splitting logic found:

| Guide | Slide | Steps before cap | Omitted |
|---|---:|---:|---:|
| Class 08, Posterior Arm and Forearm | 11 | 11 | 1 |
| Class 17, Hip and Knee Joints | 13 | 13 | 3 |
| Class 28, Posterior Abdominal Wall | 15 | 11 | 1 |

Preserve all source instructions, using additional stations or pagination if needed. A student can currently receive a positive assessment without the omitted material being considered.

### 3. Medium: access-title detection can send restricted passages to the reranker

Locations: `src/service.py:273–285`; `src/retrieval/search.py:273–288`.

When a student's allowed material does not produce course-note hits, the service performs an **unfiltered** search to discover the titles of unavailable lectures. With reranking enabled, that search can pass ungranted course text to the BullsAI rerank endpoint. The event message nevertheless says nothing was sent.

A read-only probe replacing the rerank function with a recorder confirmed that this unfiltered search passes middle-ear course text to the reranker. No text was sent to an external endpoint by that probe. This is a mismatch with the documented “access filtering before any material reaches the model” guarantee; it is not evidence that restricted answer text was displayed to a student. The title-only availability check should avoid reranking restricted content, and its event description should reflect what actually happens.

### 4. Demo configuration: both students have no grants

`student1` and `student2` each have an empty `allowed_lectures` list. The empty Guide view is therefore expected. Grant intended materials through the instructor Access screen when the demo is configured. No grants were changed during this audit.

### 5. Reproducibility and documentation gaps

- No `.git` directory or version history is present. The build report explicitly discloses reconstruction of `search.py` after an accidental overwrite. The current passing suite is useful evidence, but does not establish parity with the lost file.
- `requirements.txt` is unpinned and omits the directly used `python-pptx` package. That package is installed in this existing environment; a fresh installation is not fully specified. No clean-environment rebuild was attempted.
- README's test count is still 554; PROGRESS ends at 725; latest build status and the fresh suite show 764. Old statements in CLAUDE.md are superseded by later appended updates. Use the current code and later build-status entries for present behavior.
- Startup produced Streamlit file-watcher warnings while inspecting optional Transformers vision modules because `torchvision` is absent. The login screen rendered and the cached embedding model loaded. No dependency installation or watcher change was made.
- `eval/` contains no golden test set. Client-supplied golden Q&As remain absent locally. Historical model-judge checks are small internal source-support evaluations, not a clinical or educational accuracy benchmark.
- No Toronto plate collection was found under this project's raw-data directories. The handoff's claim that approximately 27 files were downloaded was not verified elsewhere on the computer. Library reuse permission was reported in the handoff; supporting permission correspondence was not reviewed.

## Course-content issues still awaiting instructor input

Existing local reports identify the mislabeled ANA407 Class 28 notes file (digestive content under a posterior-abdominal-wall title), guide title-slide numbering mismatches, and four unmatched guide topics: pleura/lungs, mediastinum/heart, posterior abdominal wall, and orbit. Guide ingestion is not a completed fact-check of the guides. Existing AI flags and content mappings still require the appropriate instructor/team review.

## Fresh validation and limits

- Full suite: `.venv/bin/python -m pytest -q` → **764 passed, 9 skipped in 245.26 seconds**.
- Local retrieval probes used the cached embedding model. The score reproduction disabled reranking; the access-path probe used a local recorder instead of the external rerank API.
- SHA-256 comparison before and after tests/startup: `data/flags.jsonl`, `data/question_log.jsonl`, `data/users.json`, `data/verified_fixes.jsonl`, and `data/chats.db` all unchanged. Verified fixes remain empty.
- Original notes and guides were not edited. No secrets were displayed, no files were uploaded, and no Trello cards/comments were changed.
- No new live LLM answers, independent model judging, medical fact-checking, load test, full authenticated visual regression, or deployment assessment was performed. Earlier live evaluation numbers remain historical report evidence.

Next work is intentionally left for Ani to choose. The main dependencies are retrieval correctness, complete guide content, demo access setup, and instructor review/golden Q&As; the board's larger assessment and image goals remain separate future work.
