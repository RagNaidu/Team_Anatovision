import { defineConfig } from "@playwright/test";

// Smoke test against the mock front end (no backend needed). Uses the installed Google Chrome, so no browser download.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:5174", channel: "chrome", viewport: { width: 1440, height: 900 } },
  webServer: {
    command: "VITE_USE_MOCK=true npx vite --host 127.0.0.1 --port 5174 --strictPort",
    url: "http://127.0.0.1:5174",
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
