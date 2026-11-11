// The ONLY place that talks to the backend. One typed function per endpoint of docs/api_contract.md.
// VITE_USE_MOCK !== "false" (the default) -> realistic mock data from ./mock with a 600 to 1,200 ms delay.
// VITE_USE_MOCK === "false"               -> fetch(`${VITE_API_URL ?? ""}/api/...`, { credentials: "include" }).
import type {
  AdminStats, AskBody, AskStatus, BodyTip, GuideBodyType, ChatDetail, ChatSummary, GuideHistoryItem, GuideSummary, Me, Message, OpenQuiz, QuestionPage, QuizBuildBody, QuizHistoryItem,
  BankDetail, BankData, BankFilters, BankImportPreview, BankImportResult, BankList, AnnGuide, Explanation, Mark, MarkKind, NoteAudit, NoteChange, NoteDetail, NoteDiff, NoteFilters, NoteList, NoteVersion, QuizJob, QuizLatest, QuizResults, ReviewPage, Scope, Station, StationCheck, Student, User, WebQuizPage,
} from "./types";

export const USE_MOCK: boolean = String(import.meta.env.VITE_USE_MOCK ?? "true") !== "false";
const BASE: string = String(import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Text fit for a person. Never a raw status code or a stack trace. */
export function errorMessage(e: unknown, fallback = "Something went wrong. Please try again."): string {
  if (e instanceof ApiError && e.message) return e.message;
  if (e instanceof Error && e.message && !/^(Failed to fetch|NetworkError|Load failed)/i.test(e.message)) return e.message;
  return fallback;
}

const NETWORK_MESSAGE = "Can't reach the server. Check your connection and try again.";
const GENERIC_BY_STATUS: Record<number, string> = {
  400: "That request wasn't valid.",
  401: "Please sign in again.",
  403: "You don't have access to that.",
  404: "That wasn't found.",
  409: "That can't be done right now.",
  422: "Please check what you entered.",
  429: "Too many attempts. Wait a few minutes and try again.",
  502: "The AI service couldn't finish that. Please try again.",
};

type Query = Record<string, string | number | boolean | undefined | null>;
function qs(q?: Query): string {
  if (!q) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function http<T>(method: string, path: string, body?: unknown, extra?: { headers?: Record<string, string> }): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api${path}`, {
      method,
      credentials: "include",
      headers: { ...(body !== undefined && !(body instanceof FormData) ? { "Content-Type": "application/json" } : {}), Accept: "application/json", ...(extra?.headers ?? {}) },
      body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(NETWORK_MESSAGE, 0);
  }
  let data: unknown = null;
  const text = await res.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = null; }
  }
  if (!res.ok) {
    const msg = data && typeof data === "object" && "error" in data && typeof (data as { error: unknown }).error === "string"
      ? (data as { error: string }).error : "";
    if (res.status === 401 && !path.startsWith("/auth/login") && !path.startsWith("/auth/me")) window.dispatchEvent(new Event("av:unauthorized"));
    throw new ApiError(msg || GENERIC_BY_STATUS[res.status] || "Something went wrong. Please try again.", res.status);
  }
  return data as T;
}

const mock = () => import("./mock");

// ---- Ask progress (Step D). The stages shown are the real ones reported by GET /api/ask/status/{request_id}.
// Whether the backend has the endpoint is read ONCE from its OpenAPI document, so no failing request ever reaches the console.
let statusAvailable: Promise<boolean> | null = null;
export function askStatusAvailable(): Promise<boolean> {
  if (USE_MOCK) return Promise.resolve(true);
  statusAvailable ??= fetch(`${BASE}/api/openapi.json`, { credentials: "include" })
    .then((r) => (r.ok ? r.json() : null))
    .then((j) => Boolean(j && j.paths && Object.keys(j.paths).some((p) => p.startsWith("/api/ask/status"))))
    .catch(() => false);
  return statusAvailable;
}

/** A slide image URL for <img src>: the API path as given (same origin in development and production, so the session cookie goes with it). */
export function imageSrc(url: string): string { return url.startsWith("/api/") ? `${BASE}${url}` : url; }

export const api = {
  // ---- Auth
  login: (username: string, password: string): Promise<{ user: User }> =>
    USE_MOCK ? mock().then((m) => m.login(username, password)) : http("POST", "/auth/login", { username, password }),
  logout: (): Promise<{ ok: true }> => (USE_MOCK ? mock().then((m) => m.logout()) : http("POST", "/auth/logout")),
  me: (): Promise<Me> => (USE_MOCK ? mock().then((m) => m.me()) : http("GET", "/auth/me")),

  // ---- Scope
  scope: (): Promise<Scope> => (USE_MOCK ? mock().then((m) => m.scope()) : http("GET", "/scope")),

  // ---- Chats
  listChats: (): Promise<ChatSummary[]> => (USE_MOCK ? mock().then((m) => m.listChats()) : http("GET", "/chats")),
  createChat: (): Promise<ChatSummary> => (USE_MOCK ? mock().then((m) => m.createChat()) : http("POST", "/chats")),
  getChat: (id: string): Promise<ChatDetail> => (USE_MOCK ? mock().then((m) => m.getChat(id)) : http("GET", `/chats/${encodeURIComponent(id)}`)),
  renameChat: (id: string, title: string): Promise<{ id: string; title: string }> =>
    USE_MOCK ? mock().then((m) => m.renameChat(id, title)) : http("PATCH", `/chats/${encodeURIComponent(id)}`, { title }),
  deleteChat: (id: string): Promise<{ ok: true }> =>
    USE_MOCK ? mock().then((m) => m.deleteChat(id)) : http("DELETE", `/chats/${encodeURIComponent(id)}`),

  // ---- Ask
  ask: (body: AskBody, requestId?: string): Promise<Message> =>
    USE_MOCK ? mock().then((m) => m.ask(body, requestId)) : http("POST", "/ask", requestId ? { ...body, request_id: requestId } : body),
  askStatus: async (requestId: string): Promise<AskStatus | null> => {
    if (USE_MOCK) return mock().then((m) => m.askStatus(requestId));
    if (!(await askStatusAvailable())) return null;
    try { return await http<AskStatus>("GET", `/ask/status/${encodeURIComponent(requestId)}`); } catch { return null; }
  },
  flagMessage: (id: string, reason: string, comment?: string): Promise<{ ok: true }> =>
    USE_MOCK ? mock().then((m) => m.flagMessage(id, reason, comment)) : http("POST", `/messages/${encodeURIComponent(id)}/flag`, { reason, ...(comment ? { comment } : {}) }),

  // ---- Guide
  listGuides: (): Promise<GuideSummary[]> => (USE_MOCK ? mock().then((m) => m.listGuides()) : http("GET", "/guides")),
  guideStations: (id: string): Promise<Station[]> =>
    USE_MOCK ? mock().then((m) => m.guideStations(id)) : http("GET", `/guides/${encodeURIComponent(id)}/stations`),
  lectureStations: (id: string): Promise<Station[]> =>
    USE_MOCK ? mock().then((m) => m.lectureStations(id)) : http("GET", `/lectures/${encodeURIComponent(id)}/stations`),
  checkStation: (id: string, index: number, description: string, bodyType?: GuideBodyType | null): Promise<StationCheck> =>
    USE_MOCK ? mock().then((m) => m.checkStation(id, index, description, bodyType)) : http("POST", `/guides/${encodeURIComponent(id)}/stations/${index}/check`, { description, ...(bodyType ? { body_type: bodyType } : {}) }),
  guideBodyTip: (id: string, index: number, bodyType: GuideBodyType): Promise<BodyTip> =>
    USE_MOCK ? mock().then((m) => m.guideBodyTip(id, index, bodyType)) : http("GET", `/guides/${encodeURIComponent(id)}/stations/${index}/body-tip${qs({ body_type: bodyType })}`),

  guideHistory: (): Promise<GuideHistoryItem[]> => (USE_MOCK ? mock().then((m) => m.guideHistory()) : http("GET", "/guide-history")),
  saveGuideHistory: (kind: "guide" | "lecture", ref: string, station: number, bodyType?: GuideBodyType): Promise<{ ok: true }> =>
    USE_MOCK ? mock().then((m) => m.saveGuideHistory(kind, ref, station, bodyType)) : http("PUT", "/guide-history", { kind, ref, station, ...(bodyType ? { body_type: bodyType } : {}) }),
  deleteGuideHistory: (id: string): Promise<{ ok: true }> =>
    USE_MOCK ? mock().then((m) => m.deleteGuideHistory(id)) : http("DELETE", `/guide-history/${encodeURIComponent(id)}`),

  // ---- Quiz
  buildQuiz: (body: QuizBuildBody): Promise<{ job_id: string }> => (USE_MOCK ? mock().then((m) => m.buildQuiz(body)) : http("POST", "/quiz/build", body)),
  quizJob: (id: string): Promise<QuizJob> => (USE_MOCK ? mock().then((m) => m.quizJob(id)) : http("GET", `/quiz/jobs/${encodeURIComponent(id)}`)),
  quizLatest: (): Promise<QuizLatest | null> => (USE_MOCK ? mock().then((m) => m.quizLatest()) : http("GET", "/quiz/latest")),
  acceptQuiz: (id: string): Promise<{ ok: true }> => (USE_MOCK ? mock().then((m) => m.acceptQuiz(id)) : http("POST", `/quiz/${encodeURIComponent(id)}/accept`)),
  discardQuiz: (id: string): Promise<{ ok: true }> => (USE_MOCK ? mock().then((m) => m.discardQuiz(id)) : http("DELETE", `/quiz/${encodeURIComponent(id)}`)),
  getQuiz: (id: string): Promise<OpenQuiz> => (USE_MOCK ? mock().then((m) => m.getQuiz(id)) : http("GET", `/quiz/${encodeURIComponent(id)}`)),
  saveAnswer: (id: string, index: number, optionIds: string[]): Promise<{ ok: true; answered: number }> =>
    USE_MOCK ? mock().then((m) => m.saveAnswer(id, index, optionIds)) : http("PUT", `/quiz/${encodeURIComponent(id)}/answers/${index}`, { option_ids: optionIds }),
  setCurrent: (id: string, index: number): Promise<{ ok: true }> =>
    USE_MOCK ? mock().then((m) => m.setCurrent(id, index)) : http("PUT", `/quiz/${encodeURIComponent(id)}/current`, { index }),
  submitQuiz: (id: string): Promise<QuizResults> => (USE_MOCK ? mock().then((m) => m.submitQuiz(id)) : http("POST", `/quiz/${encodeURIComponent(id)}/submit`)),
  quizResults: (id: string): Promise<QuizResults> => (USE_MOCK ? mock().then((m) => m.quizResults(id)) : http("GET", `/quiz/${encodeURIComponent(id)}/results`)),
  quizHistory: (): Promise<QuizHistoryItem[]> => (USE_MOCK ? mock().then((m) => m.quizHistory()) : http("GET", "/quiz/history")),

  deleteQuizHistory: (id: string): Promise<{ ok: true }> =>
    USE_MOCK ? mock().then((m) => m.deleteQuizHistory(id)) : http("DELETE", `/quiz/history/${encodeURIComponent(id)}`),

  // ---- Instructor
  adminWebQuizzes: (page?: number): Promise<WebQuizPage> => (USE_MOCK ? mock().then((m) => m.adminWebQuizzes()) : http("GET", `/admin/web-quizzes${qs({ page })}`)),
  adminStats: (): Promise<AdminStats> => (USE_MOCK ? mock().then((m) => m.adminStats()) : http("GET", "/admin/stats")),
  adminReview: (q: { type?: string; status?: string; lecture?: string; page?: number }): Promise<ReviewPage> =>
    USE_MOCK ? mock().then((m) => m.adminReview(q)) : http("GET", `/admin/review${qs(q)}`),
  adminDecide: (id: string, action: "verify" | "dismiss", fixText?: string): Promise<{ ok: true }> =>
    USE_MOCK ? mock().then((m) => m.adminDecide(id, action, fixText)) : http("POST", `/admin/review/${encodeURIComponent(id)}`, { action, ...(fixText ? { fix_text: fixText } : {}) }),
  adminQuestions: (q: { web?: boolean; flagged?: boolean; page?: number }): Promise<QuestionPage> =>
    USE_MOCK ? mock().then((m) => m.adminQuestions(q)) : http("GET", `/admin/questions${qs({ web: q.web ? "true" : undefined, flagged: q.flagged ? "true" : undefined, page: q.page })}`),
  adminStudents: (): Promise<Student[]> => (USE_MOCK ? mock().then((m) => m.adminStudents()) : http("GET", "/admin/students")),
  adminSetAccess: (id: string, lectureIds: string[], guideIds: string[]): Promise<{ ok: true }> =>
    USE_MOCK ? mock().then((m) => m.adminSetAccess(id, lectureIds, guideIds)) : http("PUT", `/admin/students/${encodeURIComponent(id)}/access`, { lecture_ids: lectureIds, guide_ids: guideIds }),
  adminPreview: (profile: string): Promise<{ ok: true }> => (USE_MOCK ? mock().then((m) => m.adminPreview(profile)) : http("POST", "/admin/preview", { profile })),
  adminPreviewExit: (): Promise<{ ok: true }> => (USE_MOCK ? mock().then((m) => m.adminPreviewExit()) : http("POST", "/admin/preview/exit")),

  // ---- Notes manager (instructor only)
  notesList: (f: NoteFilters): Promise<NoteList> => (USE_MOCK ? mock().then((m) => m.notesList(f)) : http("GET", `/admin/notes${qs(f as Query)}`)),
  notesUpload: (file: File, kind?: string, replaces?: string): Promise<{ doc_id: string; version: number }> => {
    if (USE_MOCK) return mock().then((m) => m.notesUpload(file.name, file.size, kind, replaces));
    const f = new FormData();
    f.append("file", file);
    if (kind) f.append("kind", kind);
    if (replaces) f.append("replaces", replaces);
    return http("POST", "/admin/notes", f);
  },
  notesDetail: (id: string): Promise<NoteDetail> => (USE_MOCK ? mock().then((m) => m.notesDetail(id)) : http("GET", `/admin/notes/${encodeURIComponent(id)}`)),
  notesMapping: (id: string, body: { region?: string; replaces?: string; lecture?: string }): Promise<{ ok: true }> =>
    USE_MOCK ? mock().then((m) => m.notesMapping(id, body)) : http("PATCH", `/admin/notes/${encodeURIComponent(id)}/mapping`, body),
  notesReplace: (id: string, file: File): Promise<{ doc_id: string; version: number }> => {
    if (USE_MOCK) return mock().then((m) => m.notesReplace(id, file.name));
    const f = new FormData();
    f.append("file", file);
    return http("POST", `/admin/notes/${encodeURIComponent(id)}/replace`, f);
  },
  notesPublish: (id: string, access: "all" | "selected" | "none" | "same", students: string[]): Promise<NoteChange> =>
    USE_MOCK ? mock().then((m) => m.notesPublish(id, access, students)) : http("POST", `/admin/notes/${encodeURIComponent(id)}/publish`, { access, students }),
  notesDiscard: (id: string): Promise<{ ok: true }> => (USE_MOCK ? mock().then((m) => m.notesDiscard(id)) : http("POST", `/admin/notes/${encodeURIComponent(id)}/discard`)),
  notesEdit: (id: string, edits: { index: number; text: string }[], note: string): Promise<NoteChange> =>
    USE_MOCK ? mock().then((m) => m.notesEdit(id, edits, note)) : http("PUT", `/admin/notes/${encodeURIComponent(id)}/sections`, { edits, note }),
  notesVersions: (id: string): Promise<NoteVersion[]> => (USE_MOCK ? mock().then((m) => m.notesVersions(id)) : http("GET", `/admin/notes/${encodeURIComponent(id)}/versions`)),
  notesVersionDiff: (id: string, version: number): Promise<NoteDiff> =>
    USE_MOCK ? mock().then((m) => m.notesVersionDiff(id, version)) : http("GET", `/admin/notes/${encodeURIComponent(id)}/versions/${version}/diff`),
  notesRollback: (id: string, version: number): Promise<NoteChange> =>
    USE_MOCK ? mock().then((m) => m.notesRollback(id, version)) : http("POST", `/admin/notes/${encodeURIComponent(id)}/rollback`, { version }),
  notesArchive: (id: string): Promise<NoteChange> => (USE_MOCK ? mock().then((m) => m.notesArchive(id)) : http("POST", `/admin/notes/${encodeURIComponent(id)}/archive`)),
  notesRestore: (id: string): Promise<NoteChange> => (USE_MOCK ? mock().then((m) => m.notesRestore(id)) : http("POST", `/admin/notes/${encodeURIComponent(id)}/restore`)),
  notesPurge: (id: string, confirmTitle: string): Promise<{ ok: true }> =>
    USE_MOCK ? mock().then((m) => m.notesPurge(id, confirmTitle)) : http("POST", `/admin/notes/${encodeURIComponent(id)}/purge`, { confirm_title: confirmTitle }),
  notesAudit: (id: string): Promise<NoteAudit[]> => (USE_MOCK ? mock().then((m) => m.notesAudit(id)) : http("GET", `/admin/notes/${encodeURIComponent(id)}/audit`)),

  // ---- Question bank (instructor only)
  bankList: (f: BankFilters): Promise<BankList> => (USE_MOCK ? mock().then((m) => m.bankList(f)) : http("GET", `/admin/bank${qs({ ...f, flagged: f.flagged ? "true" : undefined } as Query)}`)),
  bankGet: (id: string): Promise<BankDetail> => (USE_MOCK ? mock().then((m) => m.bankGet(id)) : http("GET", `/admin/bank/${encodeURIComponent(id)}`)),
  bankCreate: (d: BankData & { note?: string }): Promise<BankDetail> => (USE_MOCK ? mock().then((m) => m.bankCreate(d)) : http("POST", "/admin/bank", d)),
  bankSave: (id: string, d: BankData & { note?: string }): Promise<BankDetail> => (USE_MOCK ? mock().then((m) => m.bankSave(id, d)) : http("PUT", `/admin/bank/${encodeURIComponent(id)}`, d)),
  bankBulk: (ids: string[], action: string, value = ""): Promise<{ changed: number }> => (USE_MOCK ? mock().then((m) => m.bankBulk(ids, action, value)) : http("POST", "/admin/bank/bulk", { ids, action, value })),
  bankRestore: (id: string, version: number): Promise<BankDetail> => (USE_MOCK ? mock().then((m) => m.bankRestore(id, version)) : http("POST", `/admin/bank/${encodeURIComponent(id)}/restore`, { version })),
  bankComment: (id: string, text: string): Promise<BankDetail> => (USE_MOCK ? mock().then((m) => m.bankComment(id, text)) : http("POST", `/admin/bank/${encodeURIComponent(id)}/comments`, { text })),
  bankCheck: (id: string): Promise<BankDetail> => (USE_MOCK ? mock().then((m) => m.bankCheck(id)) : http("POST", `/admin/bank/${encodeURIComponent(id)}/check`)),
  bankDismiss: (id: string, kind: string, code: string, dismissed: boolean): Promise<BankDetail> =>
    USE_MOCK ? mock().then((m) => m.bankDismiss(id, kind, code, dismissed)) : http("POST", `/admin/bank/${encodeURIComponent(id)}/flags/dismiss`, { kind, code, dismissed }),
  bankRecheck: (id: string): Promise<BankDetail> => (USE_MOCK ? mock().then((m) => m.bankRecheck(id)) : http("POST", `/admin/bank/${encodeURIComponent(id)}/recheck`)),
  bankImportPreview: (file: File | null, importId?: string, mapping?: Record<string, string>): Promise<BankImportPreview> => {
    if (USE_MOCK) return mock().then((m) => m.bankImportPreview(file?.name ?? "", importId, mapping));
    const f = new FormData();
    if (file) f.append("file", file);
    if (importId) f.append("import_id", importId);
    if (mapping) f.append("mapping", JSON.stringify(mapping));
    return http("POST", "/admin/bank/import/preview", f);
  },
  bankImportCommit: (importId: string, mapping: Record<string, string>, status: string, use: string): Promise<BankImportResult> =>
    USE_MOCK ? mock().then((m) => m.bankImportCommit(importId, mapping, status, use)) : http("POST", "/admin/bank/import/commit", { import_id: importId, mapping, status, use, skip_duplicates: true }),
  bankExportUrl: (f: BankFilters): string => `${BASE}/api/admin/bank/export.csv${qs({ ...f, page: undefined, flagged: f.flagged ? "true" : undefined } as Query)}`,
  bankTemplateUrl: (kind: "csv" | "xlsx"): string => `${BASE}/api/admin/bank/template.${kind}`,

  // ---- Guide image annotations (instructor only)
  annotations: (guideId: string): Promise<AnnGuide> => (USE_MOCK ? mock().then((m) => m.annotations(guideId)) : http("GET", `/admin/guides/${encodeURIComponent(guideId)}/annotations`)),
  addMark: (guideId: string, body: { slide: number; crop?: number; kind: MarkKind; geom: Record<string, unknown>; text?: string; step?: number | null }): Promise<Mark> =>
    USE_MOCK ? mock().then((m) => m.addMark(guideId, body)) : http("POST", `/admin/guides/${encodeURIComponent(guideId)}/marks`, body),
  editMark: (guideId: string, markId: string, patch: { geom?: Record<string, unknown>; text?: string; step?: number | null }): Promise<Mark> =>
    USE_MOCK ? mock().then((m) => m.editMark(guideId, markId, patch)) : http("PUT", `/admin/guides/${encodeURIComponent(guideId)}/marks/${encodeURIComponent(markId)}`, patch),
  deleteMark: (guideId: string, markId: string): Promise<{ ok: true }> =>
    USE_MOCK ? mock().then((m) => m.deleteMark(guideId, markId)) : http("DELETE", `/admin/guides/${encodeURIComponent(guideId)}/marks/${encodeURIComponent(markId)}`),
  reorderMarks: (guideId: string, slide: number, crop: number, ids: string[]): Promise<{ ok: true }> =>
    USE_MOCK ? mock().then((m) => m.reorderMarks(guideId, slide, ids)) : http("POST", `/admin/guides/${encodeURIComponent(guideId)}/marks/reorder`, { slide, crop, ids }),
  reviewCrop: (guideId: string, slide: number, crop: number, ok: boolean): Promise<{ ok: true }> =>
    USE_MOCK ? mock().then((m) => m.reviewCrop(guideId, slide, crop, ok)) : http("POST", `/admin/guides/${encodeURIComponent(guideId)}/slides/${slide}/crops/${crop}/review`, { ok }),
  explainStation: (guideId: string, index: number, bodyType?: GuideBodyType | null): Promise<Explanation> =>
    USE_MOCK ? mock().then((m) => m.explainStation(guideId, index, bodyType)) : http("POST", `/guides/${encodeURIComponent(guideId)}/stations/${index}/explain`, bodyType ? { body_type: bodyType } : {}),
  approveStation: (guideId: string, index: number, approve: boolean): Promise<{ changed: number }> =>
    USE_MOCK ? mock().then((m) => m.approveStation(guideId, index, approve)) : http("POST", `/admin/guides/${encodeURIComponent(guideId)}/stations/${index}/approve`, { approve }),
};
