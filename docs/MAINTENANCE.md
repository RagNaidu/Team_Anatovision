# Maintain the project

## Where to make changes

| Change | Files |
| --- | --- |
| Dashboard UI and interactions | `app/workspace.tsx` |
| Colors, layout and responsive styling | `app/globals.css` |
| Page title and metadata | `app/layout.tsx` |
| Review findings, references and wording | `data/findings.json` |
| Extracted lecture text and paragraph indexes | `data/lectures.json` |
| Durable review decisions and approval rules | `app/api/review/route.ts` |
| Retrieval, evidence citations and LLM behavior | `app/api/ask/route.ts` |
| Browser Word export | `lib/export-docx.ts` |
| Reviewer gate | `build/review-auth.mts`, `build/worker.ts` |
| Database schema | `db/schema.ts`, new `drizzle/` migrations |
| Deployment | `wrangler.json`, `.github/workflows/deploy.yml` |

## Update findings and commented documents

`data/findings.json` is the current source of review proposals. Every finding has a stable ID, lecture ID, original zero-based paragraph index, exact original passage, explanation, suggested wording, priority and evidence references. Word paragraph positions count blank paragraphs as well. Do not renumber existing finding IDs: saved D1 decisions refer to them.

For a newly changed finding, invalidate prior review decisions for that finding and the lecture approval in the database before using it as approved content. The current API invalidates approval when a decision is saved, but does not automatically detect wording changes to an existing finding ID. Version-specific approvals are a next implementation milestone.

After editing findings:

```sh
python -m pip install -r review-tools/requirements.txt
python review-tools/comment_lectures.py
python review-tools/verify_documents.py
pnpm verify
```

The generator rebuilds all ten commented documents, the download ZIP, index and `review-output/` deliverables from original notes. Original wording remains unchanged. Open the changed Word documents and inspect their comments and layout before committing. The original review checked all 74 rendered pages; future document edits need their own visual check.

`review-tools/build_findings.py` is the historical reconstruction script used for this review, not an autonomous factual checker. It rebuilds the initial curated findings and can overwrite later edits. Normally edit the canonical findings JSON and regenerate comments; use the reconstruction script only to reproduce the initial review in a disposable checkout.

## Add a lecture

Put the new original `.docx` in a temporary local folder, then:

```sh
python review-tools/import_lecture.py path/to/new-notes.docx --number 11 --title "Lecture title"
```

This extracts text, preserves original paragraph indexes, copies the Word file and creates browser export parts. It does not review factual accuracy or approve the lecture. Tables are rejected for separate structured handling instead of silently losing table structure. Images remain in Word files; image content is not analyzed as part of text import.

Add evidence-backed findings manually after reviewing the full lecture, regenerate comments, then get faculty approval. The ten-lecture dashboard has some hardcoded counts/text. Update those to derive from `lectures.length` before adding more lectures; search `app/workspace.tsx` for `10` and `ten` rather than assuming the importer updates UI copy.

Replacing an original requires fresh paragraph anchors and re-review. The importer refuses replacement while findings reference that lecture. Archive the old version, preserve its findings and decisions, and introduce a versioned content model before replacing approved student sources.

## Connect professor-approved revised notes

The external Box folders are the client's editorial source of truth. Receiving an approved revised file is a separate step from clicking Accept in the dashboard. Next implementation should:

- Import the revised file as a separate immutable content version.
- Record professor approval, date, source filename and version.
- Keep original, commented and revised versions associated.
- Retrieve only from approved revised versions.
- Preserve evidence/citation locations after professor edits.

Do not substitute the current demo's suggested paragraph rewrites for the professor's actual revised notes in the production knowledge base.

## Long-term Phase 1 and Phase 2

The current export preserves the working review prototype. For the public learning platform, next work is revised-content ingestion, faculty/student roles, protected reviewer routes, public approved-study views, stronger retrieval and a measured Q&A evaluation set. Move large/private document storage out of the web asset directory when introducing public access.

Phase 2 adds the NBME writing guide, approved-source question generation, expert question review and question-bank delivery. It should use the same versioned approved knowledge without exposing draft notes or unreviewed questions as authoritative.

## Checks and records

- `pnpm verify`: TypeScript, reviewer-access tests and production build.
- `python review-tools/verify_documents.py`: original wording, comment counts/anchors, paragraph references and ZIP contents.
- GitHub CI performs these checks for future pushes and pull requests.
- Runtime database records are backed up separately using `pnpm db:backup`.
- Browser QA is still needed after interaction changes. The last hosted-demo check verified the server workflows and downloads; full browser preview was unavailable.

## Dependency updates

Keep `pnpm-lock.yaml` committed. For a targeted update, use `pnpm update PACKAGE`, then run all checks and review the lockfile diff. Avoid `latest` upgrades across the whole stack before a client demo. Never commit `.dev.vars`, `.env`, Cloudflare tokens or OpenAI keys.
