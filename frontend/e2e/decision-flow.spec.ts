import { readFile } from "node:fs/promises"

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

async function login(page: Page, user: User): Promise<void> {
  await page.goto("/login")
  await page.getByLabel("用户名").fill(user.username)
  await page.getByLabel("密码", { exact: true }).fill(user.password)
  await page.getByRole("button", { name: "登录" }).click()
  await expect(page).toHaveURL(/\/$/)
}

async function prepareProfileAndResume(page: Page): Promise<string> {
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
  return page.url().match(/\/resumes\/([0-9a-f-]+)/)![1]
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

test("M3 决策闭环：真实 Compose 主流程、刷新与重新登录恢复、双用户隔离", async ({ page }) => {
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

  await page.getByRole("button", { name: "退出登录" }).click()
  await registerAndLogin(page, newUser("m3-b"))
  await page.goto(`/analysis/${caseId}`)
  await expect(page.getByText("对象不存在或无权访问")).toBeVisible()
  await page.goto(`/reports/${reportId}`)
  await expect(page.getByText("对象不存在或无权访问")).toBeVisible()
  const userBSession = await page.evaluate(() => JSON.parse(sessionStorage.getItem("nora.auth.session") || "{}"))
  const foreignWrite = await page.request.post(`/api/reports/${reportId}/decision`, {
    headers: {
      Authorization: `Bearer ${userBSession.token}`,
      "Idempotency-Key": "m3-e2e-foreign-write",
    },
    data: { status: "apply", reason: null },
  })
  expect(foreignWrite.status()).toBe(404)

  await page.getByRole("button", { name: "退出登录" }).click()
  await login(page, userA)

  await page.goto(`/analysis/${caseId}`)
  await expect(page.getByRole("heading", { name: "确定性规则已执行" })).toBeVisible()
  await expect(page.getByText(`案例 ${caseId}`, { exact: false })).toBeVisible()
  const restoredRuleResults = page.getByRole("region", { name: "规则分析结果" })
  await expect(restoredRuleResults.getByText("满足", { exact: true }).first()).toBeVisible()
  await expect(restoredRuleResults.getByText("未知", { exact: true }).first()).toBeVisible()
  await expect(restoredRuleResults.getByText(/用户主档 v\d+/).first()).toBeVisible()
  await expect(restoredRuleResults.getByText(/岗位要求 v\d+/).first()).toBeVisible()

  await page.goto(`/reports/${reportId}`)
  await expect(page.getByRole("heading", { name: "报告 v1" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "暂不投递" })).toBeVisible()
  await expect(page.getByText("关键岗位要求尚未确认")).toBeVisible()
  await expect(page.getByText("报告 v1 · 简历 v1", { exact: false })).toBeVisible()
})

test("M4 投递闭环 Beta：材料、手工确认、恢复、隔离与无外部写", async ({ page }) => {
  const outsideRequests = new Set<string>()
  page.on("request", (request) => {
    const url = new URL(request.url())
    if (["http:", "https:"].includes(url.protocol) && !["localhost", "127.0.0.1"].includes(url.hostname)) {
      outsideRequests.add(`${request.method()} ${url.origin}${url.pathname}`)
    }
  })
  const userA = newUser("m4-variant-a")
  await registerAndLogin(page, userA)
  const resumeId = await prepareProfileAndResume(page)
  const jobId = await prepareJobRequirements(page)

  await page.goto(`/analysis/new?jobId=${jobId}`)
  await page.getByRole("button", { name: "开始分析" }).click()
  await expect(page).toHaveURL(/\/analysis\/[0-9a-f]{8}-/)
  await page.getByRole("button", { name: "生成报告" }).click()
  await expect(page).toHaveURL(/\/reports\/[0-9a-f]{8}-/)

  await page.getByRole("button", { name: "投递" }).click()
  await page.getByRole("button", { name: "确认决定" }).click()
  await expect(page.getByRole("heading", { name: "准备投递" })).toBeVisible()
  await page.getByRole("main").getByRole("link", { name: "定制简历" }).click()
  await expect(page).toHaveURL(new RegExp(`/resumes/${resumeId}/customize\\?decision=[0-9a-f-]+`))

  await expect(page.getByRole("heading", { name: "选择、编辑与排序" })).toBeVisible()
  await page.getByLabel("字段内容").first().fill("M4 定制用户")
  await page.getByRole("button", { name: "下移" }).first().click()
  await page.getByRole("button", { name: "创建不可变变体" }).click()
  await expect(page).toHaveURL(/\/resume-variants\/[0-9a-f]{8}-/)
  const variantId = page.url().match(/\/resume-variants\/([0-9a-f-]+)/)![1]
  await expect(page.getByRole("heading", { name: /M3 Python 工程师简历 · 定制版/ })).toBeVisible()
  await expect(page.getByText("M4 定制用户", { exact: true })).toBeVisible()

  await page.reload()
  await expect(page.getByRole("heading", { name: /M3 Python 工程师简历 · 定制版/ })).toBeVisible()
  await expect(page.getByText("M4 定制用户", { exact: true })).toBeVisible()
  await expect(page.getByText("版本已固定")).toBeVisible()

  await page.route(`**/api/resume-variants/${variantId}/pdf`, async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error_code: "artifact_storage_unavailable",
        error_category: "service_unavailable",
        message: "Artifact storage unavailable",
      }),
    })
  })
  await page.getByRole("button", { name: "生成 PDF" }).click()
  await expect(page.getByRole("alert")).toHaveText("PDF 存储暂时不可用，请重试")
  await expect(page.getByText("可用", { exact: true })).toHaveCount(0)
  await page.unroute(`**/api/resume-variants/${variantId}/pdf`)

  await page.getByRole("button", { name: "生成 PDF" }).click()
  await expect(page.getByText("可用", { exact: true })).toBeVisible()
  await expect(page.getByText(/weasyprint-69\.0/)).toBeVisible()
  const userASession = await page.evaluate(() => JSON.parse(sessionStorage.getItem("nora.auth.session") || "{}"))
  const pdfStatus = await page.request.get(`/api/resume-variants/${variantId}/pdf`, {
    headers: { Authorization: `Bearer ${userASession.token}` },
  })
  expect(pdfStatus.status()).toBe(200)
  const pdfId = (await pdfStatus.json()).id as string

  await page.reload()
  await expect(page.getByRole("button", { name: "预览" })).toBeVisible()
  await page.getByRole("button", { name: "预览" }).click()
  await expect(page.getByTitle("定制简历 PDF 预览")).toHaveAttribute("src", /^blob:/)

  const failedDownload = new RegExp(`/api/resume-pdfs/${pdfId}/content\\?download=true$`)
  await page.route(failedDownload, async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error_code: "artifact_storage_unavailable",
        error_category: "service_unavailable",
        message: "Artifact storage unavailable",
      }),
    })
  })
  await page.getByRole("button", { name: "下载" }).click()
  await expect(page.getByRole("alert")).toHaveText("PDF 存储暂时不可用，请重试")
  await page.unroute(failedDownload)

  const downloadPromise = page.waitForEvent("download")
  await page.getByRole("button", { name: "下载" }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe(`nora-resume-${pdfId}.pdf`)
  const downloadPath = await download.path()
  expect(downloadPath).not.toBeNull()
  expect((await readFile(downloadPath!)).subarray(0, 8).toString()).toBe("%PDF-1.7")

  const draftWrites: string[] = []
  page.on("request", (request) => {
    if (request.method() === "POST") draftWrites.push(new URL(request.url()).pathname)
  })
  await page.getByLabel("用户备注").fill("可在本周沟通")
  await page.getByRole("button", { name: "生成草稿" }).click()
  await expect(page).toHaveURL(/\/messages\/[0-9a-f]{8}-/)
  const draftId = page.url().match(/\/messages\/([0-9a-f-]+)/)![1]
  const editor = page.getByLabel("消息草稿内容")
  await expect(editor).toHaveValue(/M3 决策用户/)
  await expect(editor).toHaveValue(/可在本周沟通/)
  const editedText = `${await editor.inputValue()}\n\n期待您的回复。`
  await editor.fill(editedText)
  await page.getByRole("button", { name: "保存新版本" }).click()
  await expect(page.getByText("版本 2", { exact: false }).first()).toBeVisible()

  await page.reload()
  await expect(editor).toHaveValue(editedText)
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"])
  await page.getByRole("button", { name: "复制" }).click()
  await expect(page.getByRole("button", { name: "已复制" })).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(editedText)
  expect(draftWrites).toEqual([
    `/api/resume-variants/${variantId}/message-drafts`,
    `/api/message-drafts/${draftId}/revisions`,
  ])

  await page.goto(`/resume-variants/${variantId}`)
  await page.getByRole("link", { name: "创建投递记录" }).click()
  await expect(page).toHaveURL(/\/applications\/new\?variant=/)
  await page.getByRole("button", { name: "创建待确认记录" }).click()
  await expect(page).toHaveURL(/\/applications\/[0-9a-f]{8}-/)
  const applicationId = page.url().match(/\/applications\/([0-9a-f-]+)/)![1]
  await expect(page.getByRole("heading", { name: "待确认" })).toBeVisible()
  await expect(page.getByText("尚无状态转换")).toBeVisible()
  const plannedRecord = await page.request.get(`/api/application-records/${applicationId}`, {
    headers: { Authorization: `Bearer ${userASession.token}` },
  })
  expect(plannedRecord.status()).toBe(200)
  expect((await plannedRecord.json()).status).toBe("planned")

  await page.getByRole("button", { name: "已投递" }).click()
  await page.getByRole("combobox").selectOption("公司官网")
  await page.getByRole("button", { name: "确认已投递" }).click()
  await expect(page.getByRole("heading", { name: "已投递" })).toBeVisible()
  await page.getByRole("button", { name: "面试中" }).click()
  await page.getByRole("button", { name: "确认面试中" }).click()
  await expect(page.getByRole("heading", { name: "面试中" })).toBeVisible()
  await page.getByRole("link", { name: "记录面试" }).click()

  const interviewDate = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
  const localInterviewDate = new Date(
    interviewDate.getTime() - interviewDate.getTimezoneOffset() * 60_000,
  ).toISOString().slice(0, 16)
  await page.getByLabel("开始时间").fill(localInterviewDate)
  await page.getByLabel("会议链接").fill("https://meet.example.com/e2e-private")
  await page.getByLabel("备注（可选）").fill("E2E 私有面试备注")
  await page.getByRole("button", { name: "保存面试安排" }).click()
  await expect(page).toHaveURL(/\/interviews\/[0-9a-f]{8}-/)
  const interviewId = page.url().match(/\/interviews\/([0-9a-f-]+)/)![1]
  await expect(page.getByText("第 1 轮 · 线上", { exact: true })).toBeVisible()

  await page.locator(".interview-mode-field").getByRole("button", { name: "线下" }).click()
  await page.getByLabel("地点").fill("E2E 上海办公室")
  await page.getByLabel("轮次").fill("2")
  await page.getByRole("button", { name: "保存新版本" }).click()
  await expect(page.getByText("已保存为 v2")).toBeVisible()
  await page.reload()
  await expect(page.getByText("安排 v2")).toBeVisible()
  await expect(page.getByText("E2E 上海办公室")).toBeVisible()
  await expect(page.getByText("v1 · 第 1 轮 · 线上")).toBeVisible()

  await page.getByRole("button", { name: "退出登录" }).click()
  const userB = newUser("m4-variant-b")
  await registerAndLogin(page, userB)
  await page.goto(`/resume-variants/${variantId}`)
  await expect(page.getByText("对象不存在或无权访问")).toBeVisible()

  const userBSession = await page.evaluate(() => JSON.parse(sessionStorage.getItem("nora.auth.session") || "{}"))
  const foreignRead = await page.request.get(`/api/resume-variants/${variantId}`, {
    headers: { Authorization: `Bearer ${userBSession.token}` },
  })
  expect(foreignRead.status()).toBe(404)
  const foreignPdf = await page.request.get(`/api/resume-pdfs/${pdfId}`, {
    headers: { Authorization: `Bearer ${userBSession.token}` },
  })
  expect(foreignPdf.status()).toBe(404)
  const foreignPdfContent = await page.request.get(`/api/resume-pdfs/${pdfId}/content`, {
    headers: { Authorization: `Bearer ${userBSession.token}` },
  })
  expect(foreignPdfContent.status()).toBe(404)
  await page.goto(`/messages/${draftId}`)
  await expect(page.getByText("对象不存在或无权访问")).toBeVisible()
  const foreignDraft = await page.request.get(`/api/message-drafts/${draftId}`, {
    headers: { Authorization: `Bearer ${userBSession.token}` },
  })
  expect(foreignDraft.status()).toBe(404)
  const foreignDraftWrite = await page.request.post(`/api/message-drafts/${draftId}/revisions`, {
    headers: {
      Authorization: `Bearer ${userBSession.token}`,
      "Idempotency-Key": "m4-e2e-foreign-draft-write",
    },
    data: { base_version: 2, text: "foreign edit must stay invisible" },
  })
  expect(foreignDraftWrite.status()).toBe(404)
  const foreignPdfGenerate = await page.request.post(`/api/resume-variants/${variantId}/pdf`, {
    headers: { Authorization: `Bearer ${userBSession.token}` },
  })
  expect(foreignPdfGenerate.status()).toBe(404)
  await page.goto(`/applications/${applicationId}`)
  await expect(page.getByText("对象不存在或无权访问")).toBeVisible()
  const foreignApplication = await page.request.get(`/api/application-records/${applicationId}`, {
    headers: { Authorization: `Bearer ${userBSession.token}` },
  })
  expect(foreignApplication.status()).toBe(404)
  const foreignTransition = await page.request.post(
    `/api/application-records/${applicationId}/transitions`,
    {
      headers: {
        Authorization: `Bearer ${userBSession.token}`,
        "Idempotency-Key": "m4-e2e-foreign-application-write",
      },
      data: {
        base_version: 3,
        to_status: "offer_received",
        occurred_at: new Date().toISOString(),
        channel: null,
        note: null,
      },
    },
  )
  expect(foreignTransition.status()).toBe(404)
  await page.goto(`/interviews/${interviewId}`)
  await expect(page.getByText("对象不存在或无权访问")).toBeVisible()
  const foreignInterview = await page.request.get(`/api/interviews/${interviewId}`, {
    headers: { Authorization: `Bearer ${userBSession.token}` },
  })
  expect(foreignInterview.status()).toBe(404)
  const foreignInterviewWrite = await page.request.post(`/api/interviews/${interviewId}/versions`, {
    headers: {
      Authorization: `Bearer ${userBSession.token}`,
      "Idempotency-Key": "m4-e2e-foreign-interview-write",
    },
    data: {
      base_version: 2,
      starts_at: interviewDate.toISOString(),
      timezone: "Asia/Shanghai",
      mode: "phone",
      location: null,
      meeting_url: null,
      round_number: 3,
      note: null,
      status: "scheduled",
    },
  })
  expect(foreignInterviewWrite.status()).toBe(404)

  await page.getByRole("button", { name: "退出登录" }).click()
  await login(page, userA)
  await page.goto(`/resume-variants/${variantId}`)
  await expect(page.getByText("M4 定制用户", { exact: true })).toBeVisible()
  await expect(page.getByText("SHA-256", { exact: true })).toBeVisible()
  await expect(page.getByRole("link", { name: "打开 v2" })).toBeVisible()
  await page.goto(`/messages/${draftId}`)
  await expect(page.getByLabel("消息草稿内容")).toHaveValue(editedText)
  await expect(page.getByText("版本 2", { exact: false }).first()).toBeVisible()
  await page.goto(`/applications/${applicationId}`)
  await expect(page.getByRole("heading", { name: "面试中" })).toBeVisible()
  await expect(page.getByText("待确认 → 已投递")).toBeVisible()
  await expect(page.getByText("已投递 → 面试中")).toBeVisible()
  await page.goto(`/interviews/${interviewId}`)
  await expect(page.getByText("安排 v2")).toBeVisible()
  await expect(page.getByText("E2E 上海办公室")).toBeVisible()
  expect([...outsideRequests]).toEqual([])
})

test("M4 公司情报：录入、固定报告版本、追加版本与双用户隔离", async ({ page }) => {
  const userA = newUser("m4-company-a")
  await registerAndLogin(page, userA)
  await prepareProfileAndResume(page)
  const jobId = await prepareJobRequirements(page)

  await page.goto(`/analysis/new?jobId=${jobId}`)
  await page.getByRole("button", { name: "开始分析" }).click()
  await expect(page).toHaveURL(/\/analysis\/[0-9a-f]{8}-/)
  await page.getByRole("button", { name: "生成报告" }).click()
  await expect(page).toHaveURL(/\/reports\/[0-9a-f]{8}-/)
  const reportId = page.url().match(/\/reports\/([0-9a-f-]+)/)![1]

  await page.getByRole("link", { name: "录入并绑定" }).click()
  await expect(page).toHaveURL(new RegExp(`/companies/new\\?report=${reportId}`))
  await page.getByLabel("公司名称").fill("M4 Company Corp")
  await page.getByLabel("公司规模状态").selectOption("confirmed")
  await page.locator(".company-value-status input").nth(0).fill("100-499")
  await page.getByLabel("行业状态").selectOption("confirmed")
  await page.locator(".company-value-status input").nth(1).fill("Software")
  await page.getByLabel("来源摘要状态").selectOption("unconfirmed")
  await page.locator(".company-value-status textarea").fill("公开工程成长路径清晰")
  await page.getByRole("button", { name: "网页来源" }).click()
  await page.getByLabel("来源 URL").fill("https://example.com/company")
  await page.getByLabel("来源原文或人工记录").fill("Company profile and public engineering notes.")
  await page.getByLabel("发布时间").fill("2026-08-01T09:00")
  await page.getByRole("button", { name: "保存公司情报" }).click()

  await expect(page).toHaveURL(new RegExp(`/reports/${reportId}$`))
  await expect(page.getByRole("heading", { name: "M4 Company Corp" })).toBeVisible()
  await expect(page.getByText("100-499", { exact: false })).toBeVisible()
  const fixedLink = page.getByRole("link", { name: /查看固定的 CompanySnapshot v1/ })
  const fixedHref = await fixedLink.getAttribute("href")
  const snapshotId = fixedHref?.match(/\/companies\/([0-9a-f-]+)/)?.[1]
  expect(snapshotId).toBeTruthy()

  await fixedLink.click()
  await expect(page).toHaveURL(new RegExp(`/companies/${snapshotId}\\?version=1$`))
  await page.getByRole("button", { name: "新增版本" }).click()
  await page.getByLabel("公司规模状态").selectOption("unconfirmed")
  await page.locator(".company-value-status input").nth(0).fill("500-999")
  await page.getByLabel("来源 URL").fill("https://example.com/company/update")
  await page.getByLabel("来源原文或人工记录").fill("Updated public company profile.")
  await page.getByRole("button", { name: "创建新版本" }).click()
  await expect(page.getByText("当前查看 v2 · 最新 v2")).toBeVisible()
  await expect(page.getByText("500-999", { exact: false })).toBeVisible()

  await page.goto(`/reports/${reportId}`)
  await expect(page.getByText("CompanySnapshot · v1")).toBeVisible()
  await expect(page.getByText("100-499", { exact: false })).toBeVisible()
  await expect(page.getByText("500-999", { exact: false })).toHaveCount(0)
  await page.reload()
  await expect(page.getByText("CompanySnapshot · v1")).toBeVisible()

  await page.getByRole("button", { name: "退出登录" }).click()
  await registerAndLogin(page, newUser("m4-company-b"))
  await page.goto(`/companies/${snapshotId}`)
  await expect(page.getByText("对象不存在或无权访问")).toBeVisible()
  await page.goto(`/reports/${reportId}`)
  await expect(page.getByText("对象不存在或无权访问")).toBeVisible()

  await page.getByRole("button", { name: "退出登录" }).click()
  await login(page, userA)
  await page.goto(`/reports/${reportId}`)
  await expect(page.getByText("CompanySnapshot · v1")).toBeVisible()
  await expect(page.getByText("100-499", { exact: false })).toBeVisible()
})
