import { defineConfig } from "@playwright/test";

// E2E specs expect a running stack: backend on :8000 and frontend on :3000 (docker compose up, or the dev servers).
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
