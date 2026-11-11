Build the complete front end for "AnatoVision", an anatomy lab assistant for medical students and their professor. FRONT END ONLY.

STACK: Vite + React + TypeScript + Tailwind + shadcn/ui + lucide-react + react-markdown (remark-gfm) + framer-motion + recharts. Do NOT use Supabase, do NOT add any database, auth provider, edge function or backend. All data goes through ONE file, src/lib/api.ts, with a typed function per endpoint. If VITE_USE_MOCK is "true" (default) those functions return realistic mock data from src/lib/mock.ts with a 600 to 1,200 ms delay; otherwise they call fetch(`${import.meta.env.VITE_API_URL ?? ""}/api/...`, { credentials: "include" }). Types live in src/lib/types.ts and must match the API CONTRACT below exactly. Vite dev proxy: /api -> http://localhost:8000.

==================== LOOK AND FEEL ====================
Concept: a calm, modern study app with the quiet character of an anatomy textbook. Minimal. Every element must earn its place. It must NOT look AI-generated or templated.

NEVER use: gradients, glassmorphism, glow, blur backgrounds, emoji, sparkle or "AI" icons, purple/indigo, hero sections, marketing copy, testimonial cards, left-border accent cards, avatar circles on assistant messages, animated backgrounds, all-caps labels.

LAYOUT: three columns on desktop. Left: a DARK warm sidebar (272 px). Middle: LIGHT bone chat area (reading column max 700 px, centered). Right: a light source panel (360 px) that opens when a citation is clicked and closes with X or Esc. Tablet: source panel becomes an overlay sheet. Phone (390 px): sidebar becomes a drawer, source panel becomes a bottom sheet.

COLORS (CSS variables in index.css, light theme; also provide a dark theme that keeps the same hues):
- Sidebar: bg #2C2622, text #F4EFE6, muted #D2C7B8, faint #C9BEAF, border #463D36, active accent #F0B3AC, logo accent #E08C84
- Page bg (bone) #F4EFE6; surface #FBF8F2; surface-2 #F1EADF; sunken #ECE5D8
- Ink #1E1A17; body-2 #4A433C; muted #6B6259
- Border #DDD3C2; border-strong #D6CBB8
- Accent (oxblood) #8A2D2A; accent-hover #6E2220; accent-soft #EADBD3 (text on it #6E2220)
- User message bubble: bg #2C2622, text #F4EFE6
- Verdicts: correct #2E6B4F on #DCEBE2; partly #7A4F12 on #F6E7C8; not matching #8A2D2A on #EADBD3 (always with a text label, never color alone)
- Dark theme: page #1B1715, surface #24201C, surface-2 #2C2622, ink #EFE7DA, muted #B3A898, border #3A332D, accent #E08C84, sidebar #141110
Red is ONLY for small accents: citation chips, send button, active tab underline, current-chat dot. Never big red areas.

TYPE: Inter for UI and body (15 px UI, 16 px answer text, line-height 1.6). "Source Serif 4" for the logo, page/chat titles, answer section headings ("Boundaries") and the italic section labels (Today, Yesterday, "Source 1 of 2", "Anatomy lab assistant"). No all-caps.
SHAPE: radius 10 to 18 px, 1 px borders, very soft shadows only on the composer and floating buttons. Icons lucide at 16 px, stroke 1.5.

MOTION (smooth but quiet; disable all of it under prefers-reduced-motion):
- New messages fade in and rise 8 px (framer-motion, 200 ms ease-out). The answer text appears progressively (reveal by paragraph), never a blinking cursor.
- Chat sticks to the bottom while an answer arrives; if the user scrolls up, a small "↓ Latest" pill appears and scrolls back smoothly.
- Source panel, drawers and sheets slide in with a gentle spring. Mode switches crossfade (150 ms). Lists use layout animations when items are added or removed.
- Loading = three quiet pulsing dots for answers, skeleton shimmer shaped like the content for lists. Never a blank spinner page.
- Buttons: 150 ms color transitions, visible focus rings (2 px accent outline, offset 2).

==================== SCREENS ====================
1. LOGIN: bone page, centered card on surface: wordmark "Anato" + "Vision" (Vision in oxblood) in Source Serif 4, italic subtitle "Anatomy lab assistant", username, password, "Sign in" (oxblood). Wrong login shows an inline error. Footer: "For students and instructors of the Human Anatomy Lab."

2. STUDENT SIDEBAR (dark, top to bottom):
- Wordmark (Vision in #E08C84) and italic subtitle.
- Mode tabs as underlined text tabs: Ask, Guide, Quiz. Active tab: text #F4EFE6, 2 px underline #F0B3AC. Inactive: #D2C7B8.
- "New chat" button: full width, pill, CREAM fill #F4EFE6, ink text, small oxblood "+" icon, subtle shadow. It is the most visible thing in the sidebar.
- In Ask mode: chat history grouped by italic serif labels Today / Yesterday / Previous 7 days / Older. Current chat: bold with a small #E08C84 dot; others indented, #E9E1D4. Hover menu per chat: Rename, Delete (confirm dialog). Muted note "Chats are kept for 90 days".
- Above the user row: ONE quiet "Continue guide" card (only when a guide was started; remember last guide + station in localStorage, wrapped in try/catch): label "Continue guide →", title "Class 17 · Hip and Knee", a thin 12-segment progress spine (filled segments #F0B3AC, empty #4F453D). Click resumes that station.
- Bottom: user avatar initials (cream circle) + name, menu with "Sign out".

3. ASK (chat):
- Header: chat title in Source Serif 4, right side italic muted lecture label when the chat is scoped (e.g. "Lecture 08").
- Empty state: Source Serif greeting "What would you like to know?" and 4 quiet example rows (not colorful chips): "What are the boundaries and contents of the femoral triangle?", "apex", "How do I expose the femoral triangle?", "What is the nerve supply of the hypothenar muscles?".
- User message: right-aligned bubble (#2C2622 bg, cream text, radius 16).
- Assistant answer: NO bubble, NO avatar; plain markdown on the page. Headings in Source Serif 4. Citation markers [1] render as small rounded number chips (accent-soft bg, #6E2220 text); the chip of the source currently open in the panel is solid oxblood with white text. Clicking a chip opens the source panel at that source.
- Under the answer: source pills in a row ("1 · Lecture notes · L08", "2 · OpenStax 11.6 ↗"), round number badge inside each pill; then footer lines (basis_line, access_note) in small muted text if present; then quiet text actions: Copy, Flag (dialog with a reason box).
- Kinds: not_covered and refused render as a calm bordered note on surface with an info icon (no red); term_lookup renders like an answer; error shows the message and a "Try again" button.
- COMPOSER at the bottom: one rounded card (surface #FBF8F2, border-strong, radius 18, soft shadow). Auto-growing textarea "Ask about a structure, region or dissection step". Bottom row: Brief/Detailed pill toggle (active = dark #2C2622 pill), "All lectures ▾" pill (popover with checkboxes from /api/scope, locked items show a lock and "Ask your instructor"), counter "0 / 600" (turns warning color at 550), round oxblood send button. Enter sends, Shift+Enter new line.

4. SOURCE PANEL (right): top row italic "Source 1 of 2" with ‹ › arrows and ✕. Title in Source Serif 4 24 px: for notes it is just "Lecture notes" (never the professor's name); subtitle "Lecture 08 · Anterior and Medial Thigh". The snippet in a surface-2 rounded block, Source Serif 4 16 px. Small definition list: Type ("Course notes", "Dissection guide", "OpenStax", "Wikipedia", "Web", "Verified fix") and Link ("Not public" or an "Open ↗" link), plus license and retrieved date when present. NO illustrations. At the bottom, separated by a hairline: "In this answer" list of all sources (number in oxblood + short title; current one highlighted on surface-2), and two equal outline buttons "Explain simpler" (sends "Explain this more simply: <snippet>" as a brief question in the same chat) and "Quiz me on this" (switches to Quiz and builds a 5-question quiz from that source's lecture_id; hidden when lecture_id is null).

5. GUIDE:
- Picker: guides grouped by region (Back, Upper limb, Lower limb, Thorax, Abdomen, Head and neck) as simple surface cards: italic "Class 17", serif title, "12 stations". Locked cards are faded with a lock and "Ask your instructor". A secondary tab "Lecture notes (sample)" lists lectures the same way with a note "Sample mode: built from the lecture's own order, not a dissection procedure."
- Station view: in the sidebar, the station list replaces chat history, drawn as a vertical "spine" of small rounded vertebra segments (done = filled #F0B3AC, current = outlined and highlighted, upcoming = faint outline) with the station names. In the main area: "← All guides" and "Class 17 · The Hip and Knee Joints"; a horizontal 12-segment vertebra progress bar with "Station 3 of 12"; italic serif "Station III"; serif title 32 px; numbered steps with small outlined number circles; slide chips "Slide 12"; image-only stations show "See slide 14 in your lab guide". Then label "Describe what you see or what you did", a textarea card with a "Check" button (oxblood). Feedback card: verdict pill (Correct / Partly / Not matching), feedback markdown with citation chips, sources line. Buttons: "Back" (outline) and "Next station →" (oxblood).

6. QUIZ (real, not a placeholder; follows the quiz endpoints exactly):
- Setup: serif title "Quiz". Choice "My lectures and guides" / "A topic" as a two-option segmented control. Materials mode: multi-select of granted lectures and guides (locked ones show a lock). Topic mode: text input max 80 chars, placeholder "For example: rotator cuff muscles". Length 5 or 10 (segmented). Checkbox "Only questions approved by the instructor". Button "Build quiz". If GET /api/quiz/latest returns a quiz, show a quiet card at the top: "You have an unfinished quiz (3 of 10 answered)" with "Resume" and "Discard". Below: "Past quizzes" as a simple list "Oct 30 · 8 of 10" opening results.
- Building: a calm progress view "Preparing your quiz" with "4 of 10 questions ready" and a thin progress bar, plus the job's note in muted text (poll GET /api/quiz/jobs/{id} every 1.5 s). Handle results: ready → open quiz; offer → message + "Start with 5" (oxblood), "Continue preparing", "Discard"; partial/failed → message + "Continue preparing" when have > 0.
- Taking: one question per screen. Top: thin segmented progress (answered segments filled) and "Question 3 of 10". The stem in 16 px, the lead-in in Source Serif 4 semibold, then 4 options as large full-width selectable rows (min 52 px tall) with a letter circle A-D; selected row = accent-soft bg and oxblood border. NO correctness shown while taking. Each selection saves immediately (PUT answers). "Back" / "Next", and a small row of numbered dots to jump (answered dots filled). After the last question: "Review answers".
- Review: list of questions with the chosen letter or "Not answered" and "Change" links; "Submit quiz" (oxblood) with a confirm dialog "Unanswered questions count as wrong."
- Results: big serif score "8 of 10". Each question as a card: verdict pill (Correct / Incorrect), the question, all options with the right one marked (check icon, green text) and the student's wrong pick marked (x icon, oxblood); explanation; "Why not the others" collapsible (alternatives); evidence list (label, tier, open link when url; text when visible). The review label (e.g. "Not yet reviewed by the instructor") in small muted text. Buttons: "New quiz", "Back to Quiz".

7. INSTRUCTOR (role "instructor"): same shell; sidebar items instead of tabs: Overview, Review queue, Questions, Access, Preview as student (same dark sidebar style, active item = cream text with #F0B3AC dot).
- Overview: three stat cards (Questions in the last 7 days, Open flags, Web-sourced answers in the last 7 days) and the review breakdown as a small horizontal bar chart (recharts, bars in oxblood shades, labels in ink): Confirmed factual 90, Doubtful 32, Wording 442, Typos 169, Start here 14.
- Review queue: filters (type, status, lecture), list of items; detail panel on the right: lecture and section, original text, the AI's note, sources, optional "Fix text" box, buttons "Verify fix" and "Dismiss". A small note: "The AI only flags. You decide."
- Questions: table with filters "Web-sourced only" and "Flagged only"; clicking a row shows the answer exactly as the student saw it.
- Access: list of students; selecting one shows checkboxes for lectures and dissection guides, "Grant all", "Save".
- Preview as student: choose "Full access" or a student, then show the student app with a slim bar on top "Previewing as a student. Nothing is saved." and "Exit preview".

==================== API CONTRACT (types and endpoints must match exactly) ====================
Base path: /api. JSON everywhere. Auth uses an httpOnly session cookie (12 h), so a reload does NOT sign the user out. In development, Vite proxies /api to http://localhost:8000 (same origin).
Errors: every non-2xx response is {error: string} where error is a message fit to show the user.

## Auth
- POST /api/auth/login {username, password} → {user: {id, name, role: "student" | "instructor"}}. Wrong login → 401 {error}.
- POST /api/auth/logout → {ok: true}
- GET /api/auth/me → {user} or 401

## Scope (what this student may use)
- GET /api/scope → {lectures: [{id, title, granted}], guides: [{id, class_number, title, lecture_ids: [], granted}]}

## Chats
- GET /api/chats → [{id, title, updated_at}] (newest first; the UI groups them into Today / Yesterday / Previous 7 days / Older)
- POST /api/chats → {id, title: "New chat", updated_at}
- GET /api/chats/{id} → {id, title, messages: [Message]}
- PATCH /api/chats/{id} {title} → {id, title}
- DELETE /api/chats/{id} → {ok: true}

## Ask
POST /api/ask {chat_id, question (max 600 characters), length: "brief" | "detailed", lecture_ids?: []} → Message

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
  license                         // "CC BY-SA 4.0" (Wikipedia), "CC BY-NC-SA 4.0" (OpenStax), else null
}
```
- POST /api/messages/{id}/flag {reason} → {ok: true}. Goes to the professor's queue.
- "Explain simpler" in the UI is just POST /api/ask with question "Explain this more simply: <snippet>" and length "brief" (no new endpoint).

## Guide (dissection guides)
- GET /api/guides → [{id, class_number, title, region, station_count, granted}]
- GET /api/guides/{id}/stations → [{index, title, steps: [text], slides: [int], image_only: bool}]
- POST /api/guides/{id}/stations/{index}/check {description} → {verdict: "correct" | "partly" | "not_matching", feedback_markdown, sources: [Source]}
- Lecture-notes sample mode: GET /api/lectures/{id}/stations, same shape.

## Quiz (wraps src/quiz/service.py; key, explanations and evidence are NEVER sent before submit)
Building a quiz can take a while (reuse first, then generate and verify), so it runs as a job:
- POST /api/quiz/build {mode: "materials" | "topic", lecture_ids?: [], guide_ids?: [], topic? (max 80 chars), n: 5 | 10, reviewed_only: bool, continue_quiz_id?: null}
  → {job_id}
- GET /api/quiz/jobs/{job_id} → {done: bool, have, requested, note, result: BuildResult | null}
  BuildResult = {status: "ready" | "offer" | "partial" | "failed", reason, quiz_id | null, have, requested, message}
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
             explanation, alternatives: {option_id: why_wrong}, evidence: [{id, label, tier, url, visible, text, license}], label, review_status}]}
- GET /api/quiz/history → [{id, score, length, submitted}] (newest first)

## Instructor only (403 for students)
- GET /api/admin/stats → {questions_7d, flagged_open, web_answers_7d, review_counts: {confirmed_factual, doubtful, wording, typo, start_here}}
- GET /api/admin/review?type=&status=&lecture=&page= → {items: [{id, type, status, lecture, section, original_text, ai_note, sources: [Source]}], total}
- POST /api/admin/review/{id} {action: "verify" | "dismiss", fix_text?} → {ok: true}
- GET /api/admin/questions?web=&flagged=&page= → {items: [{id, student, question, kind, web, flagged, created_at, message}], total}
- GET /api/admin/students → [{id, name, username, lecture_ids, guide_ids}]
- PUT /api/admin/students/{id}/access {lecture_ids, guide_ids} → {ok: true}
- POST /api/admin/preview {profile: "full" | student_id} → starts preview-as-student. Nothing is saved while previewing. POST /api/admin/preview/exit ends it.

==================== MOCK DATA (src/lib/mock.ts) ====================
Users "inglis" (instructor, "Dr. Inglis") and "student1" (student, "Student One"); any password works in mock mode. Use these exact mock answers:
- Femoral triangle (kind "answer"), markdown:
"The femoral triangle is a region in the upper anterior thigh.\n\n**Boundaries**\n- Superior: inguinal ligament [1]\n- Lateral: medial border of sartorius [1]\n- Medial: medial border of adductor longus [1]\n\n**Floor:** iliopsoas, pectineus and adductor longus [1]\n\n**Roof:** fascia lata [2]\n\n**Contents (lateral to medial):** femoral nerve, femoral artery, femoral vein and deep inguinal lymph nodes [1][2]"
  sources: [1] type "notes", title "Lecture notes", subtitle "Lecture 08, Anterior and Medial Thigh", lecture_id "L08", url null, snippet "The femoral triangle is bounded superiorly by the inguinal ligament, laterally by the medial border of sartorius, and medially by the medial border of adductor longus. Its floor is formed by iliopsoas, pectineus and adductor longus."; [2] type "openstax", title "OpenStax Anatomy & Physiology 2e, section 11.6", lecture_id null, url "https://openstax.org/books/anatomy-and-physiology-2e/pages/11-6-appendicular-muscles-of-the-pelvic-girdle-and-lower-limbs", license "CC BY-NC-SA 4.0", short neutral snippet.
- "apex" (kind "term_lookup"): "**Apex** appears in a few places in your notes:\n- **Femoral triangle:** the apex points inferiorly, where sartorius crosses adductor longus [1]\n- **Heart:** the apex is formed by the left ventricle [2]\n- **Lung:** the apex rises above the clavicle into the root of the neck [2]\n\nAsk about a specific one for more detail."
- Amoxicillin dose (kind "refused"): "I can't help with medication dosing. This assistant answers anatomy questions from your course material."
- "What is Waldeyer's ring?" answer with one source type "wikipedia", url "https://en.wikipedia.org/wiki/Waldeyer%27s_tonsillar_ring", license "CC BY-SA 4.0", footer.basis_line "Based on Wikipedia, not your lecture notes."
- Two guides with 4 stations each (Class 17: The Hip and Knee Joints; Class 14: Gluteal Region), short neutral step text, and check responses for each verdict.
- Quiz: one 5-question quiz on the femoral triangle and thigh (realistic single-best-answer questions, 4 options each, explanations, alternatives, one evidence item each), a build job that reaches "ready" after ~4 polls, one "offer" example (6 of 10), and 2 past quizzes.
- 6 chats spread across the date groups, 8 review items, 10 question-log rows, 2 students.

QUALITY BAR: no lorem ipsum; every button works in mock mode; loading, empty and error states for every list and request; responsive at 390, 768 and 1440 px; keyboard navigable with visible focus; WCAG AA contrast; no console errors. Split components sensibly (AppShell, Sidebar, ChatView, MessageItem, CitationChip, SourcesRow, SourcePanel, Composer, GuidePicker, StationView, QuizSetup, QuizBuild, QuizTake, QuizReview, QuizResults, ReviewQueue, AccessEditor, PreviewBar). README explaining VITE_USE_MOCK, VITE_API_URL and the /api proxy.
