"""Request and response shapes. These ARE the contract (docs/api_contract.md): the response models strip anything not listed here,
so an endpoint cannot send a field the contract does not name."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Error(Model):
    error: str


class Ok(Model):
    ok: bool = True


# ---- auth ----
class LoginIn(Model):
    username: str = Field(max_length=100)
    password: str = Field(max_length=500)


class User(Model):
    id: str
    name: str
    role: Literal["student", "instructor"]


class PreviewState(Model):
    profile: str
    name: str


class UserOut(Model):
    user: User


class MeOut(Model):
    user: User
    preview: Optional[PreviewState] = None


# ---- scope ----
class LectureScope(Model):
    id: str
    title: str
    granted: bool


class GuideScope(Model):
    id: str
    class_number: int
    title: str
    lecture_ids: List[str]
    granted: bool


class ScopeOut(Model):
    lectures: List[LectureScope]
    guides: List[GuideScope]


# ---- messages ----
SourceType = Literal["notes", "guide", "openstax", "wikipedia", "web", "verified_fix"]


class Source(Model):
    n: int
    type: SourceType
    title: str
    subtitle: str
    lecture_id: Optional[str] = None
    url: Optional[str] = None
    snippet: str
    retrieved_at: Optional[str] = None
    license: Optional[str] = None
    revision: Optional[Literal["updated", "removed"]] = None        # additive: a saved answer's notes / guide source that the revised notes changed or removed


class Mark(Model):
    id: str
    slide: int
    crop: int = 1
    kind: Literal["arrow", "cut", "highlight", "label"]
    geom: Dict[str, Any]
    text: str = ""
    step: Optional[int] = None
    n: int


class StationImage(Model):
    slide: int
    crop: int = 1
    url: str
    thumb_url: str
    caption: str
    alt: str
    w: int = 0
    h: int = 0
    marks: List[Mark] = []


class ChatImage(StationImage):
    guide_id: str
    source_n: int
    step: Optional[int] = None


class Footer(Model):
    basis_line: Optional[str] = None
    access_note: Optional[str] = None


class Message(Model):
    id: str
    role: Literal["user", "assistant"]
    created_at: str
    kind: Literal["answer", "term_lookup", "not_covered", "refused", "error"]
    markdown: str
    sources: List[Source]
    footer: Optional[Footer] = None
    timing_ms: int
    images: List["ChatImage"] = []              # additive: slide image cards of the guide steps this answer used (only guides the student may open)


# ---- chats ----
class ChatItem(Model):
    id: str
    title: str
    updated_at: str


class ChatOut(Model):
    id: str
    title: str
    messages: List[Message]


class TitleIn(Model):
    title: str = Field(max_length=120)


class TitleOut(Model):
    id: str
    title: str


class AskIn(Model):
    chat_id: str = Field(max_length=64)
    question: str
    length: Literal["brief", "detailed"] = "brief"
    lecture_ids: Optional[List[str]] = None
    body_type: Optional[str] = Field(default=None, max_length=80)         # additive: "more fat, average muscle, small build"
    request_id: Optional[str] = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")      # additive: lets the client poll /api/ask/status/{id}


class AskStatus(Model):
    stage: Literal["searching", "reading", "writing", "checking", "done"]


class FlagIn(Model):
    reason: str = Field(max_length=500)
    comment: Optional[str] = Field(default=None, max_length=500)


# ---- guides ----
class GuideItem(Model):
    id: str
    class_number: int
    title: str
    region: str
    station_count: int
    granted: bool


class Station(Model):
    index: int
    title: str
    steps: List[str]
    slides: List[int]
    image_only: bool
    images: List[StationImage] = []             # additive: the slide images of this station with their APPROVED marks


GuideBodyType = Literal["lean", "average", "more_fat", "more_muscular", "not_sure"]


class CheckIn(Model):
    description: str
    body_type: Optional[GuideBodyType] = None                 # additive: the cadaver's body type for this guide session


class CheckOut(Model):
    verdict: Literal["correct", "partly", "not_matching"]
    feedback_markdown: str
    sources: List[Source]


# ---- quiz ----
class BuildIn(Model):
    mode: Literal["materials", "topic"]
    lecture_ids: Optional[List[str]] = None
    guide_ids: Optional[List[str]] = None
    topic: Optional[str] = Field(default=None, max_length=80)
    n: Literal[5, 10] = 5
    reviewed_only: bool = False
    different_style: bool = False                    # additive: only when the student asks for a different style than the instructor's examples
    continue_quiz_id: Optional[str] = Field(default=None, max_length=64)


class JobOut(Model):
    job_id: str


class BuildResult(Model):
    status: Literal["ready", "offer", "partial", "failed"]
    reason: str
    quiz_id: Optional[str] = None
    have: int
    requested: int
    message: str


class JobStatus(Model):
    done: bool
    have: int
    requested: int
    note: str
    result: Optional[BuildResult] = None


class LatestQuiz(Model):
    id: str
    status: Literal["open", "offer"]
    length: int
    answered: int


class QuizOption(Model):
    id: str
    text: str


class QuizQuestion(Model):
    stem: str
    lead_in: str
    selection_mode: str
    options: List[QuizOption]
    web: bool = False                                         # additive: built from the web (Wikipedia), not from the course notes
    source_note: Optional[str] = None                        # additive: "Not from course notes" when web, else null


class OpenQuiz(Model):
    quiz_id: str
    length: int
    current: int
    answered: int
    questions: List[QuizQuestion]
    selections: Dict[str, List[str]]


class AnswerIn(Model):
    option_ids: List[str] = Field(max_length=6)


class AnsweredOut(Model):
    ok: bool = True
    answered: int


class CurrentIn(Model):
    index: int = Field(ge=0, le=9)


class EvidenceItem(Model):
    id: str
    label: str
    tier: str
    url: Optional[str] = None
    visible: bool
    text: str
    license: Optional[str] = None


class SpanOut(Model):
    source_id: str
    span: str


class ResultQuestion(Model):
    n: int
    stem: str
    lead_in: str
    options: List[QuizOption]
    selected: List[str]
    answer_ids: List[str]
    correct: bool
    explanation: str
    alternatives: Dict[str, str]
    evidence: List[EvidenceItem]
    label: str
    review_status: str
    spans: List[SpanOut] = []                                 # additive: the supporting lines to highlight in the evidence
    web: bool = False                                         # additive: this question was built from the web (Wikipedia)
    source_note: Optional[str] = None                        # additive: "Not from course notes" when web, else null


class Results(Model):
    quiz_id: str
    score: int
    length: int
    submitted: Optional[str] = None
    questions: List[ResultQuestion]


class HistoryItem(Model):
    id: str
    score: Optional[int] = None
    length: int
    submitted: Optional[str] = None
    title: str = "Quiz"                                       # additive: the topic, or the lecture / guide names ("Femoral triangle")
    web: bool = False                                         # additive: at least one question was built from the web


class GuideHistoryItem(Model):
    id: str                                                   # "guide:class-17" or "lecture:L08-anterior-and-medial-thigh"
    kind: str                                                 # "guide" | "lecture"
    ref: str                                                  # the guide id or lecture id (the page is /guide/{ref}/{station} or /guide/lecture/{ref}/{station})
    title: str
    station: int                                              # 0-based station reached
    count: int
    updated_at: str
    body_type: Optional[str] = None                           # additive: the body type chosen for this guide, or null
    notice: Optional[str] = None                              # additive: set once when a revised guide moved or reset the student's place


class GuideHistoryIn(Model):
    kind: str = Field(pattern="^(guide|lecture)$")
    ref: str = Field(max_length=120)
    station: int = Field(ge=0, le=500)
    body_type: Optional[GuideBodyType] = None                 # additive: saved for this guide when given; kept as it was when omitted


class BodyTipLine(Model):
    text: str
    general: bool                                             # true = "General tip, not from your notes: ..."


class BodyTipOut(Model):
    body_type: str
    lines: List[BodyTipLine]


class WebQuizItem(Model):
    id: str
    student: str
    title: str
    status: str
    score: Optional[int] = None
    length: int
    web_questions: int
    sources: List[dict]
    created_at: str


class WebQuizPage(Model):
    items: List[WebQuizItem]
    total: int


# ---- admin ----
class ReviewCounts(Model):
    confirmed_factual: int
    doubtful: int
    wording: int
    typo: int
    start_here: int


class StatsOut(Model):
    questions_7d: int
    flagged_open: int
    web_answers_7d: int
    review_counts: ReviewCounts
    bank_counts: Optional[Dict[str, int]] = None       # additive: {total, draft, approved, retired, exam_secure, flagged, needs_recheck}


class ReviewItem(Model):
    id: str
    type: str
    status: Literal["open", "verified", "dismissed", "changed"]       # "changed" (additive): the quoted line is no longer in the revised notes
    lecture: str
    section: str
    original_text: str
    ai_note: str
    sources: List[Source]


class ReviewList(Model):
    items: List[ReviewItem]
    total: int


class ReviewActionIn(Model):
    action: Literal["verify", "dismiss"]
    fix_text: Optional[str] = Field(default=None, max_length=1000)


class QuestionItem(Model):
    id: str
    student: str
    question: str
    kind: str
    web: bool
    flagged: bool
    created_at: str
    message: Optional[Message] = None


class QuestionList(Model):
    items: List[QuestionItem]
    total: int


class StudentItem(Model):
    id: str
    name: str
    username: str
    lecture_ids: List[str]
    guide_ids: List[str]


class AccessIn(Model):
    lecture_ids: List[str] = Field(max_length=200)
    guide_ids: List[str] = Field(max_length=200)


class PreviewIn(Model):
    profile: str = Field(max_length=100)


# ---- Notes manager (instructor only) ----
class NoteRow(Model):
    id: str
    kind: Literal["note", "guide"]
    title: str
    region: str
    version: int
    status: Literal["draft", "processing", "ready", "published", "archived"]
    updated_at: str
    access_count: int
    note: str = ""
    earlier_version: bool = False


class NoteList(Model):
    items: List[NoteRow]
    regions: List[str]
    total: int


class NoteJob(Model):
    status: str
    step: str
    step_index: int
    steps: List[str]
    error: str = ""
    version: int


class NoteSection(Model):
    path: List[str]
    text: str


class NoteFlag(Model):
    quote: str
    issue: str
    severity: str = ""
    tier: str = ""
    section: str = ""


class NoteFlags(Model):
    count: int
    items: List[NoteFlag]


class NoteOverlap(Model):
    doc_id: str
    title: str
    score: float
    shared_sections: int = 0
    sections: int = 0
    suggest_replace: bool = False


class NoteMapping(Model):
    region: str = ""
    lecture: str = ""
    title: str = ""


class NoteDiffRow(Model):
    status: Literal["unchanged", "edited", "rewritten", "added", "removed"]
    path: str
    old: str = ""
    new: str = ""


class NoteDiff(Model):
    against: Optional[str] = None
    counts: Dict[str, int]
    rows: List[NoteDiffRow]


class NoteDetail(Model):
    id: str
    kind: Literal["note", "guide"]
    title: str
    region: str
    status: Literal["draft", "processing", "ready", "published", "archived"]
    version: int
    live_version: Optional[int] = None
    shown_version: Optional[int] = None
    created_at: str
    updated_at: str
    replaces: Optional[str] = None
    replaces_title: Optional[str] = None
    overlap: Optional[NoteOverlap] = None
    source_name: str = ""
    job: Optional[NoteJob] = None
    sections: List[NoteSection]
    mapping: NoteMapping
    flags: NoteFlags
    diff: Optional[NoteDiff] = None
    archived_at: Optional[str] = None
    purge_after: Optional[str] = None
    grants_mode: str = "none"
    has_pending: bool = False
    editable: bool = False
    guide_id: Optional[str] = None            # additive: the catalog id of a published dissection guide (for its image annotations)
    regions: List[str] = []
    lectures: List[str] = []


class NoteCreated(Model):
    doc_id: str
    version: int


class NoteMappingIn(Model):
    region: Optional[str] = Field(default=None, max_length=60)
    replaces: Optional[str] = Field(default=None, max_length=200)
    lecture: Optional[str] = Field(default=None, max_length=200)


class NotePublishIn(Model):
    access: Literal["all", "selected", "none", "same"] = "none"
    students: List[str] = Field(default=[], max_length=500)


class NoteEdit(Model):
    index: int = Field(ge=0)
    text: str = Field(max_length=60000)


class NoteEditIn(Model):
    edits: List[NoteEdit] = Field(max_length=500)
    note: str = Field(default="", max_length=200)


class NoteRollbackIn(Model):
    version: int = Field(ge=1)


class NotePurgeIn(Model):
    confirm_title: str = Field(max_length=300)


class NoteChange(Model):
    doc_id: str
    version: Optional[int] = None
    granted: int = 0
    flags_added: int = 0
    fixes_to_recheck: int = 0
    progress_moved: int = 0
    restorable_until: Optional[str] = None


class NoteVersion(Model):
    version: int
    status: str
    created_at: str
    created_by: str = ""
    note: str = ""
    n_sections: int
    source_name: str = ""
    diff: Optional[Dict[str, int]] = None


class NoteAuditRow(Model):
    at: str
    user: str
    action: str
    detail: str = ""


# ---- Question bank (instructor only) ----
class BankOption(Model):
    id: str
    text: str


class BankFlag(Model):
    kind: str
    code: str
    severity: str
    message: str
    dismissed: bool = False


class BankRow(Model):
    id: str
    lead_in: str
    stem: str = ""
    status: Literal["draft", "approved", "retired"]
    use: Literal["practice", "exam_secure"]
    source: Literal["instructor", "ai", "web", "imported"]
    lecture: str = ""
    region: str = ""
    tags: List[str]
    difficulty: str = ""
    version: int
    updated_at: str
    flagged: bool
    n_flags: int
    needs_recheck: bool
    sample: bool = False
    used: int = 0


class BankCounts(Model):
    total: int
    draft: int
    approved: int
    retired: int
    exam_secure: int
    flagged: int
    needs_recheck: int


class BankList(Model):
    items: List[BankRow]
    total: int
    counts: BankCounts
    lectures: List[str]
    regions: List[str]
    tags: List[str]


class BankData(Model):
    stem: str = Field(default="", max_length=2000)
    lead_in: str = Field(max_length=500)
    options: List[BankOption] = Field(max_length=5)
    answer: str = Field(max_length=1)
    explanation: str = Field(default="", max_length=3000)
    lecture: str = Field(default="", max_length=200)
    guide: str = Field(default="", max_length=200)
    section: str = Field(default="", max_length=400)
    region: str = Field(default="", max_length=60)
    tags: List[str] = Field(default=[], max_length=12)
    difficulty: Literal["", "easy", "medium", "hard"] = ""
    source: Literal["instructor", "ai", "web", "imported"] = "instructor"
    status: Literal["draft", "approved", "retired"] = "draft"
    use: Literal["practice", "exam_secure"] = "practice"
    objective: str = Field(default="", max_length=300)


class BankDistractor(Model):
    text: str
    picks: int
    correct: bool


class BankStats(Model):
    n: int
    p_correct: Optional[float] = None
    discrimination: Optional[float] = None
    enough: bool = False
    distractors: List[BankDistractor] = []
    min_for_stats: int
    min_for_flags: int


class BankComment(Model):
    id: int
    at: str
    by: str
    text: str


class BankVersion(Model):
    version: int
    at: str
    by: str
    note: str
    changed: List[str]


class BankDetail(Model):
    id: str
    version: int
    created_at: str
    updated_at: str
    data: BankData
    sample: bool = False
    flags: List[BankFlag]
    needs_recheck: str = ""
    stats: BankStats
    comments: List[BankComment]
    versions: List[BankVersion]


class BankSaveIn(BankData):
    note: str = Field(default="", max_length=200)


class BankBulkIn(Model):
    ids: List[str] = Field(max_length=2000)
    action: Literal["approve", "retire", "draft", "set_use", "add_tag", "remove_tag", "run_checks"]
    value: str = Field(default="", max_length=60)


class BankBulkOut(Model):
    changed: int


class BankRestoreIn(Model):
    version: int = Field(ge=1)


class BankCommentIn(Model):
    text: str = Field(max_length=2000)


class BankDismissIn(Model):
    kind: str = Field(max_length=20)
    code: str = Field(max_length=60)
    dismissed: bool = True


class BankImportPreview(Model):
    import_id: str
    filename: str
    headers: List[str]
    rows: List[List[str]]
    n_rows: int
    mapping: Dict[str, str]
    fields: List[Dict[str, str]]
    questions: List[Dict[str, str]]
    problems: List[Dict[str, str]]
    duplicates: int
    ready: int


class BankImportIn(Model):
    import_id: str = Field(max_length=40)
    mapping: Dict[str, str] = Field(max_length=30)
    status: Literal["draft", "approved", "retired"] = "draft"
    use: Literal["practice", "exam_secure"] = "exam_secure"
    skip_duplicates: bool = True


class BankImportOut(Model):
    created: int
    skipped_duplicates: int
    problems: List[Dict[str, str]]
    flagged: int


# ---- Guide image annotations (instructor only) ----
class AdminMark(Mark):
    status: Literal["draft", "approved"]
    author: str = ""
    version: int
    source: Literal["manual", "auto", "ocr"]
    flag: str = ""


class AdminImage(StationImage):
    marks: List[AdminMark] = []
    confidence: Literal["high", "low"] = "high"
    why: str = ""
    reviewed: bool = False
    original_url: str = ""


class AnnStation(Model):
    index: int
    title: str
    steps: List[str]
    slides: List[int]
    image_only: bool
    images: List[AdminImage]
    drafts: int
    approved: int


class AnnGuide(Model):
    guide_id: str
    title: str
    stations: List[AnnStation]
    rendered: bool


class MarkIn(Model):
    slide: int = Field(ge=1)
    crop: int = Field(default=1, ge=1)
    kind: Literal["arrow", "cut", "highlight", "label"]
    geom: Dict[str, Any]
    text: str = Field(default="", max_length=80)
    step: Optional[int] = Field(default=None, ge=0)


class MarkPatch(Model):
    geom: Optional[Dict[str, Any]] = None
    text: Optional[str] = Field(default=None, max_length=80)
    step: Optional[int] = Field(default=None, ge=0)


class MarkOrderIn(Model):
    slide: int = Field(ge=1)
    crop: int = Field(default=1, ge=1)
    ids: List[str] = Field(max_length=200)


class ApproveIn(Model):
    approve: bool = True


class Changed(Model):
    changed: int


class CropReviewIn(Model):
    ok: bool = True


class ExplainIn(Model):
    body_type: Optional[GuideBodyType] = None


class ExplainOut(Model):
    text: str
    label: str
    sources: List[Source]
