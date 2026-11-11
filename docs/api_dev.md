# AnatoVision JSON API: running it and wiring a front end

The contract is [api_contract.md](api_contract.md) (single source of truth). Machine-readable: [openapi.json](openapi.json). One example response per endpoint: [api_examples.json](api_examples.json). Live docs while the server runs: http://localhost:8000/api/docs.

## Run

```
.venv/bin/uvicorn app_api.main:app --port 8000          # add --reload while developing
```

The first start warms the search index and the embedding model in the background (about 10 s); a request that arrives sooner waits for it. The Streamlit app is unchanged and still runs with `.venv/bin/streamlit run app/main.py`; both use the same data files (accounts, chats, quizzes, flags), so do not run a live check against real data: use `scripts/api_sandbox.py` (below).

Regenerate the documents after changing a model or an endpoint (a test fails if they are stale):

```
.venv/bin/python scripts/export_openapi.py
.venv/bin/python scripts/build_api_examples.py
```

## Vite proxy (development)

Everything is same-origin from the browser's point of view, so the cookie works and no CORS is needed:

```ts
// vite.config.ts
export default defineConfig({
  server: { port: 5173, proxy: { "/api": { target: "http://localhost:8000", changeOrigin: false } } },
});
```

Call `fetch("/api/...", { credentials: "same-origin" })` (the default). Leave `changeOrigin` false so the `Origin`/`Host` pair still matches. If the front end instead calls `http://localhost:8000` directly from `http://localhost:5173`, the API allows exactly that origin with credentials (CORS), only while `APP_ENV=development` (the default), and you must send `credentials: "include"`. In production, serve the built front end and `/api` from one origin, set `APP_ENV=production` (CORS off) and `API_COOKIE_SECURE=1` (behind HTTPS).

## Accounts and sessions

- Accounts are the existing scrypt users in `data/users.json` (roles `professor` and `student` there; the API says `instructor` and `student`). The first start of an empty install prints generated demo passwords once.
- `POST /api/auth/login` sets one cookie, `anatovision_session`: httpOnly, SameSite=Lax, 12 hours from login. The server keeps only a hash of it in `data/api_sessions.db`, so a page reload and a server restart both keep the user signed in.
- Grants are read from `data/users.json` on every request, so the instructor's change applies at once.
- Not production security: no single sign-on, no CSRF token (SameSite=Lax plus an Origin check on writes), login throttling is in memory. Real use needs UB single sign-on.

## Settings (environment)

| Variable | Default | Meaning |
|---|---|---|
| `APP_ENV` | `development` | CORS for `http://localhost:5173` only while `development` |
| `API_COOKIE_SECURE` | `0` | `1` marks the cookie Secure (HTTPS) |
| `LOGIN_IP_MAX` | `20` | failed logins per address per 5 minutes before 429 |
| `ANATOVISION_API_SESSIONS_PATH` | `data/api_sessions.db` | session database |
| `HELPER_CACHE_SECONDS` | `120` | identical follow-up rewrites and reranks within this many seconds are not repeated (`0` = off) |
| `FAST_BRIEF_FIX` | `on` | `off` = always regenerate a brief answer whose closing line is wrong (slower) |
| `API_TIMING_LOG` | unset | a file path: one JSON line of stage timings per question (the sandbox sets it; never sent to clients) |
| the usual | | `BULLSAI_*`, `WEB_FALLBACK`, `WEB_ALLOW_WIKIPEDIA`, `RERANK`, `CHAT_RETENTION_DAYS` as in `.env.example` |

## Live check without touching real data

```
SANDBOX_DIR=/tmp/anatovision-sandbox .venv/bin/python scripts/api_sandbox.py --port 8000
```

Accounts, chats, quizzes, sessions, the question log, flags, fixes and the web cache live in `SANDBOX_DIR`; the index, the notes and the BullsAI key are the real ones (read only). Users: `student` (every lecture and guide), `nogrants`, `instructor`; the password is in `SANDBOX_DIR/PASSWORD.txt`.

## What the API is, and is not

It wraps `service.ask_for_student`, `student_view`, `chat_store`, `guide_slides`, `quiz.service`, `review`, `usage` and `auth`; retrieval, prompts, safety rules, answer logic and quiz logic are not changed. Every answer a student receives is built from the student-safe view (`src/student_view.py`): no fact-check text, scores, cost or model name. The conversational Guide (`guide_chat`) of the Streamlit app is not exposed; the contract's Guide is the station check.

## Faster answers and progress (Step D)

Time per question follows the length of the model's answer; see `reports/build_status.md` for the measurements. To show progress without streaming text, send a `request_id` with `POST /api/ask` and poll `GET /api/ask/status/{request_id}` once a second: it returns only `searching`, `reading`, `writing`, `checking` or `done`. The answer arrives whole in the POST response after the student-safe layer. Measure with `scripts/api_timing.py` against the sandbox server.
