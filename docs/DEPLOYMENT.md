# Run locally and deploy from GitHub

This standalone export uses Cloudflare Workers and D1. It is not a Vercel static export: the review APIs and durable database need the Worker runtime.

## 1. Install and run locally

Install Node.js 22.13 or newer, pnpm 11.25.0, and Git. Use the same versions in local development and CI. One installation option after installing Node:

```sh
npm install -g pnpm@11.25.0
pnpm install --frozen-lockfile
pnpm db:local
pnpm dev
```

Open http://127.0.0.1:5173. The local D1 database is in ignored `.wrangler/` state. No Cloudflare login is required for this local setup. Keep the placeholder database ID until you create your actual production database.

For optional local LLM use, copy `.dev.vars.example` to `.dev.vars` and set `OPENAI_API_KEY`. Q&A still requires resolved findings and an approved lecture. The API key stays on the server. Don't put keys in frontend code or GitHub files.

## 2. Create your production database

Create/sign in to your own Cloudflare account, then:

```sh
pnpm exec wrangler login
pnpm exec wrangler d1 create anatomy-review-db
```

The command returns a real database ID. Replace the placeholder `database_id` in `wrangler.json` with that ID. Keep binding `DB` and `migrations_dir` set to `drizzle`. Commit this configuration change. The database ID is configuration, not an API secret.

Production uses a new database and starts without the existing hosted demo's review decisions. Git does not move database records automatically. Do not reuse unrelated databases. Keep originals and findings synchronized when moving records between deployments.

## 3. First deployment

```sh
node scripts/check-deployment.mjs
pnpm deploy
```

This runs type checks, auth tests, build, remote migrations and deployment. Wrangler returns your production URL. At first the site shows **Reviewer access has not been configured** (503), so the lecture files are not exposed.

Configure reviewer access interactively:

```sh
pnpm exec wrangler secret put REVIEW_USERNAME --config wrangler.json
pnpm exec wrangler secret put REVIEW_PASSWORD --config wrangler.json
```

Use an ASCII username (no colon) and a long random ASCII password. The browser prompts for these credentials when you open the URL. Close the browser session to clear cached Basic authentication. Do not use this shared reviewer credential as the future public/student identity system.

Optional, only when you are ready to enable the answer service:

```sh
pnpm exec wrangler secret put OPENAI_API_KEY --config wrangler.json
```

The API currently defaults to model `gpt-4.1`. You can set `OPENAI_MODEL` as a server environment variable. Choose and evaluate a model before changing it. Secrets are stored in Cloudflare, not in this repository. Without an API key the interface clearly reports that generation is unavailable; it does not fabricate an answer.

## 4. Automatic GitHub deployments

In your GitHub repository, open **Settings → Secrets and variables → Actions**.

Add repository secrets:

| Secret | Value |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | An API token scoped to the target Cloudflare account with Workers Scripts edit and D1 edit access |
| `CLOUDFLARE_ACCOUNT_ID` | Your Cloudflare account ID |

Cloudflare's **Edit Cloudflare Workers** API-token template is a starting point; ensure your token can apply D1 migrations too. Keep the token out of files and terminal transcripts.

Create a GitHub environment named `production` if you want deployment approvals/protection rules. The deployment job uses this environment.

Add repository **variable** `ENABLE_CLOUDFLARE_DEPLOY` with value `true` after the database configuration and first deployment are ready. Deployment stays disabled on pushes until this variable is set. You can also trigger **Actions → Deploy Cloudflare → Run workflow** manually.

On a push to `main`, the deployment job:

1. Installs locked dependencies.
2. Rejects a placeholder database configuration.
3. Runs checks/tests and builds the Worker plus frontend.
4. Applies unapplied D1 migrations.
5. Deploys that build to your Cloudflare account.

The PR validation workflow checks the project without production credentials. It does not deploy pull requests or migrate the production database. Pushes use one serialized production deployment queue.

## 5. Future edits

```sh
# In your local checkout, with a clean working tree:
git pull
# Make changes, then:
pnpm verify
git add .
git commit -m "Describe the change"
git push
```

Check the GitHub Actions result. Open the new deployment and exercise the feature you changed. A passing build does not replace browser testing of newly changed UI interactions.

## Database backups and migrations

Create the ignored `backups` folder, then export the live database:

```sh
mkdir backups
pnpm db:backup
```

Keep that backup somewhere durable outside this Git repository; the SQL may contain reviewer notes. D1 rows are stored independently of code. If you change the schema, add a new migration rather than editing an already-applied one. Back up before schema changes. Redeploying older code does not automatically undo database migrations.

## Other hosts and the existing demo

Your exported app depends on Cloudflare bindings. Moving to Vercel, Render or another runtime requires a database/runtime adapter; simply uploading the files there is insufficient. The exact previously deployed Sites source is in `archives/sites-source-snapshot.zip` for reference. Its `.openai/hosting.json` is managed-demo configuration, not your new Cloudflare setup.

## Official references checked for this export

- Cloudflare Vite plugin: https://developers.cloudflare.com/workers/vite-plugin/get-started/
- Cloudflare GitHub Actions: https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/
- D1 commands: https://developers.cloudflare.com/workers/wrangler/commands/d1/
- Worker-first asset routing: https://developers.cloudflare.com/workers/static-assets/routing/worker-script/
- Vinext project: https://github.com/cloudflare/vinext
