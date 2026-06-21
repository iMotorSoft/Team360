import { defineConfig, devices } from "@playwright/test";

const skipWebServer = process.env.PLAYWRIGHT_SKIP_WEBSERVER === "1";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report" }],
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:4321",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: skipWebServer ? undefined : [
    {
      command:
        "cd ../backend && AUTOMATION_DIAGNOSIS_REPOSITORY=memory uv run uvicorn ls_iMotorSoft_Srv01:app --host 127.0.0.1 --port 8000",
      port: 8000,
      timeout: 30_000,
      reuseExistingServer: true,
    },
    {
      command: "corepack pnpm dev",
      port: 4321,
      timeout: 30_000,
      reuseExistingServer: true,
    },
  ],
});
