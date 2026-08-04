import { defineConfig } from "@playwright/test"

/**
 * 浏览器级基础 E2E（M2 门禁）。
 *
 * 前置：compose 栈已就绪（web :5173 + api :8000 + db），且已执行
 * `docker compose exec api alembic upgrade head`。运行命令：`npm run e2e`。
 *
 * CI 通过 .github/workflows/e2e.yml 起 compose 栈后执行本配置。
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.NORA_WEB_URL || "http://localhost:5173",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
})
