// The ONLY place that talks to the backend. One typed function per endpoint of docs/api_contract.md.
// VITE_USE_MOCK !== "false" (the default) -> realistic mock data from ./mock with a 600 to 1,200 ms delay.
// VITE_USE_MOCK === "false"               -> fetch(`${VITE_API_URL ?? ""}/api/...`, { credentials: "include" }).
import type {
  AdminStats, AskBody, AskStatus, ChatDetail, ChatSummary, GuideSummary, Me, Message, OpenQuiz, QuestionPage, QuizBuildBody, QuizHistoryItem,
  QuizJob, QuizLatest, QuizResults, ReviewPage, Scope, Station, StationCheck, Student, User,
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
      headers: { ...(body !== undefined ? { "Content-Type": "application/json" } : {}), Accept: "application/json", ...(extra?.headers ?? {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
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
    USE_MOCK ? mock().then((m) => m.ask(body, requestId)) : http("POST", "/ask", body, requestId ? { headers: { "X-Request-Id": requestId } } : undefined),
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
  checkStation: (id: string, index: number, description: string): Promise<StationCheck> =>
    USE_MOCK ? mock().then((m) => m.checkStation(id, index, description)) : http("POST", `/guides/${encodeURIComponent(id)}/stations/${index}/check`, { description }),

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

  // ---- Instructor
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
};
