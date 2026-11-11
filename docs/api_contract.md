# AnatoVision API contract (single source of truth for backend and front end)

Base path: /api. JSON everywhere. Auth uses an httpOnly session cookie (12 h), so a reload does NOT sign the user out. In development, Vite proxies /api to http://localhost:8000 (same origin).
Errors: every non-2xx response is {error: string} where error is a message fit to show the user.

## Auth
- POST /api/auth/login {username, password} → {user: {id, name, role: "student" | "instructor"}}. Wrong login → 401 {error}.
- POST /api/auth/logout → {ok: true}
- GET /api/auth/me → {user, preview} or 401. `preview` is null, or {profile: "full" | student_id, name} while an instructor is previewing (added so a page reload can show the preview bar).
- Login is throttled: 5 failures for one username, or 20 from one address, in 5 minutes → 429 {error}. A session lasts 12 h from login.

## Scope (what this student may use)
- GET /api/scope → {lectures: [{id, title, granted}], guides: [{id, class_number, title, lecture_ids: [], granted}]}

## Chats
- GET /api/chats → [{id, title, updated_at}] (newest first; the UI groups them into Today / Yesterday / Previous 7 days / Older)
- POST /api/chats → {id, title: "New chat", updated_at}
- GET /api/chats/{id} → {id, title, messages: [Message]}. A saved answer's notes / guide source that the revised notes changed or removed has `revision: "updated" | "removed"` (additive; null otherwise): the app shows "Source updated" / "Source removed" beside it.
- PATCH /api/chats/{id} {title} → {id, title}
- DELETE /api/chats/{id} → {ok: true}

## Ask
POST /api/ask {chat_id, question (max 600 characters), length: "brief" | "detailed", lecture_ids?: [], body_type?: string, request_id?: string} → Message
`body_type` (added, optional) is the cadaver body type the lab asks for first, exactly "<more|average|less> fat, <more|average|less> muscle, <large|average|small> build"; anything else → 422. `lecture_ids` only narrows the student's own grants, it never widens them. The body type is used in LAB answers only (the ordered-steps answer for a how-to question): they may add one "For this body type:" line tied to a step that a source mentions fat, fascia, muscle or depth for, and up to two lines starting "General tip, not from your notes:" (no citation, general anatomy knowledge). A concept answer ignores it, and "average fat, average muscle, average build" changes nothing.

- Progress (added, optional): send a client-made `request_id` ([A-Za-z0-9_-], max 64) with POST /api/ask and poll `GET /api/ask/status/{request_id}` → {stage: "searching" | "reading" | "writing" | "checking" | "done"} about once a second. Only the stage word is returned (it never goes backwards, and no answer text is ever streamed): the answer arrives whole in the POST response, after the student-safe layer. The status is 404 until the POST has registered the id (show "searching"), for another user's id, and two minutes after the answer. POST /api/ask without `request_id` works exactly as before.

Message:
```
{
  id, role: "user" | "assistant", created_at,
  kind: "answer" | "term_lookup" | "not_covered" | "refused" | "error",
  markdown,                       // answer text; citation markers look like [1], [2]
  sources: [Source],
  footer: { basis_line, access_note } | null,
  timing_ms
}
Source = {
  n,                              // the number used in the [n] markers
  type: "notes" | "guide" | "openstax" | "wikipedia" | "web" | "verified_fix",
  title,                          // e.g. "Lecture notes", "OpenStax Anatomy & Physiology 2e, section 11.6"
  subtitle,                       // e.g. "Lecture 08, Anterior and Medial Thigh" or "Class 17, slide 12"
  lecture_id,                     // lecture this source belongs to, or null (used by "Quiz me on this")
  url,                            // public link or null (notes and guides have none)
  snippet,                        // passage text shown in the source panel
  retrieved_at,                   // web sources only, else null
  license,                        // "CC BY-SA 4.0" (Wikipedia), "CC BY-NC-SA 4.0" (OpenStax), else null
  revision                        // "updated" | "removed" | null: an OLD answer's notes / guide source that the revised notes changed or removed
}
```
Message rules (as built):
- The student's own question is also a Message: role "user", kind "answer", sources [], footer null, timing_ms 0. Message ids are "<chat_id>:<n>", n = position in the chat from 0 (the question is 0, its answer 1).
- `[n]` markers in `markdown` always have a Source with that `n`; a marker is never printed without one.
- A withheld line shows only the sentence "Dr. Inglis is reviewing this line. Check with him before relying on it." A doubtful line is followed by the italic sentence "Check before relying on this line."; a corrected line by "Dr. Inglis corrected this line." (the contract has no field for these, so they live in the markdown).
- kind: "refused" = treatment, dosing, diagnosis or off-topic; "not_covered" = nothing in the material the student may use; "error" = the model could not answer or the session limit was reached.
- Source for notes: title "Lecture notes" (no name), subtitle "Lecture 08, Anterior and Medial Thigh" plus " › <section>" when the section differs. Guides: title "Dissection guide", subtitle "Class 17, slide 12", lecture_id of the matched lecture (null if no lecture matches). verified_fix: title "Verified correction", subtitle "<who>, <date>", snippet = the corrected text.
- footer.basis_line is "Based on OpenStax and Wikipedia, not Dr. Inglis's notes." when no notes/guide/verified text was used; footer.access_note is the short "notes for this are in Lecture 08, which you don't have yet" line. footer is null when both are empty.
- POST /api/messages/{id}/flag {reason, comment?} → {ok: true}. Goes to the professor's queue (type student_report). `reason` may be free text (max 500); one of the five standard reasons is stored as is, anything else is stored as "Something else" with the text as the comment.
- "Explain simpler" in the UI is just POST /api/ask with question "Explain this more simply: <snippet>" and length "brief" (no new endpoint).

## Guide (dissection guides)
Station `index` is 0-based (the Streamlit Guide numbers the same stations from 1).
- GET /api/guides → [{id, class_number, title, region, station_count, granted}]
- GET /api/guides/{id}/stations → [{index, title, steps: [text], slides: [int], image_only: bool}]
- POST /api/guides/{id}/stations/{index}/check {description (max 1000), body_type?: "lean" | "average" | "more_fat" | "more_muscular" | "not_sure"} → {verdict: "correct" | "partly" | "not_matching", feedback_markdown, sources: [Source]}
  `sources` holds the station's own slide text (type "guide"). A picture-only station (image_only: true) has no text to compare with, so it answers 422 {error} without calling the model; a judge that cannot run answers 502 {error}. Students outside the guide's grants get 403.
- Body type in the Guide (additive): the app asks the cadaver's body type when a guide is started or resumed and saves it per guide. `body_type` on the check is the saved choice; when it is neither average nor "not_sure" the judge may add ONE sentence after its feedback that ties the body type to the station (in the guide's own words if the slide text mentions fat, fascia, muscle or depth, otherwise a line starting "General tip, not from your notes:"). The verdict is judged on the slide text only.
- GET /api/guides/{id}/stations/{index}/body-tip?body_type=<lean|average|more_fat|more_muscular|not_sure> → {body_type, lines: [{text, general}]}: a short note for that station and body type (at most 3 lines; `general: true` lines start "General tip, not from your notes:" and are not from the guide). Empty `lines` for a picture-only station, for average / not_sure, or when nothing applies. 422 for another body type, 502 if the note could not be written.
- Guide history (additive; sidebar "Guide history"): GET /api/guide-history → [{id, kind: "guide" | "lecture", ref, title, station, count, updated_at, body_type: string | null, notice: string | null}] (newest first; `id` is "guide:class-17" or "lecture:<lecture id>", `station` is the 0-based station reached, the furthest one is kept). PUT /api/guide-history {kind, ref, station, body_type?} → {ok: true} records (and, when `body_type` is given, saves the body type chosen for that guide; omitted = kept as it was) that the student opened that station (404 / 403 if the guide or lecture does not exist or is not open to them, 422 for a station that does not exist). DELETE /api/guide-history/{id} → {ok: true} removes one of the student's own items (another student's item is a 404). A preview lists nothing and saves nothing.
- Lecture-notes sample mode: GET /api/lectures/{id}/stations, same shape (`slides` is [], `image_only` false; the lines are the notes with withheld/doubtful/corrected handling applied). No check endpoint: the sample walk-through is read-only here.
- Ids: a lecture id is the notes' lecture_id (e.g. "L09-the-hand"); a guide id is "class-NN" (zero-padded), plus "-<title>" where two guides share a class number (e.g. "class-33-the-orbit"); region is derived from the guide's title ("Back", "Upper limb", "Lower limb", "Thorax", "Abdomen", "Thorax and abdomen", "Head and neck", else "Other").

## Quiz (wraps src/quiz/service.py; key, explanations and evidence are NEVER sent before submit)
Building a quiz can take a while (reuse first, then generate and verify), so it runs as a job:
- POST /api/quiz/build {mode: "materials" | "topic", lecture_ids?: [], guide_ids?: [], topic? (max 80 chars), n: 5 | 10, reviewed_only: bool, continue_quiz_id?: null}
  → {job_id}
- GET /api/quiz/jobs/{job_id} → {done: bool, have, requested, note, result: BuildResult | null}
  BuildResult = {status: "ready" | "offer" | "partial" | "failed", reason, quiz_id | null, have, requested, message}
  Only one build per user runs at a time (a second POST answers 409). `continue_quiz_id` is the id of a waiting 5-question offer: it is dropped and the missing questions are looked for. Lecture/guide ids must be open to the user (403) and exist (422); a topic is 3 to 80 characters.
  ready → open the quiz. offer → "X of 10 ready": buttons "Start with 5", "Continue preparing", "Discard". partial/failed → show message and "Continue preparing" when have > 0.
- GET /api/quiz/latest → {id, status: "open" | "offer", length, answered} or null (shows "Resume quiz")
- POST /api/quiz/{id}/accept → {ok: true}   (accept a 5-question offer)
- DELETE /api/quiz/{id} → {ok: true}         (discard)
- GET /api/quiz/{id} → OpenQuiz = {quiz_id, length, current, answered, questions: [{stem, lead_in, selection_mode: "single", options: [{id, text}]}], selections: {"0": ["B"], ...}}
- PUT /api/quiz/{id}/answers/{index} {option_ids: ["B"]} → {ok: true, answered}
- PUT /api/quiz/{id}/current {index} → {ok: true}
- POST /api/quiz/{id}/submit → Results (scores the whole quiz; unanswered = wrong)
- GET /api/quiz/{id}/results → Results (403/409 {error} if not submitted)
  Results = {quiz_id, score, length, submitted, questions: [{n, stem, lead_in, options: [{id, text}], selected: [], answer_ids: [], correct: bool,
             explanation, alternatives: {option_id: why_wrong}, evidence: [{id, label, tier, url, visible, text, license}], label, review_status,
             spans: [{source_id, span}]}]}   // spans (added): the supporting lines to highlight inside evidence[].text
  An open quiz (the response of GET /api/quiz/{id}) never carries answer_ids, explanation, alternatives, evidence or spans. Errors: 404 not found / not yours, 403 a lecture or guide of the quiz is no longer open to the user, 409 wrong state (not open, already submitted, results before submit).
- GET /api/quiz/history → [{id, score, length, submitted, title, web}] (newest first, at most 50). `title` is the topic ("Femoral triangle") or the lecture / guide names ("Anterior and Medial Thigh +1"); `web` is true when at least one question was built from the web.
- DELETE /api/quiz/history/{id} → {ok: true} removes one finished quiz from the student's own history (another student's quiz, or one that is not finished, is a 404). `DELETE /api/quiz/{id}` still discards an unfinished quiz or offer.
- Web questions (additive): in "topic" mode, when the course material cannot supply enough evidence, questions are built from Wikipedia (the only approved web source; BullsAI writes and checks them like any other). Such a question has `web: true` and `source_note: "Not from course notes"` in OpenQuiz.questions[] and in Results.questions[]; its evidence entry has the Wikipedia `url` and `license: "CC BY-SA 4.0"`. With `reviewed_only: true` nothing is built from the web and no web question is used (the failure message says so). Every other question has `web: false`, `source_note: null`.

## Instructor only (403 for students)
- GET /api/admin/stats → {questions_7d, flagged_open, web_answers_7d, review_counts: {confirmed_factual, doubtful, wording, typo, start_here}, bank_counts: {total, draft, approved, retired, exam_secure, flagged, needs_recheck} | null (additive)}
- GET /api/admin/review?type=&status=&lecture=&page= → {items: [{id, type, status, lecture, section, original_text, ai_note, sources: [Source]}], total}
  type: confirmed_factual | doubtful | wording | typo | start_here | student_report (empty = all). status: open | verified | dismissed | changed | decided (= verified or dismissed). `changed` (additive) = the quoted line is no longer in the revised notes: the item shows the new wording as a second source and cannot be decided (409). lecture: a lecture id or title. page: 1-based, 25 per page. Items are AI suggestions until decided; a student_report item is a student's "Report an error" (original_text = the answer they saw, ai_note = who and why).
- POST /api/admin/review/{id} {action: "verify" | "dismiss", fix_text?} → {ok: true}
  verify needs fix_text (422 without): it is recorded as Dr. Inglis's verified fix, the same function as the dashboard (`confirm_error` for facts, `reword` for wording/typos), and students then see it in place of the line. dismiss = "the notes are correct as written". A student_report can only be dismissed (marked handled). Already decided → 409.
- GET /api/admin/questions?web=&flagged=&page= → {items: [{id, student, question, kind, web, flagged, created_at, message}], total}
  web/flagged are true/false filters (flagged = the student reported the answer). `message` is the answer as the student saw it (null if the student deleted the chat). Preview questions are never listed.
- GET /api/admin/web-quizzes?page= → {items: [{id, student, title, status, score, length, web_questions, sources: [{title, url, license}], created_at}], total}: every student quiz with at least one question built from the web, newest first (preview quizzes are never listed; 25 per page).
- GET /api/admin/students → [{id, name, username, lecture_ids, guide_ids}]
- PUT /api/admin/students/{id}/access {lecture_ids, guide_ids} → {ok: true}
- POST /api/admin/preview {profile: "full" | student_id} → {ok: true}; starts preview-as-student. POST /api/admin/preview/exit ends it (also ends with logout).

## Notes manager (instructor only; 403 for students on every route; additive)
Uploads, previews, publishes, edits, versions, archives and purges lecture notes and dissection guides. The AI parses, maps and flags; it never edits text. The instructor approves everything. Every change to the live data goes through one staged copy -> quick retrieval check -> backup -> swap, and the running search is reloaded. Statuses: `draft | processing | ready | published | archived` (a published document can also have a waiting new version: `has_pending`).
- GET /api/admin/notes?kind=&region=&status=&q= → {items: [{id, kind: note | guide, title, region, version, status, updated_at, access_count, note, earlier_version}], regions, total}. Includes the existing revised notes and guides (Published), the first-version files (Archived, read-only) and the earlier Lecture 17 (`earlier_version`).
- POST /api/admin/notes (multipart: file, kind?, replaces?) → {doc_id, version}. .docx, .doc, .pptx or .pdf; type, magic bytes and size are checked (422 / 413); the original is kept untouched under data/raw/notes_managed. The processing job then runs in the background (poll the detail below; `job` = {status, step, step_index, steps, error, version}). A .doc is converted to .docx with LibreOffice when it is installed (otherwise it is refused with a plain message). Publishing a new file for a dissection guide renders its slide images again and sends its approved image marks back to draft.
- GET /api/admin/notes/{id} → {id, kind, title, region, status, version, live_version, shown_version, created_at, updated_at, replaces, replaces_title, overlap: {doc_id, title, score, shared_sections, sections, suggest_replace} | null, job, sections: [{path, text}], mapping: {region, lecture, title}, flags: {count, items}, diff: {against, counts, rows} | null, archived_at, purge_after, grants_mode, has_pending, editable, regions, lectures}. The AI's flags are for the review queue once published.
- PATCH /api/admin/notes/{id}/mapping {region?, replaces?, lecture?} → {ok}. The instructor edits the region, the document this one replaces, or a guide's lecture.
- POST /api/admin/notes/{id}/replace (multipart: file) → {doc_id, version}: a new version of this document (409 if one is already waiting).
- POST /api/admin/notes/{id}/publish {access: all | selected | none | same, students?} → {doc_id, version, granted, flags_added, fixes_to_recheck, progress_moved}. `access` applies to a first publish (`same` copies the grants of the document it replaces, which is then archived). 409 if nothing is ready; 409 if the quick retrieval check fails (nothing is changed).
- POST /api/admin/notes/{id}/discard → {ok}: drops the waiting version (or a never-published document).
- PUT /api/admin/notes/{id}/sections {edits: [{index, text}], note?} → {doc_id, version, ...}: the in-browser editor; saves a NEW version and publishes it. Notes only (a guide is changed with Replace file: 409).
- GET /api/admin/notes/{id}/versions → [{version, status, created_at, created_by, note, n_sections, source_name, diff}]; GET /api/admin/notes/{id}/versions/{n}/diff → {against, counts, rows}
- POST /api/admin/notes/{id}/rollback {version} → {doc_id, version}: a new version holding the old text.
- POST /api/admin/notes/{id}/archive → {doc_id, restorable_until}: removed from answers at once; POST /api/admin/notes/{id}/restore within 30 days (409 after); POST /api/admin/notes/{id}/purge {confirm_title} → {ok}: archived only, the exact title must be typed (422); deletes versions and originals, keeps the audit log.
- GET /api/admin/notes/{id}/audit → [{at, user, action, detail}]
Knock-on effects of a change: linked fact-check items become `changed` (the quote is gone) or `unchanged` / `moved`; verified fixes whose line is gone get `needs_recheck`; saved chat answers show `revision` "updated" / "removed"; a student's place in a guide is mapped by content (with a `notice`).

## Question bank (instructor only; 403 for students on every route; additive)
The instructor's own questions, and the AI / web questions students' quizzes produce (saved as draft). Stored in data/question_bank/bank.db with full version history. A question is {stem, lead_in, options: [{id A-E, text}] (2 to 5), answer, explanation, lecture, guide, section, region, tags, difficulty: "" | easy | medium | hard, source: instructor | ai | web | imported, status: draft | approved | retired, use: practice | exam_secure, objective}.
Students never see the bank. A quiz uses only status approved AND use practice (plus AI / web questions saved as draft that the instructor has not retired or made exam_secure, labelled AI-checked); `reviewed_only` quizzes use approved + practice only. Exam-secure questions are never served and AI questions too close to one are thrown away.
- GET /api/admin/bank?status=&use=&source=&region=&difficulty=&lecture=&tag=&q=&flagged=&page= → {items: [{id, lead_in, stem, status, use, source, lecture, region, tags, difficulty, version, updated_at, flagged, n_flags, needs_recheck, sample, used}], total, counts: {total, draft, approved, retired, exam_secure, flagged, needs_recheck}, lectures, regions, tags} (50 per page)
- GET /api/admin/bank/export.csv?(same filters) → the filtered questions as CSV. GET /api/admin/bank/template.csv and GET /api/admin/bank/template.xlsx → the import template.
- POST /api/admin/bank/import/preview (multipart: file, or import_id + mapping JSON) → {import_id, filename, headers, rows (first 5), n_rows, mapping: {field: header}, fields, questions (first 8 as they would be created), problems, duplicates, ready}. CSV, XLSX or Word (.docx numbered questions); any column layout: the suggested mapping can be changed and previewed again before anything is created.
- POST /api/admin/bank/import/commit {import_id, mapping, status = draft, use = exam_secure, skip_duplicates = true} → {created, skipped_duplicates, problems, flagged}. Instructor imports default to draft + exam_secure; near-duplicates (60% of content words) are flagged, near-identical ones (90%) skipped.
- POST /api/admin/bank → BankDetail (create); GET /api/admin/bank/{id} → {id, version, created_at, updated_at, data, sample, flags: [{kind: nbme | key | duplicate | tag | stats, code, severity, message, dismissed}], needs_recheck, stats: {n, p_correct, discrimination, enough, distractors: [{text, picks, correct}], min_for_stats, min_for_flags}, comments, versions: [{version, at, by, note, changed}]}; PUT /api/admin/bank/{id} (edit: a new version, rule checks re-run).
- POST /api/admin/bank/{id}/restore {version} (a new version holding the old data); POST /api/admin/bank/{id}/comments {text}; POST /api/admin/bank/{id}/check (AI checks: item-writing flaws, near-duplicates, link to the notes by content (empty fields only), answer-key check against the notes); POST /api/admin/bank/{id}/flags/dismiss {kind, code, dismissed}; POST /api/admin/bank/{id}/recheck (after the notes changed: refresh the links and clear "needs re-check").
- POST /api/admin/bank/bulk {ids, action: approve | retire | draft | set_use | add_tag | remove_tag | run_checks, value} → {changed}.
Flags only: nothing here changes a question's status or text on its own. Statistics (times used, % correct, discrimination, distractor picks) come from submitted student quizzes; flags need at least 20 attempts and never retire anything. When the Notes manager changes or archives a section a question cites, the question gets `needs_recheck`.
POST /api/quiz/build gains `different_style: bool` (additive, default false): new AI questions copy the style of approved practice questions unless the student asks for a different style.

## Guide pictures and step-by-step marks (additive)
Each guide slide is rendered (LibreOffice) and cropped to its anatomy picture(s): the pptx picture shapes plus the label, arrow and line shapes touching them; step text, headers, footers and logo / closing slides are left out, text-only slides get no picture, several pictures on a slide are separate crops in reading order, and a slide that is one flattened picture is cropped by image analysis (always low confidence). Crops are WebP, at least 1600 px on the long side, with thumbnails, under data/processed/guide_images/<guide_id>/ (git-ignored). Nothing is AI-generated.
- GET /api/guides/{id}/slides/{n}/crops/{k}/image and GET /api/guides/{id}/slides/{n}/crops/{k}/thumb → image/webp. There is no public URL: signed-in users only (401 otherwise), and only for a guide the user may open (403 otherwise; an instructor may open every guide); 404 for a picture that does not exist, and for a student, a LOW-confidence crop the instructor has not yet marked checked. Responses are `private`, `noindex`.
- GET /api/guides/{id}/slides/{n}/original → image/png: the whole slide, INSTRUCTORS ONLY (403 for a student, even one who may open the guide), for "View original slide" in the editor.
- Each station in GET /api/guides/{id}/stations has `images: [{slide, crop, url, thumb_url, caption, alt, w, h, marks}]`: the pictures of the station's slides in slide order (an image-only station shows its picture). `caption` is "Slide N · Dr. Inglis's dissection guide" (+ " (picture k of m)" when a slide has several). `marks` are APPROVED marks only: [{id, slide, crop, kind: arrow | cut | highlight | label, geom, text, step, n}]. Coordinates are normalised 0-1 on the CROPPED picture (x from the left, y from the top): arrow {from: [x, y], to: [x, y]}, cut {points: [[x, y], ...]}, highlight {cx, cy, rx, ry}, label {x, y} (+ `text`). `step` = the 0-based step of the station (null = shown with every step). Students never receive draft or flagged marks, authors, versions or the confidence of a crop.
- POST /api/guides/{id}/stations/{index}/explain {body_type?} → {text, label: "AI explanation, check your guide", sources}: "Explain simply", at most 4 short sentences from the station's own text and the lecture notes the student may open only (a number that is not in them rejects the answer; 502 if nothing safe could be written). Student tool (403 for an instructor without a preview); 422 for a picture-only station.
- Message (POST /api/ask, GET /api/chats/{id}) has `images: [{...picture fields, guide_id, source_n, step, marks}]`: a procedural answer (two or more numbered steps) gets one card per cited guide step (at most 8), a concept answer at most one; only for guides the student may open (otherwise `images` is []). A card carries the approved marks of its picture, narrowed to its step.
- Instructor only (403 for students): GET /api/admin/guides/{id}/annotations → {guide_id, title, rendered, stations: [{index, title, steps, slides, image_only, drafts, approved, images: [{..., confidence: high | low, why, reviewed, original_url, marks: [{id, slide, crop, kind, geom, text, step, n, status: draft | approved, author, version, source: manual | auto | ocr, flag}]}]}]}; POST /api/admin/guides/{id}/marks {slide, crop?, kind, geom, text?, step?} → mark (always a draft); PUT /api/admin/guides/{id}/marks/{mark} {geom?, text?, step?} → mark (a real change sends an approved mark back to draft and clears a flag when the geometry changed); DELETE /api/admin/guides/{id}/marks/{mark} (removes it); POST /api/admin/guides/{id}/marks/reorder {slide, crop?, ids}; POST /api/admin/guides/{id}/stations/{index}/approve {approve: true | false} → {changed} (flagged marks are never approved in bulk); POST /api/admin/guides/{id}/slides/{n}/crops/{k}/review {ok} marks a low-confidence crop as checked (students see it only then). Marks read from the instructor's own slides (arrows, lines, ellipses, label text boxes; shape rotation applied) have source `auto`; labels found by OCR in the pictures (with an arrow where a leader line is seen) have source `ocr`. Both are drafts and are never approved automatically. Older marks made on the whole slide are moved onto the crops; one outside every crop becomes a flagged draft.
- GET /api/admin/notes/{id} has `guide_id` (additive): the guide's id for its pictures and marks, or null.

## Instructors and the student tools
Chats, ask, guide checks and the quiz are student tools. An instructor gets 403 {error} on them until a preview is started; during a preview they act exactly as that student (same grants, same student-safe output) and:
- chats are throw-away (ids start "preview-", kept in memory, GET /api/chats is [], nothing in the chat database), and flagging saves nothing;
- the question is logged as `professor_preview`, never as student usage;
- quizzes are the one thing kept: under the name "preview:<instructor>" (a quiz cannot work without saving its answers), never under the student's name.
GET /api/scope and GET /api/guides are readable by instructors without a preview (everything granted) so the access screen can list them.

## Errors and security
- Every non-2xx body is {error: string}: 400 bad request, 401 not signed in / wrong login, 403 not allowed (instructor-only, closed lecture, cross-site write), 404 not found (also for another user's chat or quiz), 409 wrong state, 422 invalid input, 429 too many logins, 502 the AI service failed, 500 anything unexpected (no detail).
- The session cookie is httpOnly, SameSite=Lax, path /, 12 h (Secure when API_COOKIE_SECURE=1). A POST/PUT/PATCH/DELETE with an Origin header from another site is refused. CORS allows only http://localhost:5173 and only while APP_ENV=development (the default); in production serve the front end and /api from one origin.
