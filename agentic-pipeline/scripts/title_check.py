"""Do lecture titles match their content? gpt-oss-120b sees only the content (headings and first words), then compares with the title.
Also: does each guide's own title slide agree with its file name? Writes reports/title_content_mismatches.md."""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import llm
from src.ingest import guide_map as M, guides as G

SYS = ("You get the CONTENT of one set of anatomy lecture notes (section headings with their first words) and its TITLE. First say what body region or "
       "topic the content really covers (max 14 words), then whether the TITLE describes that content. Reply with ONE JSON object: "
       '{"covers": "...", "match": "yes"|"partly"|"no", "why": "one sentence naming what is in the content but not the title, or in the title but not the content"}.')
SCHEMA = {"type": "object", "properties": {"covers": {"type": "string"}, "match": {"type": "string", "enum": ["yes", "partly", "no"]}, "why": {"type": "string"}},
          "required": ["covers", "match", "why"], "additionalProperties": False}

def main():
    client = llm.make_client()
    lectures, titles = M.lecture_sections()
    rows = []
    for lid, secs in lectures.items():
        for _ in (1, 2):
            try:
                d, _u = llm.complete_json(client, SYS, [{"role": "user", "content": f"TITLE: {titles[lid]}\n\nCONTENT:\n{M.lecture_digest(secs, 5000)}"}], 3000, SCHEMA, M.JUDGE_MODEL)
                break
            except Exception as e:
                d = {"covers": "?", "match": "error", "why": str(e)[:100]}
        rows.append((lid, titles[lid], d))
        print(d["match"], titles[lid], flush=True)
    files = {}
    for line in open(G.SLIDES_PATH):
        r = json.loads(line)
        if r["n"] == 1:
            files[r["file"]] = " ".join(r["texts"])
    guide_issues = []
    for fn, t in files.items():
        m = re.search(r"Class\s+(\d+)\s*[–-]\s*(.+?)(?:\s+Laboratory|$)", t)
        n, _ = G.parse_name(fn)
        if m and int(m.group(1)) != n:
            guide_issues.append((fn, f"its own title slide says Class {m.group(1)} ({m.group(2).strip()[:50]})"))
    L = ["# Lecture files whose title does not match their content\n", "For Dr. Inglis. Method: `scripts/title_check.py` gives `openai/gpt-oss-120b` only a lecture's content (section headings with their first words), "
         "asks what the content covers, then asks whether the title describes it. Nothing was renamed; the original files and the titles shown in the app are unchanged. "
         "The judge is an AI opinion: please check each line.\n", "## Lecture notes\n", "| Lecture file title | Content actually covers | Title matches? | Note |", "|---|---|---|---|"]
    for lid, t, d in sorted(rows, key=lambda r: {"no": 0, "partly": 1}.get(r[2]["match"], 2)):
        L.append(f"| {t} | {d['covers']} | **{d['match']}** | {d['why']} |")
    L += ["", "## Dissection guide files\n"]
    L += [f"- `{fn}`: {why}." for fn, why in guide_issues] or ["- none"]
    Path(ROOT / "reports" / "title_content_mismatches.md").write_text("\n".join(L) + "\n", encoding="utf-8")
main()
