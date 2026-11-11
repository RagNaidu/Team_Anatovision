"""Import questions from CSV, XLSX or Word. Any column layout works: the file is read into a plain table, the instructor maps headers to fields in a preview,
and only then are questions created. Items from the instructor come in as status = draft and use = exam_secure."""
import csv
import io
import re

from src.qbank.store import BankError, IDS, normalize

MAX_ROWS = 2000
MAX_BYTES = 10 << 20
FIELDS = ["lead_in", "stem", "option_a", "option_b", "option_c", "option_d", "option_e", "answer", "explanation", "lecture", "guide", "section", "region", "tags", "difficulty"]
LABEL = {"lead_in": "Question (lead-in)", "stem": "Stem / vignette", "option_a": "Option A", "option_b": "Option B", "option_c": "Option C", "option_d": "Option D", "option_e": "Option E",
         "answer": "Correct answer", "explanation": "Explanation", "lecture": "Lecture", "guide": "Dissection guide", "section": "Section", "region": "Region", "tags": "Tags", "difficulty": "Difficulty"}
SYN = {"lead_in": ["question", "question text", "lead in", "leadin", "lead-in", "prompt", "q"], "stem": ["stem", "vignette", "scenario", "context", "case"],
       "answer": ["answer", "correct", "correct answer", "key", "right answer", "correct option", "ans"], "explanation": ["explanation", "rationale", "feedback", "why", "reason"],
       "lecture": ["lecture", "topic", "unit", "module", "source lecture"], "guide": ["guide", "dissection guide", "class"], "section": ["section", "subsection", "source section"],
       "region": ["region", "body region", "area"], "tags": ["tags", "tag", "keywords", "labels", "categories"], "difficulty": ["difficulty", "level", "diff"]}
TEMPLATE_ROWS = [["Which nerve passes through the carpal tunnel?", "", "Median nerve", "Ulnar nerve", "Radial nerve", "Musculocutaneous nerve", "", "A",
                  "The median nerve runs with the flexor tendons deep to the flexor retinaculum.", "Lecture 09 - The Hand", "", "", "Upper limb", "nerves; hand", "easy"]]


def norm_header(h):
    return re.sub(r"[^a-z0-9]+", " ", str(h or "").lower()).strip()


def suggest_mapping(headers):
    """{field: header} guessed from the header names; options by their letter in many spellings."""
    nh = {h: norm_header(h) for h in headers}
    out, used = {}, set()
    for i, letter in enumerate("abcde"):
        pats = {f"option {letter}", f"choice {letter}", f"answer {letter}", f"{letter}", f"{letter} option", f"opt {letter}", f"option{letter}", f"alternative {letter}", f"distractor {letter}", str(i + 1), f"option {i + 1}",
                f"choice {i + 1}", f"answer {i + 1}"}
        for h, n in nh.items():
            if n in pats and h not in used:
                out[f"option_{letter}"] = h
                used.add(h)
                break
    for field, syn in SYN.items():
        for h, n in nh.items():
            if h not in used and (n in syn or n == norm_header(LABEL[field])):
                out[field] = h
                used.add(h)
                break
    return out


# ---------------------------------------------------------------- reading files into a table
def read_csv(data):
    text = data.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect)]
    return rows


def read_xlsx(data):
    import openpyxl
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise BankError("That spreadsheet could not be opened. Save it as .xlsx or .csv and try again.")
    ws = wb.worksheets[0]
    return [["" if c is None else str(c) for c in row] for row in ws.iter_rows(values_only=True)]


QSTART = re.compile(r"^\s*(?:question\s*)?(\d{1,3})\s*[.):]\s*(.+)", re.I)
OPT = re.compile(r"^\s*\(?([A-Ea-e])[.)]\s*(.+)")
ANS = re.compile(r"^\s*(?:correct\s+)?(?:answer|key)\s*[:\-]\s*\(?([A-Ea-e])\b", re.I)
EXP = re.compile(r"^\s*(?:explanation|rationale)\s*[:\-]\s*(.*)", re.I)


def read_docx(data):
    """A Word file of numbered questions: '1. question', 'A. option' lines, 'Answer: C', optional 'Explanation: ...'."""
    import docx
    try:
        d = docx.Document(io.BytesIO(data))
    except Exception:
        raise BankError("That Word file could not be opened. Save it as .docx and try again.")
    lines = [p.text.strip() for p in d.paragraphs if p.text.strip()]
    qs, cur = [], None
    for ln in lines:
        m = ANS.match(ln)
        if m and cur:
            cur["answer"] = m.group(1).upper()
            continue
        m = EXP.match(ln)
        if m and cur:
            cur["explanation"] = m.group(1)
            cur["_last"] = "explanation"
            continue
        m = OPT.match(ln)
        if m and cur:
            cur["options"][m.group(1).upper()] = m.group(2).strip()
            cur["_last"] = "option"
            continue
        m = QSTART.match(ln)
        if m:
            cur = {"q": m.group(2).strip(), "options": {}, "answer": "", "explanation": "", "_last": "q"}
            qs.append(cur)
            continue
        if cur and cur["_last"] == "q":
            cur["q"] += " " + ln
        elif cur and cur["_last"] == "explanation":
            cur["explanation"] += " " + ln
    if not qs:
        raise BankError("No numbered questions were found in that Word file. Use '1. question', then 'A. option' lines and 'Answer: C'.")
    headers = ["Question", "A", "B", "C", "D", "E", "Answer", "Explanation"]
    return [headers] + [[q["q"], *[q["options"].get(i, "") for i in "ABCDE"], q["answer"], q["explanation"]] for q in qs]


def read_table(filename, data):
    """-> (headers, rows) with every row padded to the header length."""
    ext = re.search(r"\.[^.]+$", filename or "")
    ext = ext.group(0).lower() if ext else ""
    if ext not in (".csv", ".xlsx", ".docx", ".txt"):
        raise BankError("Upload a .csv, .xlsx or .docx file.")
    if not data:
        raise BankError("That file is empty.")
    if len(data) > MAX_BYTES:
        raise BankError("That file is larger than 10 MB.", 413)
    if ext == ".xlsx" and not data.startswith(b"PK\x03\x04") or ext == ".docx" and not data.startswith(b"PK\x03\x04"):
        raise BankError(f"That does not look like a real {ext} file.")
    rows = read_xlsx(data) if ext == ".xlsx" else read_docx(data) if ext == ".docx" else read_csv(data)
    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if len(rows) < 2:
        raise BankError("The file needs a header row and at least one question.")
    headers = [str(h).strip() or f"Column {i + 1}" for i, h in enumerate(rows[0])]
    seen = {}
    for i, h in enumerate(headers):
        seen[h] = seen.get(h, 0) + 1
        if seen[h] > 1:
            headers[i] = f"{h} ({seen[h]})"
    body = [[str(c) for c in r] + [""] * (len(headers) - len(r)) for r in rows[1:]]
    if len(body) > MAX_ROWS:
        raise BankError(f"That file has {len(body)} questions. The limit is {MAX_ROWS} per import.")
    return headers, [r[:len(headers)] for r in body]


# ---------------------------------------------------------------- mapping rows to questions
def split_tags(text):
    return [t.strip() for t in re.split(r"[;,|]", text or "") if t.strip()]


def to_question(row, headers, mapping, defaults):
    """-> (data dict, problem or None). The answer may be a letter, a number 1-5 or the text of an option."""
    idx = {h: i for i, h in enumerate(headers)}
    get = lambda f: (row[idx[mapping[f]]].strip() if mapping.get(f) in idx else "")
    opts = [get(f"option_{c}") for c in "abcde"]
    shown = [(IDS[i], t) for i, t in enumerate(opts) if t]
    if len(shown) < 2:
        return None, "fewer than 2 options"
    ans = get("answer")
    letter = ""
    a = ans.strip().strip("().").upper()
    if a in list("ABCDE") and opts["ABCDE".index(a)]:
        letter = a
    elif a.isdigit() and 1 <= int(a) <= 5 and opts[int(a) - 1]:
        letter = IDS[int(a) - 1]
    else:
        for i, t in enumerate(opts):
            if t and ans and re.sub(r"\W+", "", t.lower()) == re.sub(r"\W+", "", ans.lower()):
                letter = IDS[i]
    if not letter:
        return None, "the correct answer is missing or does not match an option"
    kept = [t for t in opts if t]
    new_letter = IDS[sum(1 for t in opts[:"ABCDE".index(letter)] if t)]      # options are renumbered A.. without gaps
    d = {"stem": get("stem"), "lead_in": get("lead_in"), "options": [{"id": IDS[i], "text": t} for i, t in enumerate(kept)], "answer": new_letter, "explanation": get("explanation"),
         "lecture": get("lecture"), "guide": get("guide"), "section": get("section"), "region": get("region"), "tags": split_tags(get("tags")),
         "difficulty": get("difficulty").lower() if get("difficulty").lower() in ("easy", "medium", "hard") else "", **defaults}
    try:
        return normalize(d), None
    except BankError as exc:
        return None, str(exc)


def template_csv():
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([LABEL[f] for f in FIELDS])
    w.writerows(TEMPLATE_ROWS)
    return out.getvalue()


def template_xlsx():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Questions"
    ws.append([LABEL[f] for f in FIELDS])
    for r in TEMPLATE_ROWS:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()
