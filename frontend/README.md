# AnatoVision front end

React + TypeScript single-page app for the AnatoVision anatomy lab assistant. It talks to the FastAPI backend in `../app_api` through one file, `src/lib/api.ts`. The contract is [`../docs/api_contract.md`](../docs/api_contract.md) (single source of truth; `src/lib/types.ts` mirrors it).

Stack: Vite, React 18, TypeScript, Tailwind 3, shadcn-style components (Radix primitives, `src/components/ui`), lucide-react, react-markdown + remark-gfm, framer-motion, recharts (plain, no shadcn chart), react-router.

## Run

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
npm run build          # type-check + production build into dist/
npm run test:e2e       # Playwright smoke test (mock mode, uses the installed Google Chrome)
```

### Mock mode or the real API

| `.env.local` | Meaning |
|---|---|
| `VITE_USE_MOCK=true` (default) | every call is answered by `src/lib/mock.ts` after a 600 to 1,200 ms delay. Users: `inglis` (instructor) and `student1`; any password works. No backend needed. |
| `VITE_USE_MOCK=false` | calls the real API with `credentials: "include"` |
| `VITE_API_URL=` (empty, default) | same origin: the Vite dev server proxies `/api` to `http://localhost:8000`, so the httpOnly session cookie works and no CORS is needed |
| `VITE_API_URL=http://localhost:8000` | call the backend directly. It allows exactly `http://localhost:5173` with credentials, and only while `APP_ENV=development` |

Backend (from the repo root): `.venv/bin/uvicorn app_api.main:app --port 8000`. For a live check that must not touch real accounts, chats, quizzes or logs, run `SANDBOX_DIR=/some/folder .venv/bin/python scripts/api_sandbox.py --port 8000` (see `docs/api_dev.md`). In production serve the built `dist/` and `/api` from one origin.

## Where things are

```
src/lib/        types.ts (contract), api.ts (every endpoint), mock.ts, citations.ts (markers -> chips), utils.ts
src/state/      auth (session + preview from GET /api/auth/me), data (scope + chat list)
src/components/ AppShell, Sidebar, ChatList, PreviewBar, ProgressRow (the waiting indicator), ui/ (button, dialog, popover, sheet, ...)
src/pages/      ask/ (chat, composer, source panel), guide/, quiz/, admin/
e2e/            Playwright smoke test
```

## Behaviour worth knowing

- **Waiting indicator.** While an answer is prepared there is a quiet row of three dots (CSS, 1.4 s). Its chevron and stage list appear only when the backend really offers `GET /api/ask/status/{request_id}`; the page sends a client-made `request_id` with `POST /api/ask` and shows only the stage words the backend reports ("Searching your notes", "Reading the sources", "Writing the answer", "Checking the answer"). Seconds beside finished stages are measured in the browser between the moments a stage was first seen. If the endpoint is missing, only the dots show.
- **Body type.** The composer row has a quiet "Body type" control. It is sent as `body_type` ("more fat, average muscle, large build") only once chosen, and remembered in `localStorage`.
- **Session.** The cookie is httpOnly, so a reload keeps you signed in; `/api/auth/me` also says whether an instructor is previewing, so the preview bar survives a reload. A 401 on any other call returns to the login page.
- **Errors.** Every non-2xx body is `{error}`; that message is shown, never a raw status. Network failures show a plain "Can't reach the server" line.
- **Guide.** Station index is 0-based in the API and URL (`/guide/class-17/2` is "Station 3 of 12"). A picture-only station shows "See slide N in your lab guide" and no Check box. A failed check (502) shows its message in the feedback area with Try again. The conversational Guide of the Streamlit app is not in the API.
- **Quiz.** One build per user at a time (409 is shown). Keys, explanations and evidence arrive only after submit; evidence lines named by `spans` are highlighted.
- **Instructor.** Outside a preview the student screens return 403, so the instructor shell never calls them. A student report can only be dismissed; "Verify fix" needs fix text.
- Motion follows `prefers-reduced-motion` (framer-motion `MotionConfig` plus CSS). Colours are tokens in `src/index.css`, with a dark theme that keeps the same hues (user menu: Appearance).

Screenshots from the last walk-through: `../reports/ui_screenshots/react/` (mock) and `.../real/` (real API).
