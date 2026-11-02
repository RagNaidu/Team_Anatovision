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
}

export const FLAG_REASONS = [
  "The answer is wrong",
  "The answer does not match the notes",
  "A citation points to the wrong place",
  "Something important is missing",
  "Something else",
] as const;

// ---- Guide
export interface GuideSummary { id: string; class_number: number; title: string; region: string; station_count: number; granted: boolean }
export interface Station { index: number; title: string; steps: string[]; slides: number[]; image_only: boolean }
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
  continue_quiz_id?: string | null;
}
export type BuildStatus = "ready" | "offer" | "partial" | "failed";
export interface BuildResult { status: BuildStatus; reason: string; quiz_id: string | null; have: number; requested: number; message: string }
export interface QuizJob { done: boolean; have: number; requested: number; note: string; result: BuildResult | null }
export interface QuizLatest { id: string; status: "open" | "offer"; length: number; answered: number }
export interface QuizOption { id: string; text: string }
export interface OpenQuestion { stem: string; lead_in: string; selection_mode: "single"; options: QuizOption[] }
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
}
export interface QuizResults { quiz_id: string; score: number; length: number; submitted: string; questions: ResultQuestion[] }
export interface QuizHistoryItem { id: string; score: number; length: number; submitted: string }

// ---- Instructor
export type ReviewType = "confirmed_factual" | "doubtful" | "wording" | "typo" | "start_here" | "student_report";
export type ReviewStatus = "open" | "verified" | "dismissed" | "decided";
export interface AdminStats {
  questions_7d: number;
  flagged_open: number;
  web_answers_7d: number;
  review_counts: { confirmed_factual: number; doubtful: number; wording: number; typo: number; start_here: number };
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

/** Ask progress (Step D). The contract entry is added by Step D; this is the shape the UI expects. */
export type AskStageKey = "searching" | "reading" | "writing" | "checking";
export interface AskStatus { stage: AskStageKey | "done" | string; stages?: { key: string; seconds?: number | null }[] }
