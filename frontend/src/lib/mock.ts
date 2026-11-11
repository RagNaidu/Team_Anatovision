// Mock backend for VITE_USE_MOCK=true. Same shapes as docs/api_contract.md. State lives in memory (the signed-in user in sessionStorage,
// so a page reload keeps you signed in, like the real httpOnly cookie). Any password works. Users: "inglis" (instructor), "student1".
import { ApiError } from "./api";
import type {
  AdminStats, AskBody, AskStatus, ChatDetail, ChatSummary, BodyTip, GuideBodyType, GuideHistoryItem, GuideSummary, Me, Message, OpenQuiz, QuestionPage, QuestionRow, QuizBuildBody,
  QuizHistoryItem, QuizJob, QuizLatest, QuizResults, ResultQuestion, ReviewItem, ReviewPage, Scope, Source, Station, StationCheck, Student, User, WebQuizPage,
  AnnGuide, Explanation, Mark, MarkKind, SlideImage,
} from "./types";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const delay = () => sleep(600 + Math.random() * 600);
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
const iso = (daysAgo: number, hour = 10) => {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  d.setHours(hour, 12, 0, 0);
  return d.toISOString();
};

// ---------------------------------------------------------------- users and session
const USERS: Record<string, User> = {
  inglis: { id: "inglis", name: "Dr. Inglis", role: "instructor" },
  student1: { id: "student1", name: "Student One", role: "student" },
  student2: { id: "student2", name: "Student Two", role: "student" },
};
interface Session { userId: string; preview: { profile: string; name: string } | null }
const KEY = "av_mock_session";
function readSession(): Session | null {
  try { const s = sessionStorage.getItem(KEY); return s ? (JSON.parse(s) as Session) : null; } catch { return null; }
}
function writeSession(s: Session | null) {
  try { if (s) sessionStorage.setItem(KEY, JSON.stringify(s)); else sessionStorage.removeItem(KEY); } catch { /* storage can be blocked */ }
}
function session(): Session {
  const s = readSession();
  if (!s) throw new ApiError("Please sign in again.", 401);
  return s;
}
function studentSession(): Session {
  const s = session();
  if (USERS[s.userId].role === "instructor" && !s.preview) throw new ApiError("Chats, questions and quizzes are student tools. Start a preview to try them.", 403);
  return s;
}
function instructorSession(): Session {
  const s = session();
  if (USERS[s.userId].role !== "instructor") throw new ApiError("Only instructors can do that.", 403);
  return s;
}

export async function login(username: string, _password: string): Promise<{ user: User }> {
  await delay();
  const u = USERS[username.trim().toLowerCase()];
  if (!u) throw new ApiError("That username or password isn't right.", 401);
  writeSession({ userId: u.id, preview: null });
  return { user: u };
}
export async function logout(): Promise<{ ok: true }> {
  await sleep(150);
  writeSession(null);
  return { ok: true };
}
export async function me(): Promise<Me> {
  await sleep(250);
  const s = session();
  return { user: USERS[s.userId], preview: s.preview };
}

// ---------------------------------------------------------------- scope
const LECTURES = [
  { id: "L08", title: "Lecture 08 - Anterior and Medial Thigh", granted: true },
  { id: "L09", title: "Lecture 09 - The Hand", granted: true },
  { id: "L10", title: "Lecture 10 - Gluteal Region", granted: true },
  { id: "L11", title: "Lecture 11 - Posterior Thigh and Popliteal Fossa", granted: true },
  { id: "L12", title: "Lecture 12 - The Leg and Foot", granted: false },
];
const GUIDE_LIST: GuideSummary[] = [
  { id: "class-17", class_number: 17, title: "The Hip and Knee Joints", region: "Lower limb", station_count: 4, granted: true },
  { id: "class-14", class_number: 14, title: "Gluteal Region", region: "Lower limb", station_count: 4, granted: true },
  { id: "class-10", class_number: 10, title: "The Hand", region: "Upper limb", station_count: 3, granted: true },
  { id: "class-05", class_number: 5, title: "The Back and Vertebral Column", region: "Back", station_count: 3, granted: true },
  { id: "class-25", class_number: 25, title: "Pleural Cavities and Lungs", region: "Thorax", station_count: 3, granted: false },
];
export async function scope(): Promise<Scope> {
  await delay();
  session();
  return {
    lectures: clone(LECTURES),
    guides: GUIDE_LIST.map((g) => ({ id: g.id, class_number: g.class_number, title: g.title, lecture_ids: g.id === "class-17" ? ["L08", "L11"] : g.id === "class-10" ? ["L09"] : [], granted: g.granted })),
  };
}

// ---------------------------------------------------------------- sources and answers
const S_NOTES: Source = {
  n: 1, type: "notes", title: "Lecture notes", subtitle: "Lecture 08, Anterior and Medial Thigh", lecture_id: "L08", url: null,
  snippet: "The femoral triangle is bounded superiorly by the inguinal ligament, laterally by the medial border of sartorius, and medially by the medial border of adductor longus. Its floor is formed by iliopsoas, pectineus and adductor longus.",
  retrieved_at: null, license: null,
};
const S_OPENSTAX: Source = {
  n: 2, type: "openstax", title: "OpenStax Anatomy & Physiology 2e, section 11.6", subtitle: "Appendicular Muscles of the Pelvic Girdle and Lower Limbs", lecture_id: null,
  url: "https://openstax.org/books/anatomy-and-physiology-2e/pages/11-6-appendicular-muscles-of-the-pelvic-girdle-and-lower-limbs",
  snippet: "The muscles of the anterior thigh flex the hip and extend the knee. The fascia lata surrounds the thigh muscles like a stocking.",
  retrieved_at: null, license: "CC BY-NC-SA 4.0",
};
const FEMORAL: Omit<Message, "id" | "created_at"> = {
  role: "assistant", kind: "answer", timing_ms: 6800,
  markdown:
    "The femoral triangle is a region in the upper anterior thigh.\n\n**Boundaries**\n- Superior: inguinal ligament [1]\n- Lateral: medial border of sartorius [1]\n- Medial: medial border of adductor longus [1]\n\n**Floor:** iliopsoas, pectineus and adductor longus [1]\n\n**Roof:** fascia lata [2]\n\n**Contents (lateral to medial):** femoral nerve, femoral artery, femoral vein and deep inguinal lymph nodes [1][2]",
  sources: [S_NOTES, S_OPENSTAX], footer: null,
};
const APEX: Omit<Message, "id" | "created_at"> = {
  role: "assistant", kind: "term_lookup", timing_ms: 1900,
  markdown:
    "**Apex** appears in a few places in your notes:\n- **Femoral triangle:** the apex points inferiorly, where sartorius crosses adductor longus [1]\n- **Heart:** the apex is formed by the left ventricle [2]\n- **Lung:** the apex rises above the clavicle into the root of the neck [2]\n\nAsk about a specific one for more detail.",
  sources: [
    { ...S_NOTES, n: 1, snippet: "The apex of the femoral triangle points inferiorly, where sartorius crosses adductor longus." },
    { n: 2, type: "notes", title: "Lecture notes", subtitle: "Lecture 22, The Heart › Surfaces", lecture_id: "L22", url: null, snippet: "The apex of the heart is formed by the left ventricle and lies in the fifth intercostal space.", retrieved_at: null, license: null },
  ],
  footer: null,
};
const REFUSED: Omit<Message, "id" | "created_at"> = {
  role: "assistant", kind: "refused", timing_ms: 900,
  markdown: "I can't help with medication dosing. This assistant answers anatomy questions from your course material.", sources: [], footer: null,
};
const WALDEYER: Omit<Message, "id" | "created_at"> = {
  role: "assistant", kind: "answer", timing_ms: 9400,
  markdown:
    "Waldeyer's ring is a ring of lymphoid tissue in the pharynx [1].\n\n**What it includes**\n- The pharyngeal tonsil (adenoids) in the roof of the nasopharynx [1]\n- The paired tubal tonsils [1]\n- The paired palatine tonsils [1]\n- The lingual tonsil at the back of the tongue [1]",
  sources: [{
    n: 1, type: "wikipedia", title: "Wikipedia: Waldeyer's tonsillar ring", subtitle: "Wikipedia", lecture_id: null,
    url: "https://en.wikipedia.org/wiki/Waldeyer%27s_tonsillar_ring",
    snippet: "Waldeyer's tonsillar ring is an annular arrangement of lymphoid tissue in the pharynx. The ring consists of the pharyngeal tonsil, tubal tonsils, palatine tonsils and lingual tonsil.",
    retrieved_at: new Date().toISOString().slice(0, 10), license: "CC BY-SA 4.0",
  }],
  footer: { basis_line: "Based on Wikipedia, not your lecture notes.", access_note: null },
};
const NOT_COVERED: Omit<Message, "id" | "created_at"> = {
  role: "assistant", kind: "not_covered", timing_ms: 1300,
  markdown: "That isn't covered in the material you have open. Try naming the structure or region, or ask your instructor.", sources: [], footer: null,
};
const SIMPLE: Omit<Message, "id" | "created_at"> = {
  role: "assistant", kind: "answer", timing_ms: 4200,
  markdown: "In plain words: the femoral triangle is a small, triangle-shaped hollow at the top of the inner thigh [1]. The groin crease forms the top edge, and two thigh muscles, sartorius and adductor longus, form the sides [1]. The main nerve, artery and vein to the leg pass through it [1].",
  sources: [S_NOTES], footer: null,
};
const NOTES_GATED: Omit<Message, "id" | "created_at"> = {
  role: "assistant", kind: "answer", timing_ms: 5200,
  markdown: "The sciatic nerve leaves the pelvis through the greater sciatic foramen, below piriformis [1].\n\nIn the thigh it runs deep to the long head of biceps femoris [1].",
  sources: [{ ...S_OPENSTAX, n: 1, title: "OpenStax Anatomy & Physiology 2e, section 13.4", subtitle: "The Peripheral Nervous System", snippet: "The sciatic nerve is the largest nerve in the body. It exits the pelvis through the greater sciatic foramen and runs down the posterior thigh." }],
  footer: { basis_line: "Based on OpenStax and Wikipedia, not Dr. Inglis's notes.", access_note: "Dr. Inglis's notes for this are in Lecture 12, which you don't have yet. Ask him to open it." },
};

const STEPS: Omit<Message, "id" | "created_at"> = {
  role: "assistant", kind: "answer", timing_ms: 7300,
  markdown:
    "The guide gives these steps for exposing the femoral triangle [1].\n\n1. Mark the anterior superior iliac spine and the pubic tubercle, then cut through skin only along the line between them [1].\n2. Reflect the skin flaps medially and laterally to expose the superficial fascia. Take care to keep the great saphenous vein, which you will need later [1].\n3. Clean the fascia lata below the inguinal ligament:\n   - Remove the fat and lymph nodes in the way.\n   - Keep the femoral sheath intact until you reach it.\n4. Open the femoral sheath along the line of the vessels and identify, from lateral to medial, the artery, the vein and the femoral canal [1].\n\nSlide 8 shows the sheath open.",
  sources: [{ ...S_NOTES, type: "guide", title: "Dissection guide", subtitle: "Class 17, slides 3-8", snippet: "Mark the anterior superior iliac spine and the pubic tubercle. Cut through skin only. Reflect the skin flaps." }],
  footer: null,
};

/** image cards for the mock "how do I expose ..." answer (empty while the module is still loading: the sample chats are built before the guide data exists) */
function stepImages(): SlideImage[] {
  try { return [3, 5].map((n, i) => ({ ...slideImage("class-17", n, STATIONS["class-17"][i].title), guide_id: "class-17", source_n: 1, step: i === 0 ? 0 : 1 })); } catch { return []; }
}

function pickAnswer(q: string): Omit<Message, "id" | "created_at"> {
  const t = q.toLowerCase();
  if (t.startsWith("explain this more simply")) return SIMPLE;
  if (/amoxicillin|dose|dosage|prescri|how much .* mg/.test(t)) return REFUSED;
  if (/waldeyer/.test(t)) return WALDEYER;
  if (/sciatic/.test(t)) return NOTES_GATED;
  if (/^\s*apex\s*\??$/.test(t)) return APEX;
  if (/\bhow (do|can) i\b.*expose|steps/.test(t)) return { ...STEPS, images: stepImages() };
  if (/femoral triangle|expose the femoral/.test(t)) return FEMORAL;
  return NOT_COVERED;
}

// ---------------------------------------------------------------- chats (in memory)
interface ChatRec { id: string; title: string; updated_at: string; messages: Message[] }
function userMsg(chatId: string, n: number, text: string, when: string): Message {
  return { id: `${chatId}:${n}`, role: "user", created_at: when, kind: "answer", markdown: text, sources: [], footer: null, timing_ms: 0 };
}
function pair(chatId: string, q: string, when: string): Message[] {
  const a = pickAnswer(q);
  return [userMsg(chatId, 0, q, when), { ...clone(a), id: `${chatId}:1`, created_at: when }];
}
const CHATS: ChatRec[] = [
  { id: "c101", title: "Femoral triangle boundaries", updated_at: iso(0, 9), messages: pair("c101", "What are the boundaries and contents of the femoral triangle?", iso(0, 9)) },
  { id: "c102", title: "apex", updated_at: iso(0, 8), messages: pair("c102", "apex", iso(0, 8)) },
  { id: "c103", title: "Waldeyer's ring", updated_at: iso(1, 16), messages: pair("c103", "What is Waldeyer's ring?", iso(1, 16)) },
  { id: "c104", title: "Sciatic nerve course", updated_at: iso(3, 11), messages: pair("c104", "Where does the sciatic nerve leave the pelvis?", iso(3, 11)) },
  { id: "c105", title: "Hip joint ligaments", updated_at: iso(5, 14), messages: pair("c105", "Which ligaments strengthen the hip joint?", iso(5, 14)) },
  { id: "c106", title: "Dissecting the gluteal region", updated_at: iso(12, 10), messages: pair("c106", "How do I expose the femoral triangle?", iso(12, 10)) },
];
CHATS[5].messages[1].sources[0].revision = "updated";      // an old answer whose source the revised notes changed
let previewChats: ChatRec[] = [];
function chatStore(): ChatRec[] { return readSession()?.preview ? previewChats : CHATS; }
function findChat(id: string): ChatRec {
  const c = chatStore().find((x) => x.id === id);
  if (!c) throw new ApiError("That chat wasn't found.", 404);
  return c;
}
export async function listChats(): Promise<ChatSummary[]> {
  await delay();
  studentSession();
  if (readSession()?.preview) return [];
  return CHATS.filter((c) => c.messages.length > 0).sort((a, b) => b.updated_at.localeCompare(a.updated_at)).map(({ id, title, updated_at }) => ({ id, title, updated_at }));
}
export async function createChat(): Promise<ChatSummary> {
  await sleep(250);
  studentSession();
  const reuse = chatStore().find((c) => c.messages.length === 0);
  if (reuse) return { id: reuse.id, title: reuse.title, updated_at: reuse.updated_at };
  const preview = Boolean(readSession()?.preview);
  const id = `${preview ? "preview-" : "c"}${Math.random().toString(36).slice(2, 8)}`;
  const rec: ChatRec = { id, title: "New chat", updated_at: new Date().toISOString(), messages: [] };
  chatStore().push(rec);
  return { id, title: rec.title, updated_at: rec.updated_at };
}
export async function getChat(id: string): Promise<ChatDetail> {
  await delay();
  studentSession();
  const c = findChat(id);
  return clone({ id: c.id, title: c.title, messages: c.messages });
}
export async function renameChat(id: string, title: string): Promise<{ id: string; title: string }> {
  await sleep(250);
  studentSession();
  const c = findChat(id);
  c.title = title.trim().slice(0, 80) || c.title;
  return { id, title: c.title };
}
export async function deleteChat(id: string): Promise<{ ok: true }> {
  await sleep(250);
  studentSession();
  const store = chatStore();
  const i = store.findIndex((c) => c.id === id);
  if (i < 0) throw new ApiError("That chat wasn't found.", 404);
  store.splice(i, 1);
  return { ok: true };
}

// ---------------------------------------------------------------- ask
const PLANS = new Map<string, { start: number; total: number }>();
export async function ask(body: AskBody, requestId?: string): Promise<Message> {
  studentSession();
  if (!body.question.trim()) throw new ApiError("Please type a question.", 422);
  if (body.question.length > 600) throw new ApiError("Questions can be up to 600 characters.", 422);
  if (body.body_type && !/^(more|average|less) fat, (more|average|less) muscle, (large|average|small) build$/.test(body.body_type)) throw new ApiError("Please check what you entered.", 422);
  const chat = findChat(body.chat_id);
  const total = 1800 + Math.random() * 1400;
  if (requestId) PLANS.set(requestId, { start: Date.now(), total });
  await sleep(total);
  const when = new Date().toISOString();
  const q = userMsg(chat.id, chat.messages.length, body.question, when);
  const template = pickAnswer(body.question);
  const a: Message = { ...clone(template), id: `${chat.id}:${chat.messages.length + 1}`, created_at: new Date().toISOString(), timing_ms: Math.round(total) };
  if (body.length === "detailed" && a.kind === "answer") a.markdown += "\n\n**Why it matters:** the femoral sheath and its contents are a common landmark for access to the leg [1].";
  chat.messages.push(q, a);
  if (chat.title === "New chat") chat.title = body.question.length > 48 ? body.question.slice(0, 48).replace(/\s+\S*$/, "") + "…" : body.question;
  chat.updated_at = when;
  if (requestId) setTimeout(() => PLANS.delete(requestId), 5000);
  return clone(a);
}
const STAGES = ["searching", "reading", "writing", "checking"] as const;
export async function askStatus(requestId: string): Promise<AskStatus | null> {
  const p = PLANS.get(requestId);
  if (!p) return null; // like the real API: 404 until the POST registered the id
  const frac = (Date.now() - p.start) / p.total;
  if (frac >= 1) return { stage: "done" };
  return { stage: STAGES[Math.min(3, Math.floor(frac * 4))] };
}
export async function flagMessage(_id: string, reason: string, _comment?: string): Promise<{ ok: true }> {
  await sleep(300);
  studentSession();
  if (!reason.trim()) throw new ApiError("Choose a reason.", 422);
  return { ok: true };
}

// ---------------------------------------------------------------- guide slide images and marks (SAMPLE pictures drawn in the browser: no real slides in the mock)
function slideSvg(n: number, title: string, full = false): string {
  const art = `<ellipse cx="0" cy="0" rx="250" ry="260" fill="#E7B7A8"/><ellipse cx="-60" cy="-70" rx="120" ry="90" fill="#C8665B"/><rect x="-30" y="20" width="60" height="210" rx="30" fill="#F3E2B0"/><ellipse cx="110" cy="90" rx="70" ry="45" fill="#8EB7C9"/>`;
  const svg = full
    ? `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"><rect width="1280" height="720" fill="#FFFFFF"/><text x="70" y="80" font-family="Georgia,serif" font-size="40" fill="#1B1B1F">${title.replace(/&/g, "and").slice(0, 30)}</text>${[0, 1, 2, 3, 4].map((i) => `<rect x="70" y="${120 + i * 70}" width="${430 - (i % 2) * 90}" height="22" rx="11" fill="#CFC6B8"/>`).join("")}<g transform="translate(860 380)">${art}</g><text x="640" y="700" text-anchor="middle" font-family="Arial,sans-serif" font-size="22" fill="#8A8A8A">Original slide ${n} (mock)</text></svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 1000"><rect width="1200" height="1000" fill="#FFFFFF"/><g transform="translate(600 480) scale(1.5)">${art}</g><text x="600" y="975" text-anchor="middle" font-family="Arial,sans-serif" font-size="22" fill="#8A8A8A">Sample picture ${n} (mock, no slide text)</text></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}
const GUIDE_MARKS: Record<string, Mark[]> = {};   // `${guide}:${slide}` -> marks (all statuses)
const mk = (slide: number, kind: MarkKind, geom: Record<string, unknown>, step: number | null, status: "draft" | "approved", text = "", source: "manual" | "auto" = "manual"): Mark =>
  ({ id: `m-${Math.random().toString(16).slice(2, 10)}`, slide, kind, geom, text, step, n: 0, status, author: source === "auto" ? "auto" : "inglis", version: 1, source });
function seedMarks() {
  const put = (m: Mark) => { const k = `class-17:${m.slide}`; (GUIDE_MARKS[k] ??= []).push(m); m.n = GUIDE_MARKS[k].length; };
  put(mk(3, "label", { x: 0.55, y: 0.45 }, 0, "approved", "Anterior superior iliac spine"));
  put(mk(3, "arrow", { from: [0.45, 0.8], to: [0.62, 0.62] }, 0, "approved"));
  put(mk(3, "cut", { points: [[0.6, 0.4], [0.66, 0.6], [0.7, 0.8]] }, 1, "approved"));
  put(mk(3, "highlight", { cx: 0.7, cy: 0.62, rx: 0.1, ry: 0.14 }, 2, "approved"));
  put(mk(3, "label", { x: 0.72, y: 0.35 }, null, "draft", "Draft pin (students do not see this)", "auto"));
  put(mk(5, "label", { x: 0.64, y: 0.55 }, 0, "draft", "Great saphenous vein", "auto"));
  put(mk(5, "arrow", { from: [0.5, 0.3], to: [0.66, 0.5] }, 1, "draft", "", "auto"));
}
seedMarks();
const marksOf = (guide: string, slide: number, approvedOnly: boolean): Mark[] => (GUIDE_MARKS[`${guide}:${slide}`] ?? []).filter((m) => !approvedOnly || m.status === "approved");
const CHECKED = new Set<string>();   // low-confidence crops the (mock) instructor marked checked: `${guide}:${slide}:${crop}`
function slideImage(guide: string, slide: number, title: string, approvedOnly = true): SlideImage {
  const url = slideSvg(slide, title);
  const low = guide === "class-17" && slide === 8;
  return { slide, crop: 1, url, thumb_url: url, caption: `Slide ${slide} · Dr. Inglis's dissection guide`, alt: `Slide ${slide}: ${title}`, w: 1200, h: 1000, confidence: low ? "low" : "high", why: low ? "step text overlaps the picture" : "",
    reviewed: CHECKED.has(`${guide}:${slide}:1`), original_url: slideSvg(slide, title, true),
    marks: marksOf(guide, slide, approvedOnly).map((m, i) => (approvedOnly ? { id: m.id, slide: m.slide, crop: 1, kind: m.kind, geom: m.geom, text: m.text, step: m.step, n: i + 1 } : { ...m, crop: 1 })) };
}
function stationImages(guide: string, s: Station, approvedOnly = true): SlideImage[] {
  return guide === "class-17" ? s.slides.map((n) => slideImage(guide, n, s.title, approvedOnly)).filter((im) => !approvedOnly || im.confidence === "high" || im.reviewed) : [];
}
export async function reviewCrop(guideId: string, slide: number, crop: number, ok: boolean): Promise<{ ok: true }> {
  await delay(); instructorSession();
  const k = `${guideId}:${slide}:${crop}`; if (ok) CHECKED.add(k); else CHECKED.delete(k);
  return { ok: true };
}
export async function explainStation(guideId: string, index: number, bodyType?: GuideBodyType | null): Promise<Explanation> {
  await sleep(900); studentSession();
  const st = STATIONS[guideId]?.[index];
  if (!st || st.image_only) throw new ApiError("This station is a picture, so there is no text to explain.", 422);
  const bt = bodyType === "more_fat" ? " With more body fat, expect more fat to clear first." : "";
  return { text: `In this station you open the skin and fascia so the structures underneath come into view. The first cut only goes through the skin, so you do not damage what lies just below it.${bt}`, label: "AI explanation, check your guide",
    sources: [{ n: 1, type: "guide", title: "Dissection guide", subtitle: `Class ${guideId.slice(6)}, slide ${st.slides[0]}`, lecture_id: null, url: null, snippet: st.steps.join(" "), retrieved_at: null, license: null }] };
}

// ---------------------------------------------------------------- guides
const STATIONS: Record<string, Station[]> = {
  "class-17": [
    { index: 0, title: "Skin incision over the anterior thigh", slides: [3, 4], image_only: false, steps: ["Mark the anterior superior iliac spine and the pubic tubercle.", "Cut through skin only, from the iliac spine to the tibial tuberosity, keeping the blade shallow.", "Reflect the skin flaps medially and laterally to expose the superficial fascia."] },
    { index: 1, title: "Find the great saphenous vein", slides: [5, 6], image_only: false, steps: ["Look for the great saphenous vein in the superficial fascia near the saphenous opening.", "Follow the vein proximally to where it passes through the cribriform fascia.", "Note the superficial inguinal lymph nodes around it."] },
    { index: 2, title: "Open the femoral sheath", slides: [7, 8, 9], image_only: false, steps: ["Clean the fascia lata below the inguinal ligament.", "Incise the femoral sheath along the line of the femoral vessels.", "Identify the femoral artery, vein and canal from lateral to medial."] },
    { index: 3, title: "Hip joint capsule", slides: [14], image_only: true, steps: [] },
  ],
  "class-14": [
    { index: 0, title: "Reflect gluteus maximus", slides: [2, 3], image_only: false, steps: ["Place the cadaver prone with a block under the pelvis.", "Detach gluteus maximus from the sacrum and iliac crest.", "Reflect the muscle laterally, protecting the inferior gluteal vessels."] },
    { index: 1, title: "Identify piriformis", slides: [4], image_only: false, steps: ["Find the lower border of gluteus medius.", "Piriformis lies deep, passing through the greater sciatic foramen."] },
    { index: 2, title: "Trace the sciatic nerve", slides: [5, 6], image_only: false, steps: ["Locate the sciatic nerve emerging below piriformis.", "Follow it distally deep to the long head of biceps femoris."] },
    { index: 3, title: "Gluteal bursae", slides: [7], image_only: false, steps: ["Palpate the trochanteric bursa over the greater trochanter."] },
  ],
  "class-10": [
    { index: 0, title: "Palmar skin and fascia", slides: [2], image_only: false, steps: ["Cut the skin along the flexor creases.", "Reflect the palmar aponeurosis."] },
    { index: 1, title: "Carpal tunnel contents", slides: [3, 4], image_only: false, steps: ["Divide the flexor retinaculum.", "Identify the median nerve and the flexor tendons."] },
    { index: 2, title: "Hypothenar muscles", slides: [5], image_only: false, steps: ["Identify abductor, flexor and opponens digiti minimi."] },
  ],
  "class-05": [
    { index: 0, title: "Superficial back muscles", slides: [2], image_only: false, steps: ["Reflect trapezius and latissimus dorsi."] },
    { index: 1, title: "Erector spinae", slides: [3], image_only: false, steps: ["Separate iliocostalis, longissimus and spinalis."] },
    { index: 2, title: "Vertebral canal", slides: [4, 5], image_only: false, steps: ["Remove the laminae to open the canal.", "Open the dura to see the spinal cord."] },
  ],
};
const LECTURE_STATIONS: Station[] = [
  { index: 0, title: "Anterior thigh: overview", slides: [], image_only: false, steps: ["The anterior thigh holds the quadriceps and sartorius.", "Its compartment is supplied by the femoral nerve."] },
  { index: 1, title: "Femoral triangle", slides: [], image_only: false, steps: ["Superior: inguinal ligament. Lateral: sartorius. Medial: adductor longus.", "Contents from lateral to medial: nerve, artery, vein, lymphatics."] },
  { index: 2, title: "Adductor canal", slides: [], image_only: false, steps: ["Runs from the apex of the femoral triangle to the adductor hiatus."] },
];
export async function listGuides(): Promise<GuideSummary[]> {
  await delay();
  session();
  return clone(GUIDE_LIST);
}
export async function guideStations(id: string): Promise<Station[]> {
  await delay();
  session();
  const g = GUIDE_LIST.find((x) => x.id === id);
  if (!g || !STATIONS[id]) throw new ApiError("That guide wasn't found.", 404);
  if (!g.granted) throw new ApiError("That guide isn't open to you yet. Ask your instructor.", 403);
  return clone(STATIONS[id].map((st) => ({ ...st, images: stationImages(id, st) })));
}
export async function annotations(guideId: string): Promise<AnnGuide> {
  await delay(); instructorSession();
  const sts = STATIONS[guideId];
  if (!sts) throw new ApiError("That guide was not found.", 404);
  return clone({ guide_id: guideId, title: GUIDE_LIST.find((g) => g.id === guideId)?.title ?? guideId, rendered: true, stations: sts.map((st) => {
    const images = stationImages(guideId, st, false);
    const all = images.flatMap((i) => i.marks);
    return { index: st.index, title: st.title, steps: st.steps, slides: st.slides, image_only: st.image_only, images, drafts: all.filter((m) => m.status === "draft").length, approved: all.filter((m) => m.status === "approved").length };
  }) });
}
function findMark(guideId: string, markId: string): [string, Mark] {
  for (const [k, list] of Object.entries(GUIDE_MARKS)) if (k.startsWith(guideId + ":")) { const m = list.find((x) => x.id === markId); if (m) return [k, m]; }
  throw new ApiError("That mark was not found.", 404);
}
export async function addMark(guideId: string, body: { slide: number; kind: MarkKind; geom: Record<string, unknown>; text?: string; step?: number | null }): Promise<Mark> {
  await delay(); instructorSession();
  if (body.kind === "label" && !(body.text ?? "").trim()) throw new ApiError("A label needs its text.", 422);
  const k = `${guideId}:${body.slide}`;
  const m = mk(body.slide, body.kind, body.geom, body.step ?? null, "draft", body.text ?? "");
  (GUIDE_MARKS[k] ??= []).push(m); m.n = GUIDE_MARKS[k].length;
  return clone(m);
}
export async function editMark(guideId: string, markId: string, patch: { geom?: Record<string, unknown>; text?: string; step?: number | null }): Promise<Mark> {
  await delay(); instructorSession();
  const [, m] = findMark(guideId, markId);
  const before = JSON.stringify([m.geom, m.text, m.step]);
  if (patch.geom) m.geom = patch.geom; if (patch.text !== undefined) m.text = patch.text; if ("step" in patch) m.step = patch.step ?? null;
  if (JSON.stringify([m.geom, m.text, m.step]) !== before) { m.status = "draft"; m.version = (m.version ?? 1) + 1; }
  return clone(m);
}
export async function deleteMark(guideId: string, markId: string): Promise<{ ok: true }> {
  await delay(); instructorSession();
  const [k, m] = findMark(guideId, markId);
  GUIDE_MARKS[k] = GUIDE_MARKS[k].filter((x) => x !== m);
  return { ok: true };
}
export async function reorderMarks(guideId: string, slide: number, ids: string[]): Promise<{ ok: true }> {
  await delay(); instructorSession();
  const k = `${guideId}:${slide}`;
  GUIDE_MARKS[k] = ids.map((id) => GUIDE_MARKS[k].find((m) => m.id === id)!).filter(Boolean); GUIDE_MARKS[k].forEach((m, i) => { m.n = i + 1; });
  return { ok: true };
}
export async function approveStation(guideId: string, index: number, approve: boolean): Promise<{ changed: number }> {
  await delay(); instructorSession();
  const st = STATIONS[guideId]?.[index]; let n = 0;
  for (const slide of st?.slides ?? []) for (const m of GUIDE_MARKS[`${guideId}:${slide}`] ?? []) if ((m.status === "approved") !== approve) { m.status = approve ? "approved" : "draft"; n++; }
  return { changed: n };
}
export async function lectureStations(id: string): Promise<Station[]> {
  await delay();
  session();
  const l = LECTURES.find((x) => x.id === id);
  if (!l) throw new ApiError("That lecture wasn't found.", 404);
  if (!l.granted) throw new ApiError("That lecture isn't open to you yet. Ask your instructor.", 403);
  return clone(LECTURE_STATIONS);
}
export async function guideBodyTip(id: string, index: number, bodyType: GuideBodyType): Promise<BodyTip> {
  await delay();
  studentSession();
  const st = STATIONS[id]?.[index];
  if (!st) throw new ApiError("That station was not found.", 404);
  if (st.image_only || bodyType === "average" || bodyType === "not_sure") return { body_type: bodyType, lines: [] };
  const general: Record<string, string> = {
    more_fat: "General tip, not from your notes: expect more fat and thicker superficial fascia to clear before structures appear, and they may lie deeper.",
    more_muscular: "General tip, not from your notes: muscles may be bulkier, so structures may lie deeper between them.",
    lean: "General tip, not from your notes: there is less fat to clear, so structures may lie nearer the surface.",
  };
  return { body_type: bodyType, lines: [
    ...(bodyType === "more_fat" && /fascia|skin/i.test(st.steps.join(" ")) ? [{ text: "The guide has you work through skin and fascia here, so expect more fat to clear first.", general: false }] : []),
    { text: general[bodyType], general: true },
  ] };
}

export async function checkStation(id: string, index: number, description: string, bodyType?: GuideBodyType | null): Promise<StationCheck> {
  await delay();
  studentSession();
  const st = STATIONS[id]?.[index];
  if (!st) throw new ApiError("That station wasn't found.", 404);
  if (st.image_only) throw new ApiError(`This station is a picture. See slide ${st.slides[0]} in your lab guide.`, 422);
  const src: Source = { n: 1, type: "guide", title: "Dissection guide", subtitle: `Class ${id.slice(6)}, slide ${st.slides[0]}`, lecture_id: id === "class-17" ? "L08" : null, url: null, snippet: st.steps.join(" "), retrieved_at: null, license: null };
  const t = description.toLowerCase();
  if (/error|fail/.test(t)) throw new ApiError("The AI service couldn't check that. Please try again.", 502);
  if (t.length < 25) return { verdict: "not_matching", feedback_markdown: "That doesn't match this station yet. The guide asks for the following: " + st.steps[0] + " [1]", sources: [src] };
  const tip = bodyType === "more_fat" ? " General tip, not from your notes: with more body fat, expect more fat to clear before the vein appears." : "";
  if (/sartorius|saphenous|piriformis|median|vein|artery|nerve/.test(t)) return { verdict: "correct", feedback_markdown: "That matches the guide. " + st.steps[st.steps.length - 1] + " [1]" + tip, sources: [src] };
  return { verdict: "partly", feedback_markdown: "Part of that matches. You described the region, but the guide also asks you to do this: " + st.steps[0] + " [1]", sources: [src] };
}

// ---------------------------------------------------------------- quiz
const BANK: { lead: string; stem: string; options: string[]; answer: number; why: string; alts: string[]; evidence: string; span: string }[] = [
  { stem: "A student exposing the anterior thigh identifies a triangular depression below the inguinal ligament.", lead: "Which structure forms the lateral border of the femoral triangle?", options: ["Adductor longus", "Sartorius", "Pectineus", "Rectus femoris"], answer: 1, why: "The medial border of sartorius forms the lateral boundary of the femoral triangle.", alts: ["Adductor longus forms the medial border.", "", "Pectineus forms part of the floor.", "Rectus femoris lies lateral to the triangle."], evidence: "The femoral triangle is bounded superiorly by the inguinal ligament, laterally by the medial border of sartorius, and medially by the medial border of adductor longus.", span: "laterally by the medial border of sartorius" },
  { stem: "", lead: "Which structure lies most medially within the femoral triangle?", options: ["Femoral nerve", "Femoral artery", "Femoral vein", "Deep inguinal lymph nodes"], answer: 2, why: "From lateral to medial the contents are nerve, artery, vein and lymphatics. The vein is medial to the artery.", alts: ["The nerve is most lateral.", "The artery lies between the nerve and the vein.", "", "Lymph nodes lie in the femoral canal, medial to the vein, but are not a named vessel of the sheath."], evidence: "Contents (lateral to medial): femoral nerve, femoral artery, femoral vein and deep inguinal lymph nodes.", span: "femoral nerve, femoral artery, femoral vein" },
  { stem: "", lead: "What forms the roof of the femoral triangle?", options: ["Fascia lata", "Inguinal ligament", "Pectineus", "Iliopsoas"], answer: 0, why: "The fascia lata covers the triangle as its roof.", alts: ["", "The inguinal ligament is the superior border.", "Pectineus is part of the floor.", "Iliopsoas is part of the floor."], evidence: "Roof: fascia lata.", span: "fascia lata" },
  { stem: "", lead: "Which muscles form the floor of the femoral triangle?", options: ["Gracilis and sartorius", "Iliopsoas, pectineus and adductor longus", "Vastus medialis and rectus femoris", "Gluteus medius and piriformis"], answer: 1, why: "The floor is formed by iliopsoas, pectineus and adductor longus.", alts: ["Sartorius forms a border, not the floor.", "", "Those are quadriceps components lateral to the triangle.", "Those are gluteal muscles."], evidence: "Its floor is formed by iliopsoas, pectineus and adductor longus.", span: "iliopsoas, pectineus and adductor longus" },
  { stem: "", lead: "Where does the apex of the femoral triangle point?", options: ["Superiorly", "Laterally", "Inferiorly", "Medially"], answer: 2, why: "The apex points inferiorly, where sartorius crosses adductor longus.", alts: ["The base is superior.", "", "", "Medial is the adductor longus border."].map((s, i) => (i === 2 ? "" : s)), evidence: "The apex of the femoral triangle points inferiorly, where sartorius crosses adductor longus.", span: "points inferiorly" },
];
const WEB_BANK: typeof BANK = [
  { stem: "", lead: "Which tonsil sits in the roof of the nasopharynx?", options: ["Palatine tonsil", "Pharyngeal tonsil (adenoids)", "Lingual tonsil", "Tubal tonsil"], answer: 1, why: "The pharyngeal tonsil, also called the adenoids, lies in the roof of the nasopharynx.", alts: ["The palatine tonsils sit between the palatal arches.", "", "The lingual tonsil is at the back of the tongue.", "The tubal tonsils lie near the opening of the auditory tube."], evidence: "Waldeyer's tonsillar ring consists of the pharyngeal tonsil, tubal tonsils, palatine tonsils and lingual tonsil.", span: "pharyngeal tonsil, tubal tonsils, palatine tonsils and lingual tonsil" },
  { stem: "", lead: "What kind of tissue forms Waldeyer's ring?", options: ["Skeletal muscle", "Lymphoid tissue", "Cartilage", "Adipose tissue"], answer: 1, why: "It is an annular arrangement of lymphoid tissue in the pharynx.", alts: ["", "", "", ""].map((_, i) => (i === 1 ? "" : "Not what the ring is made of.")), evidence: "Waldeyer's tonsillar ring is an annular arrangement of lymphoid tissue in the pharynx.", span: "annular arrangement of lymphoid tissue in the pharynx" },
  { stem: "", lead: "Where is the lingual tonsil found?", options: ["Roof of the nasopharynx", "Back of the tongue", "Beside the auditory tube", "Between the palatal arches"], answer: 1, why: "The lingual tonsil is at the back of the tongue.", alts: ["That is the pharyngeal tonsil.", "", "That is the tubal tonsil.", "That is the palatine tonsil."], evidence: "The lingual tonsil is located at the back of the tongue.", span: "lingual tonsil is located at the back of the tongue" },
  { stem: "", lead: "In which part of the body is Waldeyer's ring found?", options: ["The pharynx", "The larynx", "The oesophagus", "The thorax"], answer: 0, why: "The ring surrounds the openings of the nose and mouth into the pharynx.", alts: ["", "Not the larynx.", "Not the oesophagus.", "Not the thorax."], evidence: "Waldeyer's tonsillar ring is an annular arrangement of lymphoid tissue in the pharynx.", span: "lymphoid tissue in the pharynx" },
  { stem: "", lead: "How many palatine tonsils are part of the ring?", options: ["One", "Two", "Three", "Four"], answer: 1, why: "There is one palatine tonsil on each side, so two.", alts: ["Only one palatine tonsil is not right.", "", "Not three.", "Not four."], evidence: "The ring includes two palatine tonsils, one on each side.", span: "two palatine tonsils, one on each side" },
];
interface QuizRec { id: string; status: "open" | "offer"; length: number; picks: Record<string, string[]>; current: number; submitted: string | null; user: string; title: string; web: boolean }
const QUIZZES = new Map<string, QuizRec>();
QUIZZES.set("qpast1", { id: "qpast1", status: "open", length: 5, picks: { 0: ["B"], 1: ["C"], 2: ["A"], 3: ["B"], 4: ["A"] }, current: 4, submitted: iso(0, 8), user: "student1", title: "Femoral triangle", web: false });
QUIZZES.set("qpast2", { id: "qpast2", status: "open", length: 5, picks: { 0: ["B"], 1: ["C"], 2: ["A"], 3: ["B"], 4: ["C"] }, current: 4, submitted: iso(9, 17), user: "student1", title: "The Hand +1", web: false });
QUIZZES.set("qpast3", { id: "qpast3", status: "open", length: 5, picks: { 0: ["B"], 1: ["B"], 2: ["A"], 3: ["A"], 4: ["C"] }, current: 4, submitted: iso(1, 12), user: "student1", title: "Waldeyer's ring", web: true });
const JOBS = new Map<string, { polls: number; body: QuizBuildBody; offer: boolean; fail: boolean; web: boolean }>();
let lastOffer: string | null = null;

function titleOf(b: QuizBuildBody): string {
  if (b.mode === "topic") return (b.topic ?? "Quiz").trim().replace(/^./, (c) => c.toUpperCase());
  const first = LECTURES.find((l) => b.lecture_ids?.includes(l.id))?.title.replace(/^Lecture \d+\s*-\s*/, "") ?? GUIDE_LIST.find((g) => b.guide_ids?.includes(g.id))?.title ?? "Quiz";
  const n = (b.lecture_ids?.length ?? 0) + (b.guide_ids?.length ?? 0);
  return n > 1 ? `${first} +${n - 1}` : first;
}

export async function buildQuiz(body: QuizBuildBody): Promise<{ job_id: string }> {
  await delay();
  studentSession();
  if ([...JOBS.values()].some((j) => j.polls < 6)) throw new ApiError("A quiz is already being prepared. Wait for it to finish.", 409);
  if (body.mode === "topic" && (!body.topic || body.topic.trim().length < 3)) throw new ApiError("A topic needs 3 to 80 characters.", 422);
  const id = `job${Math.random().toString(36).slice(2, 8)}`;
  const web = body.mode === "topic" && !/femoral|thigh|hip|knee|gluteal|hand|carpal/i.test(body.topic ?? "");
  JOBS.set(id, { polls: 0, body, offer: body.n === 10, fail: /zzz/.test(body.topic ?? "") || (web && Boolean(body.reviewed_only)), web });
  return { job_id: id };
}
export async function quizJob(id: string): Promise<QuizJob> {
  await sleep(350);
  studentSession();
  const j = JOBS.get(id);
  if (!j) throw new ApiError("That quiz job wasn't found.", 404);
  j.polls += 1;
  const req = j.body.n;
  const target = j.fail ? 0 : j.offer ? 6 : req;
  const have = Math.min(target, Math.round((j.polls / 4) * req));
  if (j.polls < 4) return { done: false, have, requested: req, note: j.polls < 2 ? "Reusing saved questions" : "Writing and checking new questions", result: null };
  if (j.fail) return { done: true, have: 0, requested: req, note: "", result: { status: "failed", reason: j.web && j.body.reviewed_only ? "no_approved" : "insufficient_evidence", quiz_id: null, have: 0, requested: req, message: j.web && j.body.reviewed_only ? "Only 0 instructor-approved question(s) match this choice. A quiz needs at least 5, and approved questions are never replaced by unreviewed ones. Questions built from the web are switched off while this is checked." : "There isn't enough material on that topic to write good questions. Try a broader topic." } };
  const qid = `q${Math.random().toString(36).slice(2, 10)}`;
  if (j.offer) {
    QUIZZES.set(qid, { id: qid, status: "offer", length: 5, picks: {}, current: 0, submitted: null, user: "student1", title: titleOf(j.body), web: j.web });
    lastOffer = qid;
    return { done: true, have: 6, requested: 10, note: "", result: { status: "offer", reason: "", quiz_id: qid, have: 6, requested: 10, message: "6 of 10 questions are ready. You can start with 5 or keep preparing." } };
  }
  QUIZZES.set(qid, { id: qid, status: "open", length: req, picks: {}, current: 0, submitted: null, user: "student1", title: titleOf(j.body), web: j.web });
  return { done: true, have: req, requested: req, note: "", result: { status: "ready", reason: "", quiz_id: qid, have: req, requested: req, message: "" } };
}
export async function quizLatest(): Promise<QuizLatest | null> {
  await delay();
  studentSession();
  const open = [...QUIZZES.values()].filter((q) => !q.submitted).pop();
  if (!open) return null;
  return { id: open.id, status: open.status, length: open.length, answered: Object.keys(open.picks).length };
}
function getRec(id: string): QuizRec {
  const q = QUIZZES.get(id);
  if (!q) throw new ApiError("That quiz wasn't found.", 404);
  return q;
}
export async function acceptQuiz(id: string): Promise<{ ok: true }> {
  await sleep(300);
  studentSession();
  const q = getRec(id);
  if (q.status !== "offer") throw new ApiError("That quiz isn't waiting for a decision.", 409);
  q.status = "open";
  return { ok: true };
}
export async function discardQuiz(id: string): Promise<{ ok: true }> {
  await sleep(300);
  studentSession();
  getRec(id);
  QUIZZES.delete(id);
  if (lastOffer === id) lastOffer = null;
  return { ok: true };
}
export async function getQuiz(id: string): Promise<OpenQuiz> {
  await delay();
  studentSession();
  const q = getRec(id);
  if (q.status !== "open" || q.submitted) throw new ApiError("That quiz isn't open.", 409);
  return {
    quiz_id: id, length: q.length, current: q.current, answered: Object.keys(q.picks).length,
    questions: bankOf(q).slice(0, q.length).map((b) => ({ stem: b.stem, lead_in: b.lead, selection_mode: "single" as const, options: b.options.map((t, i) => ({ id: "ABCD"[i], text: t })),
      web: q.web, source_note: q.web ? "Not from course notes" : null })),
    selections: clone(q.picks),
  };
}
export async function saveAnswer(id: string, index: number, optionIds: string[]): Promise<{ ok: true; answered: number }> {
  await sleep(200);
  studentSession();
  const q = getRec(id);
  q.picks[String(index)] = optionIds;
  return { ok: true, answered: Object.keys(q.picks).length };
}
export async function setCurrent(id: string, index: number): Promise<{ ok: true }> {
  await sleep(100);
  studentSession();
  getRec(id).current = index;
  return { ok: true };
}
function bankOf(q: QuizRec) {
  if (q.web) return WEB_BANK;
  // the student's quiz may include ONE instructor question, and only an approved practice one: draft, retired and exam-secure questions never leave the bank
  const served = QBANK.find((b) => bdata(b).status === "approved" && bdata(b).use === "practice" && bdata(b).options.length === 4);
  if (!served) return BANK;
  const d = bdata(served);
  return [...BANK.slice(0, 4), { stem: d.stem, lead: d.lead_in, options: d.options.map((o) => o.text), answer: d.options.findIndex((o) => o.id === d.answer), why: d.explanation, alts: d.options.map(() => ""), evidence: "", span: "" }];
}
function resultsFor(q: QuizRec): QuizResults {
  const questions: ResultQuestion[] = bankOf(q).slice(0, q.length).map((b, i) => {
    const selected = q.picks[String(i)] ?? [];
    const ansId = "ABCD"[b.answer];
    const alternatives: Record<string, string> = {};
    b.alts.forEach((t, k) => { if (t && k !== b.answer) alternatives["ABCD"[k]] = t; });
    return {
      n: i + 1, stem: b.stem, lead_in: b.lead, options: b.options.map((t, k) => ({ id: "ABCD"[k], text: t })), selected, answer_ids: [ansId],
      correct: selected.length === 1 && selected[0] === ansId, explanation: b.why, alternatives,
      evidence: [q.web
        ? { id: "e1", label: "Web: Waldeyer's tonsillar ring (Wikipedia)", tier: "Web (Wikipedia, not course notes)", url: "https://en.wikipedia.org/wiki/Waldeyer%27s_tonsillar_ring", visible: true, text: b.evidence, license: "CC BY-SA 4.0" }
        : { id: "e1", label: "Lecture 08 - Anterior and Medial Thigh › Femoral Triangle", tier: "Course material", url: null, visible: true, text: b.evidence, license: null }],
      label: "AI-checked (two models agreed and sources were checked). Not reviewed by Dr. Inglis.", review_status: "unreviewed",
      spans: [{ source_id: "e1", span: b.span }],
      web: q.web, source_note: q.web ? "Not from course notes" : null,
    };
  });
  return { quiz_id: q.id, score: questions.filter((x) => x.correct).length, length: q.length, submitted: q.submitted ?? new Date().toISOString(), questions };
}
export async function submitQuiz(id: string): Promise<QuizResults> {
  await delay();
  studentSession();
  const q = getRec(id);
  if (q.submitted) throw new ApiError("That quiz was already submitted.", 409);
  q.submitted = new Date().toISOString();
  return resultsFor(q);
}
export async function quizResults(id: string): Promise<QuizResults> {
  await delay();
  studentSession();
  const q = getRec(id);
  if (!q.submitted) throw new ApiError("Submit the quiz to see its results.", 409);
  return resultsFor(q);
}
export async function quizHistory(): Promise<QuizHistoryItem[]> {
  await sleep(350);
  studentSession();
  return [...QUIZZES.values()].filter((q) => q.submitted).sort((a, b) => (b.submitted ?? "").localeCompare(a.submitted ?? ""))
    .map((q) => ({ id: q.id, score: resultsFor(q).score, length: q.length, submitted: q.submitted!, title: q.title, web: q.web }));
}
export async function deleteQuizHistory(id: string): Promise<{ ok: true }> {
  await sleep(250);
  studentSession();
  const q = QUIZZES.get(id);
  if (!q || !q.submitted) throw new ApiError("That quiz was not found.", 404);
  QUIZZES.delete(id);
  return { ok: true };
}

// guide history (sidebar)
const GUIDE_HISTORY: GuideHistoryItem[] = [
  { id: "guide:class-17", kind: "guide", ref: "class-17", title: "Class 17 · The Hip and Knee Joints", station: 2, count: 4, updated_at: iso(0, 7), body_type: "more_fat", notice: null },
  { id: "guide:class-14", kind: "guide", ref: "class-14", title: "Class 14 · Gluteal Region", station: 0, count: 4, updated_at: iso(2, 15), body_type: null, notice: "This guide was updated. Your place was moved to the step that says the same thing." },
  { id: "lecture:L08", kind: "lecture", ref: "L08", title: "Lecture 08 · Anterior and Medial Thigh", station: 1, count: 3, updated_at: iso(9, 11), body_type: null, notice: null },
];
export async function guideHistory(): Promise<GuideHistoryItem[]> {
  await sleep(350);
  studentSession();
  if (readSession()?.preview) return [];
  return clone(GUIDE_HISTORY).sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}
export async function saveGuideHistory(kind: "guide" | "lecture", ref: string, station: number, bodyType?: GuideBodyType): Promise<{ ok: true }> {
  await sleep(100);
  studentSession();
  if (readSession()?.preview) return { ok: true };
  const id = `${kind}:${ref}`;
  const found = GUIDE_HISTORY.find((h) => h.id === id);
  const g = GUIDE_LIST.find((x) => x.id === ref);
  const l = LECTURES.find((x) => x.id === ref);
  const title = kind === "guide" ? `Class ${g?.class_number} · ${g?.title}` : (l?.title ?? ref).replace(/\s+-\s+/, " · ");
  const count = kind === "guide" ? (STATIONS[ref]?.length ?? 1) : LECTURE_STATIONS.length;
  if (found) { found.station = Math.max(found.station, station); found.updated_at = new Date().toISOString(); if (bodyType) found.body_type = bodyType; }
  else GUIDE_HISTORY.push({ id, kind, ref, title, station, count, updated_at: new Date().toISOString(), body_type: bodyType ?? null, notice: null });
  return { ok: true };
}
export async function deleteGuideHistory(id: string): Promise<{ ok: true }> {
  await sleep(250);
  studentSession();
  const i = GUIDE_HISTORY.findIndex((h) => h.id === id);
  if (i < 0) throw new ApiError("That item was not found.", 404);
  GUIDE_HISTORY.splice(i, 1);
  return { ok: true };
}
export function _lastOffer() { return lastOffer; }

// ---------------------------------------------------------------- instructor
const REVIEW: ReviewItem[] = [
  { id: "r1", type: "start_here", status: "open", lecture: "Lecture 16 - Posterior Thigh and Popliteal Fossa", section: "Popliteal Fossa › Contents › Popliteal Artery", original_text: "Continuation of femoral nerve past the adductor hiatus", ai_note: "This should say femoral artery, not nerve. The artery becomes the popliteal artery after the adductor hiatus.", sources: [{ ...S_NOTES, n: 1, subtitle: "Lecture 16, Posterior Thigh and Popliteal Fossa › Popliteal Artery", snippet: "Popliteal artery: continuation of femoral nerve past the adductor hiatus." }, S_OPENSTAX].map((s, i) => ({ ...s, n: i + 1 })) },
  { id: "r2", type: "confirmed_factual", status: "open", lecture: "Lecture 09 - The Hand", section: "Nerves of the Hand › Ulnar Nerve", original_text: "The ulnar nerve supplies the thenar muscles.", ai_note: "The thenar muscles are mostly supplied by the median nerve (recurrent branch).", sources: [{ ...S_OPENSTAX, n: 1 }] },
  { id: "r3", type: "doubtful", status: "open", lecture: "Lecture 22 - The Heart", section: "Surfaces › Apex", original_text: "The apex lies in the fourth intercostal space.", ai_note: "Most references place the apex in the fifth intercostal space.", sources: [{ ...S_NOTES, n: 1, subtitle: "Lecture 22, The Heart › Surfaces", snippet: "The apex of the heart lies in the fourth intercostal space." }] },
  { id: "r4", type: "wording", status: "open", lecture: "Lecture 08 - Anterior and Medial Thigh", section: "Femoral Triangle", original_text: "Floor made of: iliopsoas, pectenius, adductor longus.", ai_note: "Wording only. 'pectenius' should be 'pectineus'.", sources: [] },
  { id: "r5", type: "typo", status: "open", lecture: "Lecture 10 - Gluteal Region", section: "Muscles", original_text: "Gluteus medius abducts the thigh and tilts the pelvis.", ai_note: "Possible typo: 'tilts' may be 'stabilises'.", sources: [] },
  { id: "r6", type: "student_report", status: "open", lecture: "Lecture 08 - Anterior and Medial Thigh", section: "Femoral Triangle", original_text: "The femoral triangle is a region in the upper anterior thigh. Boundaries: inguinal ligament, sartorius, adductor longus [1]", ai_note: "student1: A citation points to the wrong place. The [1] marker next to the roof points to the floor sentence.", sources: [] },
  { id: "r7", type: "wording", status: "verified", lecture: "Lecture 11 - Posterior Thigh and Popliteal Fossa", section: "Hamstrings", original_text: "Hamstrings extend the hip and flex the knee joint.", ai_note: "Wording only.", sources: [] },
  { id: "r9", type: "confirmed_factual", status: "changed", lecture: "Lecture 08 - Anterior and Medial Thigh", section: "Femoral Triangle › Boundaries", original_text: "Superior – inguinal canal", ai_note: "Changed in the revised notes: the quoted line is no longer there.\nNew wording: Superior: inguinal ligament.\nThe boundary is the inguinal ligament, not the canal.", sources: [{ ...S_NOTES, n: 1, title: "Lecture notes (revised)", snippet: "Superior: inguinal ligament." }] },
  { id: "r8", type: "doubtful", status: "dismissed", lecture: "Lecture 09 - The Hand", section: "Carpal Tunnel", original_text: "Nine tendons pass through the carpal tunnel.", ai_note: "Correct: four FDS, four FDP and FPL.", sources: [] },
];
export async function adminStats(): Promise<AdminStats> {
  await delay();
  instructorSession();
  return { questions_7d: 84, flagged_open: 5, web_answers_7d: 11, review_counts: { confirmed_factual: 90, doubtful: 32, wording: 442, typo: 169, start_here: 14 }, bank_counts: bankCountsNow() };
}
export async function adminReview(q: { type?: string; status?: string; lecture?: string; page?: number }): Promise<ReviewPage> {
  await delay();
  instructorSession();
  let items = REVIEW.filter((r) => (!q.type || r.type === q.type) && (!q.lecture || r.lecture.toLowerCase().includes(q.lecture.toLowerCase())));
  if (q.status === "decided") items = items.filter((r) => r.status !== "open");
  else if (q.status) items = items.filter((r) => r.status === q.status);
  return { items: clone(items), total: items.length };
}
export async function adminDecide(id: string, action: "verify" | "dismiss", fixText?: string): Promise<{ ok: true }> {
  await delay();
  instructorSession();
  const r = REVIEW.find((x) => x.id === id);
  if (!r) throw new ApiError("That item wasn't found.", 404);
  if (r.status !== "open") throw new ApiError("That item was already decided.", 409);
  if (action === "verify") {
    if (r.type === "student_report") throw new ApiError("A student report can only be dismissed.", 422);
    if (!fixText?.trim()) throw new ApiError("Write the corrected text before verifying.", 422);
    r.status = "verified";
  } else r.status = "dismissed";
  return { ok: true };
}
const QROWS: QuestionRow[] = (() => {
  const qs: [string, string, Omit<Message, "id" | "created_at">, boolean][] = [
    ["student1", "What are the boundaries of the femoral triangle?", FEMORAL, false],
    ["student2", "apex", APEX, false],
    ["student1", "What is Waldeyer's ring?", WALDEYER, false],
    ["student2", "amoxicillin dose for a child", REFUSED, false],
    ["student1", "Where does the sciatic nerve leave the pelvis?", NOTES_GATED, true],
    ["student2", "What forms the floor of the femoral triangle?", FEMORAL, false],
    ["student1", "Explain this more simply: the femoral triangle", SIMPLE, false],
    ["student2", "What is the tarsal tunnel?", NOT_COVERED, false],
    ["student1", "What is Waldeyer's ring made of?", WALDEYER, true],
    ["student2", "Which muscle forms the lateral border of the femoral triangle?", FEMORAL, false],
  ];
  return qs.map(([student, question, tpl, flagged], i) => ({
    id: `qr${i + 1}`, student, question, kind: tpl.kind, web: tpl.sources.some((s) => s.type === "wikipedia" || s.type === "web"), flagged,
    created_at: iso(Math.floor(i / 3), 9 + i), message: { ...clone(tpl), id: `qc${i}:1`, created_at: iso(Math.floor(i / 3), 9 + i) },
  }));
})();
export async function adminQuestions(q: { web?: boolean; flagged?: boolean; page?: number }): Promise<QuestionPage> {
  await delay();
  instructorSession();
  const items = QROWS.filter((r) => (!q.web || r.web) && (!q.flagged || r.flagged));
  return { items: clone(items), total: items.length };
}
const STUDENTS: Student[] = [
  { id: "student1", name: "Student One", username: "student1", lecture_ids: ["L08", "L09", "L10", "L11"], guide_ids: ["class-17", "class-14", "class-10", "class-05"] },
  { id: "student2", name: "Student Two", username: "student2", lecture_ids: ["L08"], guide_ids: ["class-17"] },
];
export async function adminWebQuizzes(): Promise<WebQuizPage> {
  await delay();
  instructorSession();
  return { items: [{ id: "qpast3", student: "student1", title: "Waldeyer's ring", status: "submitted", score: 3, length: 5, web_questions: 5, created_at: iso(1, 12),
    sources: [{ title: "Web: Waldeyer's tonsillar ring (Wikipedia)", url: "https://en.wikipedia.org/wiki/Waldeyer%27s_tonsillar_ring", license: "CC BY-SA 4.0" }] }], total: 1 };
}
export async function adminStudents(): Promise<Student[]> {
  await delay();
  instructorSession();
  return clone(STUDENTS);
}
export async function adminSetAccess(id: string, lectureIds: string[], guideIds: string[]): Promise<{ ok: true }> {
  await delay();
  instructorSession();
  const s = STUDENTS.find((x) => x.id === id);
  if (!s) throw new ApiError("That student wasn't found.", 404);
  s.lecture_ids = lectureIds;
  s.guide_ids = guideIds;
  return { ok: true };
}
export async function adminPreview(profile: string): Promise<{ ok: true }> {
  await delay();
  const s = instructorSession();
  const stu = STUDENTS.find((x) => x.id === profile);
  if (profile !== "full" && !stu) throw new ApiError("That student wasn't found.", 404);
  previewChats = [];
  writeSession({ ...s, preview: { profile, name: profile === "full" ? "Full access" : stu!.name } });
  return { ok: true };
}
export async function adminPreviewExit(): Promise<{ ok: true }> {
  await sleep(250);
  const s = instructorSession();
  previewChats = [];
  writeSession({ ...s, preview: null });
  return { ok: true };
}

// ---------------------------------------------------------------- Notes manager (instructor only)
import type { NoteAudit, NoteChange, NoteDetail, NoteDiff, NoteFilters, NoteList, NoteRow, NoteVersion } from "./types";
const NSTEPS = ["Reading the file and keeping its headings", "Matching region and lecture by content", "Checking overlap with existing documents", "Fact-checking new or changed sections", "Preparing the preview"];
interface MDoc { row: NoteRow; sections: { path: string[]; text: string }[]; versions: { version: number; status: string; created_at: string; note: string; text?: string }[]; audit: NoteAudit[]; started?: number; pending?: boolean; archived_at?: string; replaces?: string }
const SEC = (t: string) => [{ path: ["Overview", "Borders"], text: `${t}: borders and contents are listed here.` }, { path: ["Overview", "Nerves"], text: "The nerve runs deep to the muscle and supplies the skin of the region." }];
const NDOCS: MDoc[] = [
  { row: { id: "L08", kind: "note", title: "Lecture 08 - The Femoral Triangle", region: "Lower limb", version: 2, status: "published", updated_at: iso(6), access_count: 2, note: "", earlier_version: false }, sections: SEC("Femoral triangle"),
    versions: [{ version: 2, status: "live", created_at: iso(6), note: "the revised notes" }], audit: [{ at: iso(6), user: "system", action: "adopted", detail: "live version 2 entered the manager" }] },
  { row: { id: "L09", kind: "note", title: "Lecture 09 - The Hand", region: "Upper limb", version: 2, status: "published", updated_at: iso(6), access_count: 2, note: "", earlier_version: false }, sections: SEC("Hand"),
    versions: [{ version: 2, status: "live", created_at: iso(6), note: "the revised notes" }], audit: [] },
  { row: { id: "L17", kind: "note", title: "Lecture 17 - The Gluteal Region", region: "Lower limb", version: 1, status: "published", updated_at: iso(30), access_count: 1, note: "Earlier version, not in revised notes", earlier_version: true }, sections: SEC("Gluteal region"),
    versions: [{ version: 1, status: "live", created_at: iso(30), note: "" }], audit: [] },
  { row: { id: "G-class-17", kind: "guide", title: "Class 17: The Hip and Knee Joints", region: "Lower limb", version: 2, status: "published", updated_at: iso(6), access_count: 2, note: "", earlier_version: false }, sections: [{ path: ["Slide 2"], text: "Open the posterior wall of the joint capsule." }],
    versions: [{ version: 2, status: "live", created_at: iso(6), note: "" }], audit: [] },
  { row: { id: "v1:L08", kind: "note", title: "Lecture 08 - Femoral Triangle (first version)", region: "Lower limb", version: 1, status: "archived", updated_at: iso(14), access_count: 0, note: "First version, replaced by the revised notes", earlier_version: false }, sections: [],
    versions: [], audit: [] },
];
const ndoc = (id: string) => { const d = NDOCS.find((x) => x.row.id === id); if (!d) throw new ApiError("That document was not found.", 404); return d; };
const nlog = (d: MDoc, action: string, detail = "") => d.audit.unshift({ at: new Date().toISOString(), user: "inglis", action, detail });
export async function notesList(f: NoteFilters): Promise<NoteList> {
  await delay(); instructorSession();
  const items = NDOCS.map((d) => d.row).filter((r) => (!f.kind || r.kind === f.kind) && (!f.region || r.region === f.region) && (!f.status || r.status === f.status) && (!f.q || (r.title + r.region).toLowerCase().includes(f.q.toLowerCase())));
  return clone({ items, regions: [...new Set(NDOCS.map((d) => d.row.region))].sort(), total: items.length });
}
export async function notesUpload(name: string, size: number, kind?: string, replaces?: string): Promise<{ doc_id: string; version: number }> {
  await delay(); instructorSession();
  const ext = name.slice(name.lastIndexOf(".")).toLowerCase();
  if (![".docx", ".doc", ".pptx", ".pdf"].includes(ext)) throw new ApiError("Upload a .docx, .doc, .pptx or .pdf file.", 422);
  if (size > 15 << 20 && ext !== ".pptx") throw new ApiError(`That file is ${(size / 1048576).toFixed(1)} MB. The limit for ${ext} is 15 MB.`, 413);
  const title = name.replace(/\.[^.]+$/, "").replace(/[_-]+Notes.*$/i, "").trim();
  const id = `N-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${Math.random().toString(16).slice(2, 6)}`;
  const isGuide = (kind || (ext === ".pptx" ? "guide" : "note")) === "guide";
  const d: MDoc = { row: { id, kind: isGuide ? "guide" : "note", title, region: "Other", version: 1, status: "processing", updated_at: new Date().toISOString(), access_count: 0, note: "", earlier_version: false }, sections: SEC(title),
    versions: [{ version: 1, status: "processing", created_at: new Date().toISOString(), note: "" }], audit: [], started: Date.now(), replaces };
  nlog(d, "uploaded", `${name}, version 1`);
  NDOCS.unshift(d);
  return { doc_id: id, version: 1 };
}
function jobOf(d: MDoc) {
  const i = d.started ? Math.min(NSTEPS.length, Math.floor((Date.now() - d.started) / 1100)) : NSTEPS.length;
  if (d.started && i >= NSTEPS.length) { d.started = undefined; if (d.row.status === "processing") { d.row.status = "ready"; d.row.region = "Lower limb"; } d.versions[0].status = d.row.status === "published" ? "live" : "ready"; }
  const done = !d.started;
  return { status: done ? "ready" : "processing", step: done ? "Ready for preview" : NSTEPS[i], step_index: done ? NSTEPS.length : i, steps: NSTEPS, error: "", version: d.versions[0].version };
}
export async function notesDetail(id: string): Promise<NoteDetail> {
  await sleep(250); instructorSession();
  const d = ndoc(id);
  if (id.startsWith("v1:")) throw new ApiError("This is the archived first version. It is kept for reference and cannot be opened here.", 404);
  const job = d.row.status === "published" && !d.pending ? { status: "live", step: "", step_index: NSTEPS.length, steps: NSTEPS, error: "", version: d.row.version } : jobOf(d);
  const ready = job.status !== "processing";
  const replaced = d.replaces ? NDOCS.find((x) => x.row.id === d.replaces) : undefined;
  return clone({ id, kind: d.row.kind, title: d.row.title, region: d.row.region, status: d.row.status, version: d.row.version, live_version: d.row.status === "published" ? d.row.version : null, shown_version: d.row.version,
    created_at: d.versions[d.versions.length - 1].created_at, updated_at: d.row.updated_at, replaces: d.replaces ?? null, replaces_title: replaced?.row.title ?? null,
    overlap: d.row.status === "ready" && !d.replaces ? { doc_id: "L08", title: "Lecture 08 - The Femoral Triangle", score: 0.71, shared_sections: 1, sections: 2, suggest_replace: true } : null,
    source_name: "", job, sections: ready ? d.sections : [], mapping: { region: d.row.region, lecture: d.row.kind === "guide" ? "Lecture 13 - The Hip Joint" : "", title: d.row.title },
    flags: ready && d.row.status !== "published" ? { count: 2, items: [{ quote: "Continuation of femoral nerve past the adductor hiatus", issue: "The popliteal artery continues the femoral artery, not the nerve.", severity: "high", tier: "likely_factual", section: "Overview › Nerves" },
      { quote: "supplies the skin of the region", issue: "Wording is vague.", severity: "low", tier: "wording", section: "Overview › Nerves" }] } : { count: 0, items: [] },
    diff: replaced && ready ? { against: replaced.row.title, counts: { unchanged: 1, edited: 1, rewritten: 0, added: 0, removed: 0 }, rows: [{ status: "edited", path: "Overview › Nerves", old: "The nerve runs deep to the muscle.", new: d.sections[1].text }] } : null,
    archived_at: d.archived_at ?? null, purge_after: d.archived_at ? new Date(Date.parse(d.archived_at) + 30 * 864e5).toISOString() : null, grants_mode: "none", has_pending: false,
    editable: d.row.kind === "note" && d.row.status === "published", guide_id: d.row.kind === "guide" && d.row.status === "published" && id === "G-class-17" ? "class-17" : null, regions: [...new Set(NDOCS.map((x) => x.row.region))].sort(), lectures: NDOCS.filter((x) => x.row.kind === "note" && !x.row.id.startsWith("v1:")).map((x) => x.row.title) });
}
export async function notesMapping(id: string, body: { region?: string; replaces?: string; lecture?: string }): Promise<{ ok: true }> {
  await delay(); instructorSession(); const d = ndoc(id);
  if (body.region !== undefined) { d.row.region = body.region; nlog(d, "changed the region", body.region); }
  if (body.replaces !== undefined) { d.replaces = body.replaces || undefined; nlog(d, "replaces", body.replaces); }
  return { ok: true };
}
export async function notesReplace(id: string, name: string): Promise<{ doc_id: string; version: number }> {
  await delay(); instructorSession(); const d = ndoc(id);
  if (d.pending) throw new ApiError("This document already has a new version waiting. Publish or discard it first.", 409);
  d.pending = true; d.started = Date.now(); const v = d.row.version + 1; d.versions.unshift({ version: v, status: "processing", created_at: new Date().toISOString(), note: "" }); nlog(d, "replaced the file", `${name}, version ${v}`);
  d.row.note = "New version being prepared";
  return { doc_id: id, version: v };
}
export async function notesPublish(id: string, access: string, students: string[]): Promise<NoteChange> {
  await sleep(1400); instructorSession(); const d = ndoc(id);
  if (d.row.status !== "ready" && !d.pending) throw new ApiError("There is no prepared version to publish.", 409);
  d.row.status = "published"; d.pending = false; d.row.version = d.versions[0].version; d.versions.forEach((v, i) => { if (i) v.status = "superseded"; }); d.versions[0].status = "live";
  d.row.access_count = access === "all" ? 2 : access === "selected" ? students.length : 0; d.row.note = ""; d.row.updated_at = new Date().toISOString(); nlog(d, "published", `version ${d.row.version}`);
  return { doc_id: id, version: d.row.version, granted: d.row.access_count, flags_added: 2, fixes_to_recheck: 0, progress_moved: 0, restorable_until: null };
}
export async function notesDiscard(id: string): Promise<{ ok: true }> {
  await delay(); instructorSession(); const d = ndoc(id);
  if (d.row.status === "published" && d.pending) { d.versions.shift(); d.pending = false; d.row.note = ""; } else NDOCS.splice(NDOCS.indexOf(d), 1);
  return { ok: true };
}
export async function notesEdit(id: string, edits: { index: number; text: string }[], note: string): Promise<NoteChange> {
  await sleep(1200); instructorSession(); const d = ndoc(id);
  edits.forEach((e) => { d.sections[e.index].text = e.text; });
  d.row.version += 1; d.versions.forEach((v) => { v.status = "superseded"; }); d.versions.unshift({ version: d.row.version, status: "live", created_at: new Date().toISOString(), note: note || "edited in the browser", text: JSON.stringify(d.sections) });
  d.row.updated_at = new Date().toISOString(); nlog(d, "edited", `version ${d.row.version}`);
  return { doc_id: id, version: d.row.version, granted: 0, flags_added: 0, fixes_to_recheck: 1, progress_moved: 0, restorable_until: null };
}
export async function notesVersions(id: string): Promise<NoteVersion[]> {
  await delay(); instructorSession(); const d = ndoc(id);
  return d.versions.map((v, i) => ({ version: v.version, status: v.status, created_at: v.created_at, created_by: "inglis", note: v.note, n_sections: d.sections.length, source_name: "", diff: i < d.versions.length - 1 ? { unchanged: 1, edited: 1, rewritten: 0, added: 0, removed: 0 } : null }));
}
export async function notesVersionDiff(id: string, version: number): Promise<NoteDiff> {
  await delay(); instructorSession(); ndoc(id);
  return { against: `version ${version - 1}`, counts: { unchanged: 1, edited: 1, rewritten: 0, added: 0, removed: 0 }, rows: [{ status: "edited", path: "Overview › Nerves", old: "The nerve runs deep to the muscle.", new: "The nerve runs deep to the muscle and supplies the skin of the region." }] };
}
export async function notesRollback(id: string, version: number): Promise<NoteChange> {
  await sleep(1200); instructorSession(); const d = ndoc(id);
  d.row.version += 1; d.versions.forEach((v) => { v.status = "superseded"; }); d.versions.unshift({ version: d.row.version, status: "live", created_at: new Date().toISOString(), note: `rolled back to version ${version}` });
  nlog(d, "rolled back", `to version ${version}`);
  return { doc_id: id, version: d.row.version, granted: 0, flags_added: 0, fixes_to_recheck: 0, progress_moved: 0, restorable_until: null };
}
export async function notesArchive(id: string): Promise<NoteChange> {
  await sleep(1000); instructorSession(); const d = ndoc(id);
  d.row.status = "archived"; d.archived_at = new Date().toISOString(); d.row.access_count = 0; nlog(d, "archived");
  return { doc_id: id, version: null, granted: 0, flags_added: 0, fixes_to_recheck: 0, progress_moved: 0, restorable_until: new Date(Date.now() + 30 * 864e5).toISOString() };
}
export async function notesRestore(id: string): Promise<NoteChange> {
  await sleep(1000); instructorSession(); const d = ndoc(id);
  d.row.status = "published"; d.archived_at = undefined; nlog(d, "restored");
  return { doc_id: id, version: d.row.version, granted: 0, flags_added: 0, fixes_to_recheck: 0, progress_moved: 0, restorable_until: null };
}
export async function notesPurge(id: string, confirmTitle: string): Promise<{ ok: true }> {
  await delay(); instructorSession(); const d = ndoc(id);
  if (confirmTitle.trim() !== d.row.title) throw new ApiError("Type the document's title exactly to confirm.", 422);
  NDOCS.splice(NDOCS.indexOf(d), 1);
  return { ok: true };
}
export async function notesAudit(id: string): Promise<NoteAudit[]> {
  await delay(); instructorSession(); return clone(ndoc(id).audit);
}

// ---------------------------------------------------------------- Question bank (instructor only). 15 FAKE sample questions: mock data never goes into the real bank.
import type { BankComment, BankData, BankDetail, BankFilters, BankFlag, BankImportPreview, BankImportResult, BankList, BankRow } from "./types";
interface MBank { id: string; created: string; updated: string; versions: { version: number; at: string; by: string; note: string; data: BankData }[]; comments: BankComment[]; flags: BankFlag[]; recheck: string; sample: boolean; used: number }
const SAMPLE: [string, string, string, string[]][] = [
  ["Lower limb", "Lecture 08 - Anterior and Medial Thigh", "Which muscle forms the lateral border of the femoral triangle?", ["Sartorius", "Gracilis", "Pectineus", "Adductor magnus"]],
  ["Lower limb", "Lecture 08 - Anterior and Medial Thigh", "Which nerve supplies the quadriceps femoris?", ["Femoral nerve", "Obturator nerve", "Tibial nerve", "Sciatic nerve"]],
  ["Lower limb", "Lecture 08 - Anterior and Medial Thigh", "Where does the great saphenous vein drain?", ["Femoral vein", "Popliteal vein", "External iliac artery", "Profunda femoris vein"]],
  ["Lower limb", "Lecture 08 - Anterior and Medial Thigh", "Which artery is the main blood supply of the thigh?", ["Femoral artery", "Obturator artery", "Popliteal artery", "Gluteal artery"]],
  ["Lower limb", "Lecture 08 - Anterior and Medial Thigh", "Which structure lies medial to the femoral vein?", ["Femoral canal", "Femoral nerve", "Sartorius", "Iliopsoas"]],
  ["Upper limb", "Lecture 09 - The Hand", "Which nerve passes through the carpal tunnel?", ["Median nerve", "Ulnar nerve", "Radial nerve", "Axillary nerve"]],
  ["Upper limb", "Lecture 09 - The Hand", "Which muscle abducts the thumb?", ["Abductor pollicis brevis", "Adductor pollicis", "Opponens digiti minimi", "Palmaris brevis"]],
  ["Upper limb", "Lecture 09 - The Hand", "Which nerve supplies the hypothenar muscles?", ["Ulnar nerve", "Median nerve", "Radial nerve", "Musculocutaneous nerve"]],
  ["Upper limb", "Lecture 09 - The Hand", "What do the lumbricals flex?", ["Metacarpophalangeal joints", "Wrist", "Distal interphalangeal joints", "Elbow"]],
  ["Upper limb", "Lecture 09 - The Hand", "Which arch lies more distally in the palm?", ["Superficial palmar arch", "Deep palmar arch", "Dorsal carpal arch", "Radial recurrent arch"]],
  ["Head and neck", "Lecture 20 - The Neck", "What forms the anterior border of the posterior triangle of the neck?", ["Sternocleidomastoid", "Trapezius", "Omohyoid", "Digastric"]],
  ["Head and neck", "Lecture 20 - The Neck", "Which nerve supplies the trapezius?", ["Accessory nerve", "Vagus nerve", "Phrenic nerve", "Hypoglossal nerve"]],
  ["Head and neck", "Lecture 20 - The Neck", "Which gland lies anterior to the trachea?", ["Thyroid gland", "Parotid gland", "Submandibular gland", "Thymus"]],
  ["Head and neck", "Lecture 20 - The Neck", "Which vessel runs in the carotid sheath with the vagus nerve?", ["Internal jugular vein", "External jugular vein", "Facial vein", "Subclavian vein"]],
  ["Head and neck", "Lecture 20 - The Neck", "Which muscle elevates the hyoid bone?", ["Mylohyoid", "Sternohyoid", "Omohyoid", "Thyrohyoid"]],
];
const QBANK: MBank[] = SAMPLE.map(([region, lecture, lead, opts], i) => {
  const data: BankData = { stem: "", lead_in: lead, options: opts.map((t, j) => ({ id: "ABCD"[j], text: t })), answer: "A", explanation: "SAMPLE explanation: not real course content.", lecture, guide: "", section: "", region, tags: ["sample"],
    difficulty: (["easy", "medium", "hard"] as const)[i % 3], source: i % 5 === 3 ? "ai" : "instructor", status: i % 5 < 3 ? "approved" : "draft", use: i % 5 === 4 ? "exam_secure" : "practice", objective: "" };
  const flags: BankFlag[] = i === 2 ? [{ kind: "nbme", code: "longest_key", severity: "warn", message: "The correct option is the longest and most detailed: a testwise cue.", dismissed: false }]
    : i === 6 ? [{ kind: "key", code: "key_mismatch", severity: "warn", message: "Answering from the notes, the AI chose B, but the key is A. The notes say the adductor pollicis adducts the thumb.", dismissed: false }] : [];
  return { id: `q-sample${String(i + 1).padStart(2, "0")}`, created: iso(20 - i), updated: iso(10 - (i % 7)), versions: [{ version: 1, at: iso(20 - i), by: "sample", note: "sample question (fake)", data }], comments: [], flags, recheck: i === 9 ? "Notes changed: the section it cites was changed (Lecture 09 > Arteries of the Hand)" : "", sample: true, used: i % 5 < 3 ? 12 + i : 0 };
});
const bdoc = (id: string) => { const b = QBANK.find((x) => x.id === id); if (!b) throw new ApiError("That question was not found.", 404); return b; };
const bdata = (b: MBank) => b.versions[0].data;
function brow(b: MBank): BankRow {
  const d = bdata(b), open = b.flags.filter((f) => !f.dismissed);
  return { id: b.id, lead_in: d.lead_in, stem: d.stem, status: d.status, use: d.use, source: d.source, lecture: d.lecture || d.guide, region: d.region, tags: d.tags, difficulty: d.difficulty, version: b.versions[0].version, updated_at: b.updated, flagged: open.length > 0 || !!b.recheck, n_flags: open.length, needs_recheck: !!b.recheck, sample: b.sample, used: b.used };
}
function bcounts() {
  const rows = QBANK.map(brow);
  return { total: rows.length, draft: rows.filter((r) => r.status === "draft").length, approved: rows.filter((r) => r.status === "approved").length, retired: rows.filter((r) => r.status === "retired").length, exam_secure: rows.filter((r) => r.use === "exam_secure").length, flagged: rows.filter((r) => r.n_flags > 0).length, needs_recheck: rows.filter((r) => r.needs_recheck).length };
}
export function bankCountsNow() { return bcounts(); }
export async function bankList(f: BankFilters): Promise<BankList> {
  await delay(); instructorSession();
  const words = (f.q ?? "").toLowerCase().split(/\s+/).filter(Boolean);
  const rows = QBANK.filter((b) => {
    const d = bdata(b), r = brow(b);
    return (!f.status || d.status === f.status) && (!f.use || d.use === f.use) && (!f.source || d.source === f.source) && (!f.region || d.region === f.region) && (!f.lecture || r.lecture === f.lecture)
      && (!f.tag || d.tags.includes(f.tag)) && (!f.difficulty || d.difficulty === f.difficulty) && (!f.flagged || r.flagged) && words.every((w) => (d.lead_in + " " + d.options.map((o) => o.text).join(" ") + " " + d.tags.join(" ")).toLowerCase().includes(w));
  }).map(brow);
  return clone({ items: rows, total: rows.length, counts: bcounts(), lectures: [...new Set(QBANK.map((b) => brow(b).lecture).filter(Boolean))].sort(), regions: [...new Set(QBANK.map((b) => bdata(b).region).filter(Boolean))].sort(), tags: [...new Set(QBANK.flatMap((b) => bdata(b).tags))].sort() });
}
function bdetail(b: MBank): BankDetail {
  const vs = b.versions;
  const stats = b.used ? { n: b.used, p_correct: 0.62, discrimination: 0.31, enough: true, distractors: bdata(b).options.map((o, j) => ({ text: o.text, picks: j === 0 ? Math.round(b.used * 0.62) : Math.round(b.used * 0.12), correct: j === 0 })), min_for_stats: 10, min_for_flags: 20 }
    : { n: 0, p_correct: null, discrimination: null, enough: false, distractors: [], min_for_stats: 10, min_for_flags: 20 };
  return clone({ id: b.id, version: vs[0].version, created_at: b.created, updated_at: b.updated, data: bdata(b), sample: b.sample, flags: b.flags, needs_recheck: b.recheck, stats, comments: b.comments,
    versions: vs.map((v, i) => ({ version: v.version, at: v.at, by: v.by, note: v.note, changed: i + 1 < vs.length ? (Object.keys(v.data) as (keyof BankData)[]).filter((k) => JSON.stringify(v.data[k]) !== JSON.stringify(vs[i + 1].data[k])) : ["created"] })) });
}
export async function bankGet(id: string): Promise<BankDetail> { await sleep(250); instructorSession(); return bdetail(bdoc(id)); }
function bcheck(d: BankData): BankFlag[] {
  const out: BankFlag[] = [];
  if (/\b(except|not)\b/i.test(d.lead_in)) out.push({ kind: "nbme", code: "negative", severity: "warn", message: "Negative lead-in (EXCEPT / NOT / least likely): it tests recognising wrong statements, which the NBME advises against.", dismissed: false });
  if (d.options.some((o) => /all of the above|none of the above/i.test(o.text))) out.push({ kind: "nbme", code: "all_none", severity: "warn", message: "An option says all / none of the above (or combines options): remove it.", dismissed: false });
  if (d.options.some((o) => /\b(always|never|only)\b/i.test(o.text))) out.push({ kind: "nbme", code: "absolutes", severity: "warn", message: "Absolute words in an option: students use them as cues.", dismissed: false });
  return out;
}
function bvalidate(d: BankData) {
  if (!d.lead_in.trim()) throw new ApiError("The lead-in (the actual question) is required.", 422);
  const opts = d.options.filter((o) => o.text.trim());
  if (opts.length < 2) throw new ApiError("A question needs 2 to 5 options.", 422);
  if (!opts.some((o) => o.id === d.answer)) throw new ApiError(`The answer must be one of ${opts.map((o) => o.id).join(", ")}.`, 422);
}
export async function bankCreate(d: BankData): Promise<BankDetail> {
  await delay(); instructorSession(); bvalidate(d);
  const b: MBank = { id: `q-${Math.random().toString(16).slice(2, 12)}`, created: new Date().toISOString(), updated: new Date().toISOString(), versions: [{ version: 1, at: new Date().toISOString(), by: "inglis", note: "created", data: clone(d) }], comments: [], flags: bcheck(d), recheck: "", sample: false, used: 0 };
  QBANK.unshift(b);
  return bdetail(b);
}
export async function bankSave(id: string, d: BankData & { note?: string }): Promise<BankDetail> {
  await delay(); instructorSession(); bvalidate(d); const b = bdoc(id);
  const { note, ...data } = d;
  if (JSON.stringify(data) !== JSON.stringify(bdata(b))) { b.versions.unshift({ version: b.versions[0].version + 1, at: new Date().toISOString(), by: "inglis", note: note || "edited", data: clone(data) }); b.updated = new Date().toISOString(); b.flags = bcheck(data); }
  return bdetail(b);
}
export async function bankBulk(ids: string[], action: string, value: string): Promise<{ changed: number }> {
  await delay(); instructorSession();
  let n = 0;
  for (const id of ids) {
    const b = bdoc(id), d = clone(bdata(b));
    if (action === "approve") d.status = "approved"; else if (action === "retire") d.status = "retired"; else if (action === "draft") d.status = "draft";
    else if (action === "set_use") d.use = value as BankData["use"]; else if (action === "add_tag") { if (!d.tags.includes(value)) d.tags.push(value); } else if (action === "remove_tag") d.tags = d.tags.filter((t) => t !== value);
    else if (action === "run_checks") { b.flags = bcheck(d); n++; continue; }
    if (JSON.stringify(d) !== JSON.stringify(bdata(b))) { b.versions.unshift({ version: b.versions[0].version + 1, at: new Date().toISOString(), by: "inglis", note: `bulk: ${action}${value ? " " + value : ""}`, data: d }); b.updated = new Date().toISOString(); n++; }
  }
  return { changed: n };
}
export async function bankRestore(id: string, version: number): Promise<BankDetail> {
  await delay(); instructorSession(); const b = bdoc(id); const old = b.versions.find((v) => v.version === version);
  if (!old) throw new ApiError("That version was not found.", 404);
  b.versions.unshift({ version: b.versions[0].version + 1, at: new Date().toISOString(), by: "inglis", note: `restored version ${version}`, data: clone(old.data) }); b.updated = new Date().toISOString();
  return bdetail(b);
}
export async function bankComment(id: string, text: string): Promise<BankDetail> {
  await delay(); instructorSession(); const b = bdoc(id);
  if (!text.trim()) throw new ApiError("Write a comment first.", 422);
  b.comments.push({ id: b.comments.length + 1, at: new Date().toISOString(), by: "inglis", text }); return bdetail(b);
}
export async function bankCheck(id: string): Promise<BankDetail> {
  await sleep(1500); instructorSession(); const b = bdoc(id);
  b.flags = [...bcheck(bdata(b)), ...b.flags.filter((f) => f.kind === "key")]; return bdetail(b);
}
export async function bankDismiss(id: string, kind: string, code: string, dismissed: boolean): Promise<BankDetail> {
  await delay(); instructorSession(); const b = bdoc(id); b.flags.forEach((f) => { if (f.kind === kind && f.code === code) f.dismissed = dismissed; }); return bdetail(b);
}
export async function bankRecheck(id: string): Promise<BankDetail> { await delay(); instructorSession(); const b = bdoc(id); b.recheck = ""; return bdetail(b); }
const IMPORTS: Record<string, { headers: string[]; rows: string[][]; filename: string }> = {};
const FIELDS = [["lead_in", "Question (lead-in)"], ["stem", "Stem / vignette"], ["option_a", "Option A"], ["option_b", "Option B"], ["option_c", "Option C"], ["option_d", "Option D"], ["option_e", "Option E"], ["answer", "Correct answer"], ["explanation", "Explanation"], ["lecture", "Lecture"], ["region", "Region"], ["tags", "Tags"], ["difficulty", "Difficulty"]];
function bevaluate(im: { headers: string[]; rows: string[][] }, m: Record<string, string>) {
  const col = (r: string[], f: string) => (m[f] && im.headers.includes(m[f]) ? r[im.headers.indexOf(m[f])] ?? "" : "");
  const problems: { row: string; problem: string }[] = [], questions: BankImportPreview["questions"] = [];
  let ready = 0, duplicates = 0;
  im.rows.forEach((r, i) => {
    const opts = ["a", "b", "c", "d", "e"].map((c) => col(r, `option_${c}`)).filter(Boolean);
    if (!col(r, "lead_in")) { problems.push({ row: String(i + 1), problem: "the question is not mapped or is empty" }); return; }
    if (opts.length < 2) { problems.push({ row: String(i + 1), problem: "fewer than 2 options" }); return; }
    const ans = col(r, "answer").trim().toUpperCase();
    if (!ans) { problems.push({ row: String(i + 1), problem: "the correct answer is missing or does not match an option" }); return; }
    const dup = QBANK.some((b) => bdata(b).lead_in.toLowerCase() === col(r, "lead_in").toLowerCase());
    duplicates += dup ? 1 : 0; ready++;
    if (questions.length < 8) questions.push({ row: String(i + 1), lead_in: col(r, "lead_in"), options: opts.join(" | "), answer: ans, duplicate: dup ? "q-sample (100%)" : "" });
  });
  return { questions, problems, duplicates, ready };
}
export async function bankImportPreview(filename: string, importId?: string, mapping?: Record<string, string>): Promise<BankImportPreview> {
  await delay(); instructorSession();
  if (!importId) {
    if (!/\.(csv|xlsx|docx)$/i.test(filename)) throw new ApiError("Upload a .csv, .xlsx or .docx file.", 422);
    importId = `imp${Math.random().toString(16).slice(2, 10)}`;
    IMPORTS[importId] = { filename, headers: ["No.", "What is asked", "1", "2", "3", "4", "Right one", "Why", "Chapter"], rows: [
      ["1", "Which nerve is injured in a fractured surgical neck of the humerus?", "Axillary nerve", "Radial nerve", "Ulnar nerve", "Median nerve", "Axillary nerve", "It winds around the surgical neck.", "Lecture 06 - Shoulder"],
      ["2", "Which muscle initiates abduction of the arm?", "Supraspinatus", "Deltoid", "Teres minor", "Infraspinatus", "Supraspinatus", "", "Lecture 06 - Shoulder"],
      ["3", "Which nerve passes through the carpal tunnel?", "Median nerve", "Ulnar nerve", "Radial nerve", "Axillary nerve", "Median nerve", "", "Lecture 09 - The Hand"],
      ["4", "A row with a problem", "Only one option", "", "", "", "A", "", ""]] };
  }
  const im = IMPORTS[importId];
  if (!im) throw new ApiError("That import has expired. Upload the file again.", 404);
  const guess: Record<string, string> = mapping ?? { option_a: "1", option_b: "2", option_c: "3", option_d: "4", explanation: "Why" };
  return clone({ import_id: importId, filename: im.filename, headers: im.headers, rows: im.rows.slice(0, 5), n_rows: im.rows.length, mapping: guess, fields: FIELDS.map(([field, label]) => ({ field, label })), ...bevaluate(im, guess) });
}
export async function bankImportCommit(importId: string, mapping: Record<string, string>, status: string, use: string): Promise<BankImportResult> {
  await delay(); instructorSession(); const im = IMPORTS[importId];
  if (!im) throw new ApiError("That import has expired. Upload the file again.", 404);
  const ev = bevaluate(im, mapping); let created = 0;
  im.rows.forEach((r) => {
    const col = (f: string) => (mapping[f] && im.headers.includes(mapping[f]) ? r[im.headers.indexOf(mapping[f])] ?? "" : "");
    const opts = ["a", "b", "c", "d", "e"].map((c) => col(`option_${c}`)).filter(Boolean);
    if (!col("lead_in") || opts.length < 2 || !col("answer")) return;
    if (QBANK.some((b) => bdata(b).lead_in.toLowerCase() === col("lead_in").toLowerCase())) return;
    const ai = opts.findIndex((o) => o.toLowerCase() === col("answer").toLowerCase());
    const d: BankData = { stem: col("stem"), lead_in: col("lead_in"), options: opts.map((t, j) => ({ id: "ABCDE"[j], text: t })), answer: "ABCDE"[Math.max(0, ai)], explanation: col("explanation"), lecture: col("lecture"), guide: "", section: "", region: col("region"), tags: [], difficulty: "", source: "imported", status: status as BankData["status"], use: use as BankData["use"], objective: "" };
    QBANK.unshift({ id: `q-${Math.random().toString(16).slice(2, 12)}`, created: new Date().toISOString(), updated: new Date().toISOString(), versions: [{ version: 1, at: new Date().toISOString(), by: "inglis", note: `imported from ${im.filename}`, data: d }], comments: [], flags: bcheck(d), recheck: "", sample: false, used: 0 }); created++;
  });
  delete IMPORTS[importId];
  return { created, skipped_duplicates: ev.duplicates, problems: ev.problems, flagged: 0 };
}
