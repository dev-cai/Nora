import { execFileSync } from "node:child_process"

import { expect, test, type Page } from "@playwright/test"

function requiredEnvironment(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`${name} is required`)
  return value
}

async function login(page: Page, username: string, loginPassword: string): Promise<void> {
  await page.goto("/login")
  await page.getByLabel("用户名").fill(username)
  await page.getByLabel("密码", { exact: true }).fill(loginPassword)
  await page.getByRole("button", { name: "登录" }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole("region", { name: "工作台概览" })).toBeVisible()
}

function recoverOwner(): void {
  const composeFile = requiredEnvironment("BETA_E2E_COMPOSE_FILE")
  const environmentFile = requiredEnvironment("BETA_E2E_ENV_FILE")
  execFileSync(
    "docker",
    [
      "compose",
      "--env-file",
      environmentFile,
      "-f",
      composeFile,
      "exec",
      "-T",
      "api",
      "python",
      "-m",
      "app.apps.identity_management",
      "recover-owner",
      "--request-id",
      "beta-e2e-recovery",
      "--password-file",
      "/run/secrets/owner_recovery_password",
    ],
    { stdio: "ignore" },
  )
}

test("M4 Beta 生产认证：受控开户、恢复、撤销、限额与 Origin 边界", async ({ page }) => {
  const username = requiredEnvironment("BETA_E2E_OWNER_USERNAME")
  const password = requiredEnvironment("BETA_E2E_OWNER_PASSWORD")
  const recoveryPassword = requiredEnvironment("BETA_E2E_OWNER_RECOVERY_PASSWORD")
  const registerPage = await page.goto("/register")
  expect(registerPage).not.toBeNull()
  const pageHeaders = registerPage?.headers() || {}
  expect(pageHeaders["strict-transport-security"]).toContain("max-age=31536000")
  expect(pageHeaders["content-security-policy"]).toBe(
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-src blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
  )
  expect(pageHeaders["x-content-type-options"]).toBe("nosniff")
  expect(pageHeaders["x-frame-options"]).toBe("DENY")
  expect(pageHeaders["referrer-policy"]).toBe("no-referrer")
  await expect(page.getByRole("heading", { name: "页面不存在" })).toBeVisible()
  await expect(page.getByRole("link", { name: "创建账号" })).toHaveCount(0)

  const hiddenRegistration = await page.request.post("/api/auth/register", {
    headers: { Origin: "https://localhost:8443" },
    data: { username: "public-user", email: "public@example.invalid", password: "password-123" },
  })
  expect(hiddenRegistration.status()).toBe(404)
  expect((await hiddenRegistration.json()).error_code).toBe("entity_not_found")
  expect(hiddenRegistration.headers()["x-nora-web-proxy"]).toBe("true")
  expect(hiddenRegistration.headers()["strict-transport-security"]).toContain("max-age=31536000")

  const live = await page.request.get("/api/live")
  expect(live.status()).toBe(200)
  expect(await live.json()).toEqual({ status: "live" })
  expect(live.headers()["x-nora-web-proxy"]).toBe("true")

  await login(page, username, password)
  const originalSession = await page.evaluate(() => ({
    local: localStorage.getItem("nora.auth.session"),
    session: sessionStorage.getItem("nora.auth.session"),
  }))
  expect(originalSession.local).toBeNull()
  expect(originalSession.session).not.toBeNull()
  expect(page.url()).not.toContain("token")

  await page.reload()
  await expect(page.getByRole("region", { name: "工作台概览" })).toBeVisible()
  const oldToken = await page.evaluate(() => JSON.parse(
    sessionStorage.getItem("nora.auth.session") || "{}",
  ).token as string)

  recoverOwner()
  const revoked = await page.request.get("/api/auth/me", {
    headers: { Authorization: `Bearer ${oldToken}` },
  })
  expect(revoked.status()).toBe(401)
  await page.reload()
  await expect(page).toHaveURL(/\/login$/)
  expect(await page.evaluate(() => sessionStorage.getItem("nora.auth.session"))).toBeNull()

  await login(page, username, recoveryPassword)
  await page.getByRole("button", { name: "退出登录" }).click()
  await expect(page).toHaveURL(/\/login$/)
  expect(await page.evaluate(() => sessionStorage.getItem("nora.auth.session"))).toBeNull()

  const deniedOrigin = await page.request.post("/api/auth/login", {
    headers: { Origin: "https://attacker.example" },
    data: { username, password: recoveryPassword },
  })
  expect(deniedOrigin.status()).toBe(403)
  expect((await deniedOrigin.json()).error_code).toBe("origin_not_allowed")
  expect(deniedOrigin.headers()["access-control-allow-origin"]).toBeUndefined()

  for (let attempt = 0; attempt < 5; attempt += 1) {
    const failed = await page.request.post("/api/auth/login", {
      headers: {
        Origin: "https://localhost:8443",
        "X-Forwarded-For": `198.51.100.${attempt + 1}`,
        "X-Forwarded-Proto": "http",
      },
      data: { username: "rate-limited-browser", password: "wrong-password" },
    })
    expect(failed.status()).toBe(401)
  }
  const limited = await page.request.post("/api/auth/login", {
    headers: {
      Origin: "https://localhost:8443",
      "X-Forwarded-For": "203.0.113.99",
      "X-Forwarded-Proto": "http",
    },
    data: { username: "rate-limited-browser", password: "wrong-password" },
  })
  expect(limited.status()).toBe(429)
  expect((await limited.json()).error_code).toBe("authentication_rate_limited")
  expect(Number(limited.headers()["retry-after"])).toBeGreaterThan(0)

  await page.goto("/login")
  await page.getByLabel("用户名").fill("rate-limited-browser")
  await page.getByLabel("密码", { exact: true }).fill("wrong-password")
  await page.getByRole("button", { name: "登录" }).click()
  await expect(page.getByRole("alert")).toHaveText("登录尝试过于频繁，请稍后重试")
})
