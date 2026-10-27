# AnatoVision: Quiz and expanded Q&A implementation prompt

Work in `/Users/anirudhramesh_11/Desktop/anatovision`. Implement the complete working feature below, verify it, and leave the app running. Do not stop at a plan or a disconnected prototype.

## Latest requirements: accuracy, exact quiz sizes, and delayed source reveal

These requirements override any older implementation prompt or report:

- Accuracy takes priority over speed, variety, or fulfilling a request. Never release an item with an unsupported key, ambiguous alternative, unresolved evidence conflict, or failed verification. Do not promise zero factual errors: source support and model agreement are safeguards, not proof of anatomical truth.
- Offer exactly **5 questions** or **10 questions**, default 5. No other quiz lengths, automatic extra batches, or silent rounding. Count each independently scored matching/shared-stem prompt toward the chosen total.
- Validate a complete 5- or 10-item batch before allowing an attempt to begin. If there are only five eligible items for a ten-question request, offer the five-question choice explicitly; do not silently change the size. If fewer than five survive, explain that there is insufficient reliable material and offer another topic. Do not weaken checks to fill a batch.
- Reveal correct answers, grading, explanations, anatomical citations, and supporting source passages **only after final submission of the entire quiz**. Answering or saving one item must not reveal these. Ordinary Q&A continues to show citations with its normal answers.
- The original NBME manual remains at the exact reference path below and must be integrated as item-writing guidance.

## Rules

- Keep Streamlit and the existing BullsAI gateway. Generation and helper calls use `google/gemma-4-31B-it`. Use `openai/gpt-oss-120b` through BullsAI for an independent, small live evaluation. No switch to Claude or another inference provider.
- No full fact-check run, deployment, publication, or file uploads. Never display secrets. Use the established BullsAI inference calls and allowlisted public-source retrieval for this feature; keep the original PDF local and send only relevant rule/source passages to the gateway.
- Never modify original source documents in `data/raw/`, including the NBME PDF. Do not rebuild the entire anatomy index just to add writing guidelines.
- Keep `data/verified_fixes.jsonl` empty. Do not alter existing users/grants, flags, logs, Q&A chats, or saved Guide sessions while testing. Isolate all tests and live checks, including new quiz records, in temporary storage. Hash protected files before/after, and account for concurrent real app usage rather than deleting it.
- No bulk 10,000-question generation. Build bounded, on-demand batches and a sound foundation for a later reviewed bank.
- Retry failed gateway/network calls at most once; do not multiply retries across SDK, JSON repair, and outer loops. Stop live checks on repeated 504s and finish unaffected local work. Use explicit time/call/batch budgets, visible cancellation/progress, and no endless refill loops.
- There is no local Git repository. Make a recoverable snapshot of files to be modified, excluding credentials and student runtime data. Preserve unrelated changes.
- Record stage completion in `reports/build_status.md`. Continue through all stages without pausing for routine implementation choices. At interruption, leave concrete completed/pending status.
- Run the full test suite. The last reported full baseline is 829 passed, 9 skipped; verify the actual baseline. Inspect real browser screenshots at 1440 and 390 px. Restart the app and give its URL. Report briefly and honestly.

## Read first

Read `CLAUDE.md`, its latest overriding updates, `README.md`, `reports/build_status.md`, `reports/project_audit_2026-10-20.md`, and the recent Guide reports. Inspect retrieval, source priority, grants, `student_view`, Q&A, controlled web lookup, LLM wrapper, navigation, theme, persistence, and test isolation before changing them.

Required writing reference, already present:

`/Users/anirudhramesh_11/Desktop/anatovision/data/raw/assessment_guidelines/NBME Test Writing Guide.pdf`

Reference note:

`/Users/anirudhramesh_11/Desktop/anatovision/data/raw/assessment_guidelines/README.md`

The supplied PDF is *Constructing Written Test Questions for the Basic and Clinical Sciences*, fourth edition, preface December 2016, 104 PDF pages. Expected SHA-256: `f5be7f6f42bbaac0306f212948412f33eb694428cdb5bc612ad5c81ebf1ec48b`.

Read the actual manual. Relevant printed/PDF pages: format families 5–10 / 13–18; technical flaws 11–19 / 19–27; core rules 29–31 / 37–39; application/vignettes 33 onward / 41 onward; retired formats 69–75 / 77–83; response-based item analysis 21–26 / 29–34.

Keep this PDF in its assessment-reference location. Extract a separate, page-aware, versioned rules/checklist artifact under `data/processed/assessment_guidelines/` and document its provenance. Do not insert its clinical sample questions into the anatomy answer corpus, copy its sample items into quizzes, or fine-tune a model on it.

The manual favors one-best-answer items and identifies drawbacks in negative stems and multiple-true/false formats. Ani explicitly wants negation and multiple-correct practice anyway. Implement them. Apply the manual's clarity, evidence, and item-quality principles, and label these additional formats accurately as extended practice. Do not claim they are recommended by NBME or that generated items are official, approved, or validated NBME questions. Do not treat the manual's 2016 descriptions as a verified statement of today's examination formats.

## Product behavior

Enable a real Quiz page, replacing the disabled Coming soon item. It should support anatomy exam practice from a selected permitted lecture/guide, a typed anatomy topic, or both.

The student can request examples such as:

- “Five questions on the hand.”
- “Harder questions for this lecture.”
- “Different questions; don't repeat the last set.”
- “Add one or two related topics beyond these slides.”
- “Which is NOT … questions.”
- “Select all that apply.”
- “Give me table-based multiple-choice questions.”

Interpret counts, topic, style, polarity, answer selection, difficulty, and source scope into validated settings that the student can inspect/change. Ambiguous consequential settings get one concise clarification. Quiz length is a validated enum containing only 5 and 10, default 5. If a typed request asks for another count, explain the two available choices and let the student choose; do not silently round or start an unsupported size.

All generated assessment items must be multiple choice, including table, matching, and ordering tasks. No essays, free-text answer fields, fill-in-the-blanks, drag-and-drop-only interactions, or image generation.

## Stage 1: share an evidence pipeline between Quiz and Q&A

Default to verified fixes > permitted instructor lecture notes/dissection guides > OpenStax > approved web text. Evaluate coverage of the actual requested learning objective, not merely whether retrieval returned some related hits.

Automatically retrieve public web evidence, with Wikipedia first, when:

1. The requested anatomy topic or a needed part of it is absent or insufficient in accessible course/reference passages.
2. The student explicitly asks for harder, different, or expanded practice beyond the slides. Perform a topical Wikipedia lookup in this situation even if the lecture itself has sufficient material, then use relevant evidence where it adds a supported angle.
3. The student asks for additional related topics outside the lecture. Keep them anchored to the requested region/objectives and visibly identify the expansion.

Use the same behavior for ordinary Q&A gaps and explicit expansion requests, including partial gaps when some course hits exist. The existing OpenStax-only coverage check is not sufficient for every case.

Reuse/extend the existing controlled lookup: Wikipedia's article text and relevant sections first, then the existing approved NLM MeSH/MedlinePlus sources if useful. No general unrestricted browsing agent, scraped answer banks, search snippets as evidence, bypassing blocks, or new paid search providers. Reuse allowlists, redirect validation, timeouts, caching, anatomy relevance checks, and reasonable throttling.

Search for normalized anatomy topics, not usernames, private conversation dumps, original restricted slides, or donor information. Treat fetched text as untrusted data, strip markup/instructions, and preserve title, article URL, section, retrieval time, and applicable attribution. Retain a source snapshot/hash for reproducibility; prefer Wikipedia revision metadata/permalinks where available through the existing API without adding excessive calls.

Access grants still apply before course material reaches any model/reranker. Public Wikipedia information about a student-entered topic may be used even when corresponding instructor notes are ungranted; it does not unlock those notes. Do not derive web search queries from restricted note text, expose its content, or claim that an external explanation is the instructor's lecture. Recheck grants on saved quiz resume/reuse.

If the web is disabled, throttled, or empty, use sufficient permitted local evidence or explain the evidence gap. Keep valid drafts available server-side within the existing generation budget, but start an attempt only when a complete chosen batch of 5 or 10 passes every check. Never invent facts to reach a question count or let one gateway failure discard previously valid drafts.

Preserve clinical scope: anatomy, function, lab identification, and source-supported anatomical clinical relevance. Do not expand into medication dosing or personalized diagnosis/treatment advice because the manual contains clinical examples. Conflicts remain instructor-review items; do not silently replace course claims with Wikipedia. Exclude unresolved conflicting or withheld facts from answer keys.

## Stage 2: question styles, modeled as independent dimensions

Separate response selection, presentation, cognitive task, polarity, and grouping. A table can be single-answer or multiple-correct; an application item can be positive or negative. Validate supported combinations rather than creating an unmaintainable enum for every permutation.

Implement these usable styles:

1. **Single best answer:** radio buttons; exactly one keyed option; typically 4–5 meaningful alternatives.
2. **Multiple correct:** checkboxes; at least two keyed options and at least one incorrect option; clear “Select all that apply” or “Select TWO” instructions. Validate a stated selection count against the actual key. Do not silently show radio buttons for these items.
3. **Negation/exception:** “Which is NOT …?”, “All of the following … EXCEPT …”, and explicit select-all-NOT variants. Display NOT/EXCEPT prominently and avoid double negatives. For single-answer negative items, exactly one option must satisfy the negative lead-in. For multi-answer negatives, the key is exactly the supported false/exception set.
4. **Table-based options:** lettered rows with named columns, such as structure / nerve / action or vessel / territory. The student selects the correct row or rows using radio buttons/checkboxes. Represent rows as typed structured data, not model-generated HTML or a fragile Markdown table. Each component of a keyed row and the reason each distractor row fails must be supported.
5. **Anatomical association/matching:** multiple prompts share an option list; each prompt is answered by selecting a listed option. State whether reuse is allowed. No text-entry matching. Include focused lead-ins and evidence for each pairing.
6. **Scenario/application questions:** concise lab/anatomical or source-supported clinical-relevance scenarios. Test relationships and reasoning; no invented examination findings or unsupported causal relationships added as decoration.
7. **Ordering/sequencing MCQs:** show alternative ordered sequences as choices, based only on explicit source order or stated dependencies. Do not treat a slide's position as an invented biological prerequisite.
8. **Statement-set combinations:** optional extended practice, where options encode explicit statement sets, such as statements 1 and 3 only. Store statement truth and combination membership structurally; ensure exactly the intended set wins. Avoid ambiguous coding and gratuitous “all/none of the above” filler. Identify this as extended practice, not the manual's preferred format.
9. **Shared-stem sets:** several independent MCQs use a common supported scenario or comparison. Each scored prompt counts toward the total of 5 or 10. All feedback remains hidden until the entire quiz is finally submitted. Do not claim exact simulation of a named NBME exam delivery format.

Support direct recall, relationships/comparison, and application as intended difficulty/cognitive settings. Harder means more supported reasoning and integration, not obscure trivia, verbal tricks, longer text, or unsupported clinical details. Difficulty labels are intended challenge, not measured item difficulty.

Defaults: provide a simple “Mixed practice” choice with standard questions plus requested variation; extended practice can include negation and multiple-correct by default when Mixed is selected. Also offer a focused one-best-answer preset based on the manual's preferred format. Let the student explicitly include/exclude individual styles. An explicit request for a style must actually deliver that style or explain insufficient evidence.

## Stage 3: generate, review, and score correctly

### Mandatory item release checks

For every candidate, preserve a server-side evidence record tying each answer-determining proposition to an actual permitted passage. Include the exact source identifier, location, source version/hash, and the supporting text span. Validate spans against the supplied snapshot rather than trusting invented model quotations or plausible-looking URLs. Keep quotations short and preserve applicable attribution. An existing citation alone is not proof the claim is supported.

Evaluate the complete logical proposition: structure, relationship, laterality, region, condition, and any qualifiers. Do not confuse a nearby term match with support. Explain incorrect alternatives using evidence that actually rules them out for the stated lead-in; source silence is not a negative fact. For a table, check every answer-determining cell relationship. For a negative or multiple-correct item, validate every option's truth status under the stem, not just the keyed option.

Run three checks before release:

1. Deterministic schema, reference/span, option uniqueness, polarity, answer-count, table/combination, access, and scoring checks.
2. A fresh blinded solve/review using Gemma with the item and evidence but without the proposed key or generation rationale. It must derive the same exact answer set and identify any insufficient support or ambiguous alternatives.
3. An independent release verifier, `openai/gpt-oss-120b` through the same BullsAI gateway, given the item and exact evidence without the proposed key initially. Use structured per-item verdicts for evidence adequacy, derived answer set, and ambiguity. It may review a bounded batch to control latency. Require agreement on the key and no unresolved evidence/ambiguity issues before accepting an item. A confidence number or vague “looks correct” is not an acceptance condition.

A timeout, unavailable verifier, malformed verdict, invalid reference, disagreement, or insufficient evidence means the candidate is not eligible. Use bounded repair/replacement within the call budget; do not bypass a required verifier to avoid an empty result. Tell the student when a reliable complete quiz could not be prepared.

These model checks do not independently establish anatomical truth. Preserve instructor review status separately. Provide a “Professor-reviewed only” option that uses only explicitly approved item/source versions; when too few exist, explain that and do not silently substitute AI-generated items. The normal practice path must clearly distinguish AI-checked from professor-reviewed questions without presenting an approval badge that was never earned.

Use validated structured output with stable item/option IDs. Keep the private key, per-option reasoning, evidence mapping, and validation details on the server. Create a separate student-safe unanswered projection: prompt, options/table, selection instruction, and necessary non-revealing metadata. No answer keys, explanations, correct-option CSS/classes, hidden correctness fields, raw judge results, or instructor review text in the unanswered UI.

Each item needs: source scope, topic/objective, intended difficulty, dimensions, stem/lead-in, structured options, exact answer set, explanation, per-option rationale, anatomical evidence IDs/locations, writing-rule references, and review state. Keys must reference actual option IDs, not a model's unvalidated letter. Preserve answer mappings through shuffling, reruns, saving, and resume.

Generate original questions from evidence. Perform separate checks for:

- Source support of the key, relevant stem claims, explanations, and each distractor's incorrectness/relative inferiority for this specific lead-in.
- Clear, answerable lead-in; comparable plausible alternatives; no duplicates or giveaway wording/length/grammar; one best answer or exact multi-answer set as declared.
- Consistency of negative polarity, table cells, statement combinations, matching rules, and procedural sequence.
- Adequate support for exclusions: absence of an option from an incomplete passage is not proof it is false. Negative and multiple-correct items require explicit relationships, a source-supported complete set, or sufficient evidence to decide every option.
- Scope, grants, conflicting/withheld facts, source attribution, and safe serialization.

For single-best-answer items, alternatives may be less appropriate for the stated scenario rather than universally false. Explain that precisely. Never force invented rationales just to populate feedback.

Reject or repair a bounded number of invalid drafts; if insufficient eligible drafts remain, do not start an undersized or padded attempt. Follow the exact 5/10 fallback choice above. A model's self-review is not proof of correctness. Use all mandatory release checks, with professor review available for banking items.

Default scoring is one point per item: single-answer exact match; multiple-correct exact-set match, so checking everything earns no credit. State this before the quiz. Save answers and permit review/editing before final submission, without correctness hints. After final submission of all 5 or 10 questions, show the total and per-item results: the student's selection, the correct set, why each option is correct or incorrect for the stem, and the exact supporting passage(s). Do not invent negative marking or imply that this score predicts an examination result.

On that final review, link course answers to their actual lecture/section or guide/class/slide passages; link external answers to the Wikipedia article/section or other approved source actually used. Show source tier, external-source labeling, and provenance/retrieval date. Provide the frozen supporting excerpt so the student can compare the answer with its evidence. The NBME rule is writing-method evidence, not a substitute for anatomical evidence.

An answer key must be frozen before an attempt starts and must never be generated anew when the student presses Finish or changes a selection. If a student/professor reports a faulty question, retain the attempt for audit, quarantine the item from future reuse, and support reviewed invalidation with transparent score adjustment. Never silently rewrite an answer key or auto-approve a correction from an error report.

Avoid repetitions using stable IDs, content hashes, answer/objective comparisons, and bounded near-duplicate detection. Changing option order alone is not a new question. “Different questions” should vary learning objectives, supported scenarios, or relationships; on explicit expanded requests perform the Wikipedia retrieval described above. Prevent false promises of unlimited unique questions from thin evidence.

## Stage 4: Q&A integration

Ordinary factual Q&A stays a natural-language answer with citations and the new coverage/expansion logic. The NBME manual governs generated assessment writing; it is not an anatomy fact source or a reason to turn every Q&A answer into an MCQ.

When a student asks Q&A to “quiz me,” “ask me harder questions,” or produce MCQs, route to the same quiz engine. Carry topic and validated requested settings into the Quiz page with a clear action, or show an equivalent usable inline quiz with the same final-submission reveal behavior. Do not leak keys by generating a second, unvalidated quiz path in chat. Short requests such as “make them harder,” “different ones,” and “another five on the same topic” should use the active quiz context with grants enforced. A request for two more must explain that only five- or ten-question quizzes are available. Quiz-related helpers must not expose the active attempt's private keys, rationales, or source excerpts before final submission; ordinary independent Q&A retains its normal cited-answer behavior.

## Stage 5: UI and persistence

Keep the existing Vellum & Petrol theme and accessible native controls. The setup flow should be compact: material/topic, a 5/10 question-count selector, intended challenge, and styles, with secondary controls in an expander. Show whether practice is course-grounded, supplemented, or expanded from Wikipedia, and the actual review status. Before final submission, use source-category labels only where specific article titles or passages could reveal answers; detailed evidence belongs in final review. Explain an automatic external-source expansion briefly without requiring permission for every permitted lookup.

Show one item at a time, numbered progress, a clear single/multiple selection instruction, prominent negation, Save answer/Next, Back, Review answers, and Finish quiz. Before finishing, show unanswered items and let the student return to them; do not auto-submit because they reached the last item. Only final submission enables scoring and the source/explanation review. Handle loading, cancellation, retries, insufficient validated batches, empty results, and duplicate final submissions. On mobile, tables must retain column/row meaning with an accessible responsive presentation; avoid page-wide overflow and clipped option labels. Add keyboard and visible-focus checks, not screenshots alone.

Provide a final score, missed objectives, source-backed review, and a “Practice these topics again” action that creates genuinely new supported items. Do not promise exam success or medical validation.

Use per-user server-side storage for attempts, answer order, progress, and resume. Separate student-safe messages from private item keys and review metadata. Do not expose another user's attempts via IDs/caches; recheck grants when loading saved items. Do not mutate old attempt keys after a source update. Retain source/version provenance and explicitly handle inaccessible or obsolete items rather than silently substituting a new question.

Support professor inspection of generated items, evidence, and approval status using separate quiz-review records. AI-reviewed practice is not professor-approved; do not use `verified_fixes.jsonl` to fabricate approval. A professor preview must not count as a student's attempt. Apply existing retention conventions and document the actual persistence limits.

Do not rebuild the conversational Guide or introduce Wikipedia-derived dissection instructions. Preserve its source-only procedures, authoritative position, one-at-a-time checks, and readiness/completion separation.

## Stage 6: tests and real checks

Automated tests must mock network/LLM calls and verify:

- Shared evidence coverage for absent topics and partial gaps despite existing course hits; explicit harder/different/extra-topic requests trigger topical Wikipedia lookup; ordinary sufficient course answers avoid unnecessary external calls.
- Source order, access restrictions, public reference fallback without leaking ungranted text, withheld/conflict exclusion, URL/redirect allowlist, cache behavior, 429/timeouts, and no-result handling.
- Every implemented question style, including positive/negative single-answer, positive/negative multiple-correct, tables, matching, sequences, statement sets, and shared stems.
- Rejection of ambiguous keys, unsupported distractor rationales, missing negative evidence, duplicate options, wrong select-count instructions, invalid table cells, nonexistent source IDs, and out-of-scope generation.
- Exact-set scoring; no checking-all exploit; stable mapping across shuffle/rerun/resume; final-submit idempotency; no keys, score, correctness feedback, source passages, or revealing article metadata before whole-quiz completion, including direct handler calls, resume, and Q&A quiz-entry paths; full evidence revealed afterward.
- Exactly 5/10 items and no other sizes across UI, service, stored payload validation, and natural-language entry; matching/shared-stem prompts count toward the total; invalid counts and insufficient eligible drafts cannot start an attempt; ten-to-five fallback requires an explicit choice.
- All mandatory reviewers receive the correct evidence, blind solves do not receive the proposed key, derived answer sets must agree, invalid spans are rejected, and reviewer timeout/disagreement cannot be converted into acceptance. A professor-reviewed-only request must never receive unapproved or changed-version items.
- User isolation, cache/grant boundaries, changed sources, professor-preview behavior, bounded calls/retries/cancellation, insufficient-batch handling, frozen keys, item quarantine/invalidation, and natural-language settings/context.
- Existing Q&A and Guide regressions. Remove the existing `assert ... or True` in `tests/test_guide_chat.py` and make that state-validity check meaningful; do not weaken tests to make a result pass.

Run a small isolated live matrix with the actual gateway: a lecture-grounded set, a guide-grounded set, a topic verified absent from accessible local material, a partially covered topic, and an explicit harder/different expanded request. Include negative, multiple-correct, table, and scenario items. Exercise both a complete 5-question and a complete 10-question attempt, plus an intentionally insufficient-evidence request that must not start. Show which external lookup actually ran; do not simulate missing local coverage by merely choosing a random topic.

In addition to runtime release verification, the independent evaluation judge should review final accepted items with their keys and exact evidence, and separately assess answer support, alternative ambiguity, polarity, distractor reasoning, and writing quality. Inspect failures manually; do not dismiss them solely as judge disagreement. An accepted item with a known unresolved support/key problem blocks completion of that case until repaired or excluded. Record raw structured results privately in evaluation artifacts, not student output. Report accepted/rejected/repaired counts and remaining uncertainty. This is a small internal check, not an accuracy benchmark or a zero-error guarantee.

Use sandbox accounts for a full-access student, a guide-only student, and a student with no course grants using a public topic. Inspect actual desktop/mobile UI, a keyboard-only answer path, and contrast for any new combinations. Capture the 5/10 setup, normal MCQ, negation, multiple-correct, table, pre-final answer review without correctness/source disclosure, expanded-source labeling, insufficient-evidence state, and final results with actual source excerpts/links. Do not publish screenshots containing personal student data.

## Deliverables

- Working enabled Quiz with exactly 5/10 questions, strict release verification, whole-quiz final-submission source reveal, shared Q&A evidence expansion, all requested MCQ styles, and honest source/review labels.
- Original NBME PDF preserved plus extracted page-aware writing rules and updated reference/integration documentation. The reference note's previous “not implemented” section should reflect completed integration.
- Current build status; full-suite result; live evaluation with evidence, actual source lookups and limitations; screenshots; protected-file comparison; running app URL.
- A concise final report distinguishing completed, tested, and unverified behavior. Do not claim a 10,000-item bank, NBME endorsement, clinical accuracy, deployment, or improved exam outcomes.

Complete the bounded implementation and checks before reporting. Do not leave placeholder buttons for requested question styles.
