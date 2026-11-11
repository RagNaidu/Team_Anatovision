# Setting up AnatoVision on a new machine

AnatoVision is a FastAPI backend (`app_api/`, with the logic in `src/`), a React front end (`frontend/`) and an older Streamlit app (`app/`).
This page gets a teammate from `git clone` to a running copy.

## What is not in the repository, and why

| Not in git | Why | How you get it |
|---|---|---|
| `data/` (everything) | Dr. Inglis's lecture notes and dissection guides (Word and PowerPoint files), the pictures extracted from the guides, the search index built from them, and the local databases (accounts, sessions, chats, quizzes, question bank, review decisions). The notes are course material that is not ours to publish, and the databases hold student data. | A data bundle from the project owner (step 3). |
| `.env` | Holds the BullsAI key. | Copy `.env.example` and add the key (step 2). |
| `reports/` (except `decisions_log.md` and `quiz_item_writing_checklist.md`) | Reports quote the lecture notes (fact-check results, evaluations, quiz drafts). | Part of the data bundle. |
| `node_modules/`, `frontend/dist/`, `.venv/`, `__pycache__/`, test output | Rebuilt on your machine. | Steps 1 to 3. |

Everything is excluded by `.gitignore`. Check with `git status` before committing: nothing under `data/` or `reports/` should ever show up.

## 0. Get this version

```bash
git fetch origin
git checkout ui-scroll-shell-and-voice-input
```

This branch has its own history. It is not based on `main`, which holds a different project (a Next.js app), so do not merge it into `main` without talking to the owner first.

Versions this was built and tested with: Python 3.12 (3.11 or newer should work), Node 20.19+ or 22+, Google Chrome (for the Playwright tests).

## 1. Front end only (no data, no key)

This is enough to see and work on every screen. The front end answers from built-in sample data ("mock mode").

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

Sign in as `student1` or `inglis` (the instructor) with any password. Mock mode is the default; it is switched by `VITE_USE_MOCK` in `frontend/.env.local` (see `frontend/.env.example`).

## 2. Backend

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt     # the first run also downloads the local embedding model (BAAI/bge-small-en-v1.5, about 130 MB)

cp .env.example .env
```

Open `.env` and fill in `BULLSAI_API_KEY` and `BULLSAI_BASE_URL` (UB's BullsAI gateway: ask the owner for a key, one per person, never commit it). `BULLSAI_MODEL` is already set to `google/gemma-4-31B-it`. The other settings in `.env.example` have working defaults. No other provider key is needed.

## 3. The data bundle

Ask the project owner for `anatovision-data.tar.gz`. It contains Dr. Inglis's course material, so send and keep it in private (UB OneDrive or a direct transfer), not in GitHub, a public chat or a shared drive link that anyone can open. Unpack it in the repository root:

```bash
tar -xzf anatovision-data.tar.gz     # creates data/ and reports/factcheck_all.json
```

The bundle holds the parsed notes (`data/processed/`), the search index (`data/index/`), the pictures and text extracted from the dissection guides, the OpenStax reference text, and the fact-check results the review queue reads. It leaves out accounts, sessions, chats, quizzes, the review-decision files and the original (very large) PowerPoint files. The app creates fresh, empty versions of the databases on first start.

**For the owner, to make the bundle** (run in the repository root):

```bash
tar -czf anatovision-data.tar.gz \
  --exclude='data/users.json' --exclude='*.db' --exclude='*.db-*' --exclude='data/archive' --exclude='data/staging_v2' \
  --exclude='data/web_cache' --exclude='data/raw/*.zip' --exclude='data/raw/dissection_guides' --exclude='data/raw/dissection_guides_revised' \
  --exclude='data/question_log.jsonl' --exclude='data/flags.jsonl' --exclude='data/verified_fixes.jsonl' --exclude='.DS_Store' \
  data reports/factcheck_all.json
```

About 275 MB. If someone needs to re-render the guide pictures or re-upload notes in the Notes manager, they also need the original files; ask the owner for those separately.

## 4. Run the whole thing

Two terminals, both from the repository root unless stated.

```bash
# terminal 1: the API (http://localhost:8000, docs at /api/docs)
source .venv/bin/activate
uvicorn app_api.main:app --port 8000
```

On its first start with an empty install, the API prints generated demo passwords for `inglis` (instructor), `student1` and `student2` **once**. Copy them from that terminal. (To choose your own, set `DEMO_PROFESSOR_PASSWORD` and `DEMO_STUDENT_PASSWORD` before the first start.) The first start also warms the search index and takes about 10 seconds.

```bash
# terminal 2: the front end, talking to the real API
cd frontend
echo "VITE_USE_MOCK=false" > .env.local
npm run dev                  # http://localhost:5173 (the dev server forwards /api to port 8000)
```

Student accounts only see the lectures and guides granted to them. Sign in as `inglis` to grant access (Access screen), or see `docs/api_dev.md` for the sandbox script that runs the API on throw-away accounts.

The older Streamlit app still runs too: `streamlit run app/main.py` (see `README.md`).

## 5. Tests

```bash
# backend (from the repository root, with the data bundle unpacked; about 2 minutes)
python -m pytest -q

# front end (from frontend/)
npm run build            # type-check and production build
npm run test:unit        # voice-input logic, node's built-in test runner
npm run test:e2e         # Playwright in mock mode; needs Google Chrome installed, starts its own dev server on port 5174
```

The backend tests use temporary copies for everything they write; they never change your `data/` files, and they need no BullsAI key and no network (checked on a fresh clone with the data bundle and no `.env`: 1,120 passed, 9 skipped). Tests that read the real notes and index need the data bundle; without it they are skipped or fail. The front-end tests do not need it.

## Things that are easy to get wrong

- Do not commit `.env`, anything under `data/`, or lecture notes in any format (`.docx`, `.doc`, `.pptx`, `.pdf`). `.gitignore` blocks them; do not override it with `git add -f`.
- Streamlit and the API read the same `data/` files; do not run two copies against one `data/` folder while testing something that writes.
- The Vite dev server does not pick up `.env.local` changes until you restart it.
