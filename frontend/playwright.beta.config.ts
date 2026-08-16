import { defineConfig } from "@playwright/test"

export default defineConfig({
  testDir: "./e2e",
  testMatch: "beta-security.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
  use: {
    baseURL: process.env.NORA_BETA_WEB_URL || "https://localhost:8443",
    headless: true,
    ignoreHTTPSErrors: true,
    trace: "off",
    screenshot: "only-on-failure",
  },
})
