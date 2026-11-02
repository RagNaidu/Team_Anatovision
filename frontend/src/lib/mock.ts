// Mock backend for VITE_USE_MOCK=true. Same shapes as docs/api_contract.md. State lives in memory (the signed-in user in sessionStorage,
// so a page reload keeps you signed in, like the real httpOnly cookie). Any password works. Users: "inglis" (instructor), "student1".
import { ApiError } from "./api";
import type {
  AdminStats, AskBody, AskStatus, ChatDetail, ChatSummary, GuideSummary, Me, Message, OpenQuiz, QuestionPage, QuestionRow, QuizBuildBody,
  QuizHistoryItem, QuizJob, QuizLatest, QuizResults, ResultQuestion, ReviewItem, ReviewPage, Scope, Source, Station, StationCheck, Student, User,
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

function pickAnswer(q: string): Omit<Message, "id" | "created_at"> {
  const t = q.toLowerCase();
  if (t.startsWith("explain this more simply")) return SIMPLE;
  if (/amoxicillin|dose|dosage|prescri|how much .* mg/.test(t)) return REFUSED;
  if (/waldeyer/.test(t)) return WALDEYER;
  if (/sciatic/.test(t)) return NOTES_GATED;
  if (/^\s*apex\s*\??$/.test(t)) return APEX;
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
  return clone(STATIONS[id]);
}
export async function lectureStations(id: string): Promise<Station[]> {
  await delay();
  session();
  const l = LECTURES.find((x) => x.id === id);
  if (!l) throw new ApiError("That lecture wasn't found.", 404);
  if (!l.granted) throw new ApiError("That lecture isn't open to you yet. Ask your instructor.", 403);
  return clone(LECTURE_STATIONS);
}
export async function checkStation(id: string, index: number, description: string): Promise<StationCheck> {
  await delay();
  studentSession();
  const st = STATIONS[id]?.[index];
  if (!st) throw new ApiError("That station wasn't found.", 404);
  if (st.image_only) throw new ApiError(`This station is a picture. See slide ${st.slides[0]} in your lab guide.`, 422);
  const src: Source = { n: 1, type: "guide", title: "Dissection guide", subtitle: `Class ${id.slice(6)}, slide ${st.slides[0]}`, lecture_id: id === "class-17" ? "L08" : null, url: null, snippet: st.steps.join(" "), retrieved_at: null, license: null };
  const t = description.toLowerCase();
  if (/error|fail/.test(t)) throw new ApiError("The AI service couldn't check that. Please try again.", 502);
  if (t.length < 25) return { verdict: "not_matching", feedback_markdown: "That doesn't match this station yet. The guide asks for the following: " + st.steps[0] + " [1]", sources: [src] };
  if (/sartorius|saphenous|piriformis|median|vein|artery|nerve/.test(t)) return { verdict: "correct", feedback_markdown: "That matches the guide. " + st.steps[st.steps.length - 1] + " [1]", sources: [src] };
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
interface QuizRec { id: string; status: "open" | "offer"; length: number; picks: Record<string, string[]>; current: number; submitted: string | null; user: string }
const QUIZZES = new Map<string, QuizRec>();
QUIZZES.set("qpast1", { id: "qpast1", status: "open", length: 5, picks: { 0: ["B"], 1: ["C"], 2: ["A"], 3: ["B"], 4: ["A"] }, current: 4, submitted: iso(2, 15), user: "student1" });
QUIZZES.set("qpast2", { id: "qpast2", status: "open", length: 5, picks: { 0: ["B"], 1: ["C"], 2: ["A"], 3: ["B"], 4: ["C"] }, current: 4, submitted: iso(9, 17), user: "student1" });
const JOBS = new Map<string, { polls: number; body: QuizBuildBody; offer: boolean; fail: boolean }>();
let lastOffer: string | null = null;

export async function buildQuiz(body: QuizBuildBody): Promise<{ job_id: string }> {
  await delay();
  studentSession();
  if ([...JOBS.values()].some((j) => j.polls < 6)) throw new ApiError("A quiz is already being prepared. Wait for it to finish.", 409);
  if (body.mode === "topic" && (!body.topic || body.topic.trim().length < 3)) throw new ApiError("A topic needs 3 to 80 characters.", 422);
  const id = `job${Math.random().toString(36).slice(2, 8)}`;
  JOBS.set(id, { polls: 0, body, offer: body.n === 10, fail: /zzz/.test(body.topic ?? "") });
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
  if (j.fail) return { done: true, have: 0, requested: req, note: "", result: { status: "failed", reason: "insufficient_evidence", quiz_id: null, have: 0, requested: req, message: "There isn't enough material on that topic to write good questions. Try a broader topic." } };
  const qid = `q${Math.random().toString(36).slice(2, 10)}`;
  if (j.offer) {
    QUIZZES.set(qid, { id: qid, status: "offer", length: 5, picks: {}, current: 0, submitted: null, user: "student1" });
    lastOffer = qid;
    return { done: true, have: 6, requested: 10, note: "", result: { status: "offer", reason: "", quiz_id: qid, have: 6, requested: 10, message: "6 of 10 questions are ready. You can start with 5 or keep preparing." } };
  }
  QUIZZES.set(qid, { id: qid, status: "open", length: req, picks: {}, current: 0, submitted: null, user: "student1" });
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
    questions: BANK.slice(0, q.length).map((b) => ({ stem: b.stem, lead_in: b.lead, selection_mode: "single" as const, options: b.options.map((t, i) => ({ id: "ABCD"[i], text: t })) })),
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
function resultsFor(q: QuizRec): QuizResults {
  const questions: ResultQuestion[] = BANK.slice(0, q.length).map((b, i) => {
    const selected = q.picks[String(i)] ?? [];
    const ansId = "ABCD"[b.answer];
    const alternatives: Record<string, string> = {};
    b.alts.forEach((t, k) => { if (t && k !== b.answer) alternatives["ABCD"[k]] = t; });
    return {
      n: i + 1, stem: b.stem, lead_in: b.lead, options: b.options.map((t, k) => ({ id: "ABCD"[k], text: t })), selected, answer_ids: [ansId],
      correct: selected.length === 1 && selected[0] === ansId, explanation: b.why, alternatives,
      evidence: [{ id: "e1", label: "Lecture 08 - Anterior and Medial Thigh › Femoral Triangle", tier: "Course material", url: null, visible: true, text: b.evidence, license: null }],
      label: "AI-checked (two models agreed and sources were checked). Not reviewed by Dr. Inglis.", review_status: "unreviewed",
      spans: [{ source_id: "e1", span: b.span }],
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
  await delay();
  studentSession();
  return [...QUIZZES.values()].filter((q) => q.submitted).sort((a, b) => (b.submitted ?? "").localeCompare(a.submitted ?? ""))
    .map((q) => ({ id: q.id, score: resultsFor(q).score, length: q.length, submitted: q.submitted! }));
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
  { id: "r8", type: "doubtful", status: "dismissed", lecture: "Lecture 09 - The Hand", section: "Carpal Tunnel", original_text: "Nine tendons pass through the carpal tunnel.", ai_note: "Correct: four FDS, four FDP and FPL.", sources: [] },
];
export async function adminStats(): Promise<AdminStats> {
  await delay();
  instructorSession();
  return { questions_7d: 84, flagged_open: 5, web_answers_7d: 11, review_counts: { confirmed_factual: 90, doubtful: 32, wording: 442, typo: 169, start_here: 14 } };
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
