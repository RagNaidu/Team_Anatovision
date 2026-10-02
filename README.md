# Anatomy Evidence Lab

A private anatomy lecture review workspace for the CDA 650 project. The dashboard shows ten original lectures and 53 proposed factual, terminology, mechanism and omission findings. Reviewers can read highlighted passages, inspect references, save notes, accept or reject suggestions, and download commented Word documents.

**Start here:** [GitHub setup](docs/GITHUB_SETUP.md) → [local setup and deployment](docs/DEPLOYMENT.md) → [ongoing changes](docs/MAINTENANCE.md).

## Included

| Location | Contents |
| --- | --- |
| `app/` | Dashboard, study-library and Q&A views; review and answer APIs |
| `data/` | Ten extracted lectures and all 53 proposed findings with evidence URLs |
| `public/documents/` | Original Word notes, commented copies, ZIP and Word export source parts |
| `review-output/` | Ten faculty-review deliverables and a finding index |
| `review-tools/` | Import, comment-generation, historical finding reconstruction and validation scripts |
| `db/`, `drizzle/` | Durable review-state schema and migration |
| `.github/workflows/` | Checks on pushes/PRs; configurable deployment to Cloudflare |
| `archives/sites-source-snapshot.zip` | Exact previous Sites source, retained for historical reference |

## Quick local start

Install Node.js 22.13+ and pnpm 11.25.0. From this folder:

```sh
pnpm install --frozen-lockfile
pnpm db:local
pnpm dev
```

Open http://127.0.0.1:5173. Reviewer authentication is bypassed **only in local development**. For optional local LLM access, copy `.dev.vars.example` to `.dev.vars`, then enter your own API key. Do not commit that file.

```sh
pnpm verify
python -m pip install -r review-tools/requirements.txt
python review-tools/verify_documents.py
```

## Project scope and approval workflow

1. Original notes: client folder “Lecture Notes (for Review)”.
2. AI proposes highlighted comments: “Lecture Notes (With Comments)”.
3. Professor accepts, revises or rejects suggestions and saves clean approved copies in “Lecture Notes (Revised)”.
4. Those approved revised documents become the Phase 1 student-learning source.
5. NBME question writing and question-bank generation belong to Phase 2.

The 53 findings are review proposals, not a certification that all other content is correct. Dashboard accept/reject and approval actions demonstrate the review workflow. The current demo composes approved content from the original paragraphs and accepted suggestions. **It does not yet import the professor's externally revised Box files.** Build that ingestion/versioning step before treating the system as the production student knowledge base.

## Deployment model

This export uses the existing React/TypeScript + Vinext/Vite stack, Cloudflare Workers and a Cloudflare D1 SQLite database. The frontend and APIs deploy together. Your own GitHub repository is the source of truth; your own Cloudflare account owns the runtime and database.

The export replaces the hosted demo's ChatGPT access gate with a private reviewer username/password gate that covers the dashboard, APIs and lecture downloads. Production fails closed until reviewer credentials are configured. This is a private reviewer demo, not yet a multi-user public learning platform.

The original demo is still at https://anatomy-review-lab.sairaghavendra179.chatgpt.site. GitHub deployments create a separate Cloudflare URL; they do not update that hosted demo automatically.

## Current limits

- Q&A uses keyword retrieval and needs a server-side OpenAI key for generated answers. No key or configured LLM service is bundled.
- Add revised-document ingestion, version-specific approval, user roles, retrieval evaluation and public student views before the wider launch.
- UB Box uploads/synchronization remain manual.
- Some dashboard totals are scoped to the ten-lecture demo; see maintenance instructions when expanding the course.
- Vinext is the current pinned beta framework. Keep the lockfile; review upgrades rather than changing framework and deployment architecture at the same time.
- This ZIP includes code, lecture material and artifacts. Runtime D1 rows, cloud-account credentials and external Box content are not Git files and are not bundled.

## Ownership

Keep this repository private because it contains the client's course materials. Lecture copyright remains with its owner. No permission to publicly redistribute those notes is implied. Third-party dependency and vendored stylesheet licenses remain applicable; see `vendor/`.
