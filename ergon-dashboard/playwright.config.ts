import { defineConfig, devices } from "@playwright/test";

const isLive = process.env.PLAYWRIGHT_LIVE === "1";
const port = isLive ? "3000" : "3101";
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "on",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: isLive
    ? undefined
    : {
        command: "pnpm dev:test",
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        cwd: __dirname,
        env: {
          NODE_ENV: "development",
          PORT: port,
          ENABLE_TEST_HARNESS: "1",
          ERGON_API_BASE_URL: process.env.ERGON_API_BASE_URL ?? "http://127.0.0.1:9000",
        },
      },
});
