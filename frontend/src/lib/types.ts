// Types for docs/api_contract.md. That document is the single source of truth; change it first, then this file.

export type Role = "student" | "instructor";
export interface User { id: string; name: string; role: Role }
export interface Preview { profile: "full" | string; name: string }
export interface Me { user: User; preview: Preview | null }

export interface ScopeLecture { id: string; title: string; granted: boolean }
export interface ScopeGuide { id: string; class_number: number; title: string; lecture_ids: string[]; granted: boolean }
export interface Scope { lectures: ScopeLecture[]; guides: ScopeGuide[] }

export interface ChatSummary { id: string; title: string; updated_at: string }

export type SourceType = "notes" | "guide" | "openstax" | "wikipedia" | "web" | "verified_fix";
export interface Source {
  n: number;
  type: SourceType;
  title: string;
  subtitle: string;
  lecture_id: string | null;
  url: string | null;
  snippet: string;
  retrieved_at: string | null;
  license: string | null;
  /** an old answer's notes / guide source that the revised notes changed or removed */
  revision?: "updated" | "removed" | null;
}

export type MessageKind = "answer" | "term_lookup" | "not_covered" | "refused" | "error";
export interface Footer { basis_line: string | null; access_note: string | null }
export interface Message {
  id: string;
  role: "user" | "assistant";
  created_at: string;
  kind: MessageKind;
  markdown: string;
  sources: Source[];
  footer: Footer | null;
  timing_ms: number;
  /** slide image cards of the guide steps this answer used (only guides the student may open) */
  images?: SlideImage[];
}
export interface ChatDetail { id: string; title: string; messages: Message[] }

export type AnswerLength = "brief" | "detailed";
export interface AskBody {
  chat_id: string;
  question: string;
  length: AnswerLength;
  lecture_ids?: string[];
  /** "<more|average|less> fat, <more|average|less> muscle, <large|average|small> build"; anything else is 422 */
  body_type?: string;
  /** client-made id ([A-Za-z0-9_-], max 64): lets the UI poll GET /api/ask/status/{request_id} for the real stage */
  request_id?: string;
}

export const FLAG_REASONS = [
  "The answer is wrong",
  "The answer does not match the notes",
  "A citation points to the wrong place",
  "Something important is missing",
  "Something else",
] as const;

// ---- Guide
export type GuideBodyType = "lean" | "average" | "more_fat" | "more_muscular" | "not_sure";
export interface BodyTipLine { text: string; general: boolean }
export interface BodyTip { body_type: string; lines: BodyTipLine[] }
export interface GuideSummary { id: string; class_number: number; title: string; region: string; station_count: number; granted: boolean }
export type MarkKind = "arrow" | "cut" | "highlight" | "label";
/** Coordinates are 0-1 on the slide image (x from the left, y from the top). */
export interface Mark { id: string; slide: number; crop?: number; kind: MarkKind; geom: Record<string, unknown>; text: string; step: number | null; n: number; status?: "draft" | "approved"; author?: string; version?: number; source?: "manual" | "auto" | "ocr"; flag?: string }
export interface SlideImage { slide: number; crop?: number; url: string; thumb_url: string; caption: string; alt: string; w: number; h: number; marks: Mark[]; guide_id?: string; source_n?: number; step?: number | null; confidence?: "high" | "low"; why?: string; reviewed?: boolean; original_url?: string }
export interface Station { index: number; title: string; steps: string[]; slides: number[]; image_only: boolean; images?: SlideImage[] }
export interface AnnStation { index: number; title: string; steps: string[]; slides: number[]; image_only: boolean; images: SlideImage[]; drafts: number; approved: number }
export interface AnnGuide { guide_id: string; title: string; stations: AnnStation[]; rendered: boolean }
export type Verdict = "correct" | "partly" | "not_matching";
export interface StationCheck { verdict: Verdict; feedback_markdown: string; sources: Source[] }

// ---- Quiz
export type QuizMode = "materials" | "topic";
export interface QuizBuildBody {
  mode: QuizMode;
  lecture_ids?: string[];
  guide_ids?: string[];
  topic?: string;
  n: 5 | 10;
  reviewed_only: boolean;
  different_style?: boolean;
  continue_quiz_id?: string | null;
}
export type BuildStatus = "ready" | "offer" | "partial" | "failed";
export interface BuildResult { status: BuildStatus; reason: string; quiz_id: string | null; have: number; requested: number; message: string }
export interface QuizJob { done: boolean; have: number; requested: number; note: string; result: BuildResult | null }
export interface QuizLatest { id: string; status: "open" | "offer"; length: number; answered: number }
export interface QuizOption { id: string; text: string }
export interface OpenQuestion {
  stem: string; lead_in: string; selection_mode: "single"; options: QuizOption[];
  /** built from the web (Wikipedia), not from the course notes */
  web: boolean;
  /** "Not from course notes" when web, else null */
  source_note: string | null;
}
export interface OpenQuiz {
  quiz_id: string;
  length: number;
  current: number;
  answered: number;
  questions: OpenQuestion[];
  selections: Record<string, string[]>;
}
export interface EvidenceItem { id: string; label: string; tier: string; url: string | null; visible: boolean; text: string; license: string | null }
export interface ResultQuestion {
  n: number;
  stem: string;
  lead_in: string;
  options: QuizOption[];
  selected: string[];
  answer_ids: string[];
  correct: boolean;
  explanation: string;
  alternatives: Record<string, string>;
  evidence: EvidenceItem[];
  label: string;
  review_status: string;
  spans: { source_id: string; span: string }[];
  web: boolean;
  source_note: string | null;
}
export interface QuizResults { quiz_id: string; score: number; length: number; submitted: string; questions: ResultQuestion[] }
export interface QuizHistoryItem { id: string; score: number; length: number; submitted: string; title: string; web: boolean }
export interface GuideHistoryItem { id: string; kind: "guide" | "lecture"; ref: string; title: string; station: number; count: number; updated_at: string; body_type: GuideBodyType | null; notice: string | null }
export interface WebQuizItem {
  id: string; student: string; title: string; status: string; score: number | null; length: number; web_questions: number;
  sources: { title: string; url: string | null; license: string }[]; created_at: string;
}
export interface WebQuizPage { items: WebQuizItem[]; total: number }

// ---- Instructor
export type ReviewType = "confirmed_factual" | "doubtful" | "wording" | "typo" | "start_here" | "student_report";
export type ReviewStatus = "open" | "verified" | "dismissed" | "changed" | "decided";
export interface AdminStats {
  questions_7d: number;
  flagged_open: number;
  web_answers_7d: number;
  review_counts: { confirmed_factual: number; doubtful: number; wording: number; typo: number; start_here: number };
  bank_counts?: BankCounts | null;
}
export interface ReviewItem {
  id: string;
  type: ReviewType;
  status: ReviewStatus;
  lecture: string;
  section: string;
  original_text: string;
  ai_note: string;
  sources: Source[];
}
export interface ReviewPage { items: ReviewItem[]; total: number }
export interface QuestionRow {
  id: string;
  student: string;
  question: string;
  kind: MessageKind;
  web: boolean;
  flagged: boolean;
  created_at: string;
  message: Message | null;
}
export interface QuestionPage { items: QuestionRow[]; total: number }
export interface Student { id: string; name: string; username: string; lecture_ids: string[]; guide_ids: string[] }

/** GET /api/ask/status/{request_id}: only the stage word; 404 until the POST registered the id (treat as "searching"). */
export type AskStageKey = "searching" | "reading" | "writing" | "checking";
export interface AskStatus { stage: AskStageKey | "done" }

// ---- Notes manager (instructor only)
export type NoteStatus = "draft" | "processing" | "ready" | "published" | "archived";
export interface NoteRow { id: string; kind: "note" | "guide"; title: string; region: string; version: number; status: NoteStatus; updated_at: string; access_count: number; note: string; earlier_version: boolean }
export interface NoteList { items: NoteRow[]; regions: string[]; total: number }
export interface NoteJob { status: string; step: string; step_index: number; steps: string[]; error: string; version: number }
export interface NoteFlag { quote: string; issue: string; severity: string; tier: string; section: string }
export interface NoteDiffRow { status: "unchanged" | "edited" | "rewritten" | "added" | "removed"; path: string; old: string; new: string }
export interface NoteDiff { against: string | null; counts: Record<string, number>; rows: NoteDiffRow[] }
export interface NoteDetail {
  id: string; kind: "note" | "guide"; title: string; region: string; status: NoteStatus; version: number; live_version: number | null; shown_version: number | null;
  created_at: string; updated_at: string; replaces: string | null; replaces_title: string | null;
  overlap: { doc_id: string; title: string; score: number; shared_sections: number; sections: number; suggest_replace: boolean } | null;
  source_name: string; job: NoteJob | null; sections: { path: string[]; text: string }[]; mapping: { region: string; lecture: string; title: string };
  flags: { count: number; items: NoteFlag[] }; diff: NoteDiff | null; archived_at: string | null; purge_after: string | null; grants_mode: string;
  has_pending: boolean; editable: boolean; regions: string[]; lectures: string[]; guide_id?: string | null;
}
export interface NoteChange { doc_id: string; version: number | null; granted: number; flags_added: number; fixes_to_recheck: number; progress_moved: number; restorable_until: string | null }
export interface NoteVersion { version: number; status: string; created_at: string; created_by: string; note: string; n_sections: number; source_name: string; diff: Record<string, number> | null }
export interface NoteAudit { at: string; user: string; action: string; detail: string }
export interface NoteFilters { kind?: string; region?: string; status?: string; q?: string }

// ---- Question bank (instructor only)
export type BankStatus = "draft" | "approved" | "retired";
export type BankUse = "practice" | "exam_secure";
export type BankSource = "instructor" | "ai" | "web" | "imported";
export interface BankCounts { total: number; draft: number; approved: number; retired: number; exam_secure: number; flagged: number; needs_recheck: number }
export interface BankRow { id: string; lead_in: string; stem: string; status: BankStatus; use: BankUse; source: BankSource; lecture: string; region: string; tags: string[]; difficulty: string; version: number; updated_at: string; flagged: boolean; n_flags: number; needs_recheck: boolean; sample: boolean; used: number }
export interface BankList { items: BankRow[]; total: number; counts: BankCounts; lectures: string[]; regions: string[]; tags: string[] }
export interface BankFilters { q?: string; status?: string; use?: string; source?: string; region?: string; lecture?: string; tag?: string; difficulty?: string; flagged?: boolean; page?: number }
export interface BankOption { id: string; text: string }
export interface BankData { stem: string; lead_in: string; options: BankOption[]; answer: string; explanation: string; lecture: string; guide: string; section: string; region: string; tags: string[]; difficulty: "" | "easy" | "medium" | "hard"; source: BankSource; status: BankStatus; use: BankUse; objective: string }
export interface BankFlag { kind: string; code: string; severity: "warn" | "info"; message: string; dismissed: boolean }
export interface BankStats { n: number; p_correct: number | null; discrimination: number | null; enough: boolean; distractors: { text: string; picks: number; correct: boolean }[]; min_for_stats: number; min_for_flags: number }
export interface BankVersion { version: number; at: string; by: string; note: string; changed: string[] }
export interface BankComment { id: number; at: string; by: string; text: string }
export interface BankDetail { id: string; version: number; created_at: string; updated_at: string; data: BankData; sample: boolean; flags: BankFlag[]; needs_recheck: string; stats: BankStats; comments: BankComment[]; versions: BankVersion[] }
export interface BankImportPreview { import_id: string; filename: string; headers: string[]; rows: string[][]; n_rows: number; mapping: Record<string, string>; fields: { field: string; label: string }[]; questions: { row: string; lead_in: string; options: string; answer: string; duplicate: string }[]; problems: { row: string; problem: string }[]; duplicates: number; ready: number }
export interface BankImportResult { created: number; skipped_duplicates: number; problems: { row: string; problem: string }[]; flagged: number }

export interface Explanation { text: string; label: string; sources: Source[] }
