import { expect, test, type Page } from "@playwright/test"

type User = { username: string; email: string; password: string }

function newUser(prefix: string): User {
  const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
  const username = `${prefix}-${suffix}`
  return { username, email: `${username}@example.com`, password: "e2e-password-123" }
}

async function registerAndLogin(page: Page, user: User): Promise<void> {
  await page.goto("/register")
  await page.getByLabel("用户名").fill(user.username)
  await page.getByLabel("邮箱").fill(user.email)
  await page.getByLabel("密码", { exact: true }).fill(user.password)
  await page.getByLabel("确认密码").fill(user.password)
  await page.getByRole("button", { name: "创建账号" }).click()
  await expect(page.getByRole("heading", { name: "登录工作台" })).toBeVisible()
  await page.getByLabel("用户名").fill(user.username)
  await page.getByLabel("密码", { exact: true }).fill(user.password)
  await page.getByRole("button", { name: "登录" }).click()
  await expect(page).toHaveURL(/\/$/)
}

async function prepareProfileAndResume(page: Page): Promise<void> {
  await page.goto("/profile")
  await page.getByLabel("姓名").fill("M3 决策用户")
  await page.getByLabel("当前所在地").fill("上海")
  await page.locator(".fact-field").nth(0).locator("select").selectOption("confirmed")
  await page.locator(".fact-field").nth(1).locator("select").selectOption("confirmed")
  await page.getByRole("button", { name: "添加技能" }).click()
  const skill = page.locator(".skill-row").last()
  await skill.getByLabel("技能名称").fill("Python")
  await skill.locator("select").first().selectOption("confirmed")
  await page.getByRole("button", { name: "保存主档新版本" }).click()
  await expect(page.getByText(/主档第 \d+ 版已保存/)).toBeVisible()

  await page.goto("/resumes/new")
  await page.getByLabel("简历标题").fill("M3 Python 工程师简历")
  await page.getByRole("button", { name: "发布不可变版本" }).click()
  await expect(page).toHaveURL(/\/resumes\/[0-9a-f]{8}-/)
}

async function prepareJobRequirements(page: Page): Promise<string> {
  await page.goto("/jobs/new")
  await page.getByLabel("职位名称").fill("M3 Python 工程师")
  await page.getByLabel("公司名称").fill("M3 E2E Corp")
  await page.getByLabel("工作地点").fill("上海")
  await page.getByLabel("岗位描述").fill("要求 Python；其余要求留待确认，用于验证 unknown。")
  await page.getByRole("button", { name: "保存岗位快照" }).click()
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f]{8}-/)
  const jobId = page.url().match(/\/jobs\/([0-9a-f-]+)/)![1]

  await page.goto(`/jobs/${jobId}/requirements`)
  const skills = page.locator(".form-section").filter({ hasText: "技能要求" })
  await skills.getByRole("button", { name: "添加技能" }).click()
  await skills.locator(".skill-row input").fill("Python")
  await skills.locator(".field-meta select").selectOption("confirmed")
  await page.getByRole("button", { name: "保存为新版本" }).click()
  await expect(page.getByText("已创建岗位要求快照")).toBeVisible()
  return jobId
}

test("M3 决策闭环：真实 Compose 主流程、刷新恢复、决定与双用户隔离", async ({ page }) => {
  const userA = newUser("m3-a")
  await registerAndLogin(page, userA)
  await prepareProfileAndResume(page)
  const jobId = await prepareJobRequirements(page)

  await page.goto(`/analysis/new?jobId=${jobId}`)
  await expect(page.getByRole("heading", { name: "发起适配分析" })).toBeVisible()
  await expect(page.getByRole("button", { name: "开始分析" })).toBeEnabled()
  await page.getByRole("button", { name: "开始分析" }).click()
  await expect(page).toHaveURL(/\/analysis\/[0-9a-f]{8}-/)
  const caseId = page.url().match(/\/analysis\/([0-9a-f-]+)/)![1]

  await expect(page.getByRole("heading", { name: "确定性规则已执行" })).toBeVisible()
  const ruleResults = page.getByRole("region", { name: "规则分析结果" })
  await expect(ruleResults.getByText("满足", { exact: true }).first()).toBeVisible()
  await expect(ruleResults.getByText("未知", { exact: true }).first()).toBeVisible()
  await page.getByRole("button", { name: "生成报告" }).click()
  await expect(page).toHaveURL(/\/reports\/[0-9a-f]{8}-/)
  const reportId = page.url().match(/\/reports\/([0-9a-f-]+)/)![1]

  await expect(page.getByRole("heading", { name: "报告 v1" })).toBeVisible()
  await expect(page.getByRole("region", { name: "报告结果汇总" })).toContainText("满足")
  await expect(page.getByRole("heading", { name: "未知项" })).toBeVisible()
  await page.reload()
  await expect(page.getByRole("heading", { name: "报告 v1" })).toBeVisible()

  await page.getByRole("button", { name: "不投" }).click()
  await page.getByRole("textbox", { name: "不投原因" }).fill("关键岗位要求尚未确认")
  await page.getByRole("button", { name: "确认决定" }).click()
  await expect(page.getByRole("heading", { name: "暂不投递" })).toBeVisible()
  await page.reload()
  await expect(page.getByRole("heading", { name: "暂不投递" })).toBeVisible()
  await expect(page.getByText("报告 v1 · 简历 v1", { exact: false })).toBeVisible()

  const session = await page.evaluate(() => JSON.parse(sessionStorage.getItem("nora.auth.session") || "{}"))
  const authorization = { Authorization: `Bearer ${session.token}` }
  const replay = await page.request.post(`/api/reports/${reportId}/decision`, {
    headers: { ...authorization, "Idempotency-Key": "m3-e2e-replay" },
    data: { status: "skip", reason: "关键岗位要求尚未确认" },
  })
  expect(replay.status()).toBe(200)
  const conflict = await page.request.post(`/api/reports/${reportId}/decision`, {
    headers: { ...authorization, "Idempotency-Key": "m3-e2e-conflict" },
    data: { status: "apply", reason: null },
  })
  expect(conflict.status()).toBe(409)
  expect((await conflict.json()).error_code).toBe("application_decision_conflict")
  const invalid = await page.request.post(`/api/reports/${reportId}/decision`, {
    headers: { ...authorization, "Idempotency-Key": "m3-e2e-invalid" },
    data: { status: "skip", reason: "" },
  })
  expect(invalid.status()).toBe(422)

  await page.getByRole("button", { name: "退出登录" }).click()
  await registerAndLogin(page, newUser("m3-b"))
  await page.goto(`/analysis/${caseId}`)
  await expect(page.getByText("对象不存在或无权访问")).toBeVisible()
  await page.goto(`/reports/${reportId}`)
  await expect(page.getByText("对象不存在或无权访问")).toBeVisible()
})

test("报告读取失败时保留稳定的 401、503 与网络错误界面", async ({ page }) => {
  await registerAndLogin(page, newUser("m3-errors"))

  await page.route("**/api/reports/network-failure", (route) => route.abort("connectionrefused"))
  await page.goto("/reports/network-failure")
  await expect(page.getByText("无法连接 Nora 服务，请检查网络后重试")).toBeVisible()

  await page.route("**/api/reports/service-unavailable", (route) => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ error_code: "database_unavailable" }),
  }))
  await page.goto("/reports/service-unavailable")
  await expect(page.getByText("服务暂时不可用，请稍后重试")).toBeVisible()

  await page.route("**/api/reports/unauthorized", (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify({ error_code: "authentication_required" }),
  }))
  await page.goto("/reports/unauthorized")
  await expect(page).toHaveURL(/\/login/)
})
