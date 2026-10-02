# Export validation

The standalone export passed:

- TypeScript checking and production Worker/frontend build.
- Four reviewer-gate tests: missing configuration, missing/malformed/incorrect credentials, valid credentials, and explicit local-only bypass.
- Local production-runtime requests: protected dashboard/API/lecture downloads, successful server rendering, commented Word download, persisted reviewer note, unresolved-finding approval rejection, and Q&A gating without approved notes.
- All ten original-versus-commented Word text comparisons, native comment anchors/counts, exact original finding passages and ZIP lecture count.
- Portable lecture importer: all original text and paragraph indexes preserved in an isolated import.
- Frozen dependency lockfile validation and GitHub workflow YAML parsing.

A fresh live deployment from your GitHub repository has not been performed: it requires your repository and Cloudflare account configuration. Browser interaction QA and live LLM evaluation remain separate checks. No real credentials or runtime database contents are included.

The hosted-demo source snapshot is from commit `181d0b61d43daec2563529795d4589c26dde216f`. The active standalone source adds portable deployment configuration and reviewer access protection; it is not the same deployment target as the hosted demo.
