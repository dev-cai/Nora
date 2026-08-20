import { expect, test, type Page } from "@playwright/test"

test.use({ trace: "off", screenshot: "off", video: "off" })

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

async function token(page: Page): Promise<string> {
  return page.evaluate(() => {
    const session = JSON.parse(sessionStorage.getItem("nora.auth.session") || "{}") as { token?: string }
    return session.token || ""
  })
}

async function prepareProfileAndResume(page: Page): Promise<string> {
  await page.goto("/profile")
  await page.getByLabel("姓名").fill("M5 Agent 用户")
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
  await page.getByLabel("简历标题").fill("M5 Agent Python 简历")
  await page.getByRole("button", { name: "发布不可变版本" }).click()
  await expect(page).toHaveURL(/\/resumes\/[0-9a-f]{8}-/)
  return page.url().match(/\/resumes\/([0-9a-f-]+)/)![1]
}

async function prepareJob(page: Page): Promise<string> {
  await page.goto("/jobs/new")
  await page.getByLabel("职位名称").fill("M5 Agentic RAG 工程师")
  await page.getByLabel("公司名称").fill("M5 E2E Corp")
  await page.getByLabel("工作地点").fill("上海")
  await page.getByLabel("岗位描述").fill("要求 Python、RAG 和面试准备能力。")
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

async function createReport(page: Page, jobId: string): Promise<string> {
  await page.goto(`/analysis/new?jobId=${jobId}`)
  await page.getByRole("button", { name: "开始分析" }).click()
  await expect(page).toHaveURL(/\/analysis\/[0-9a-f]{8}-/)
  await expect(page.getByRole("heading", { name: "确定性规则已执行" })).toBeVisible()
  await page.getByRole("button", { name: "生成报告" }).click()
  await expect(page).toHaveURL(/\/reports\/[0-9a-f]{8}-/)
  return page.url().match(/\/reports\/([0-9a-f-]+)/)![1]
}

async function seedKnowledgeSource(page: Page, auth: string): Promise<string> {
  const artifact = await page.request.post("/api/artifacts", {
    headers: { Authorization: `Bearer ${auth}`, "Idempotency-Key": `m5-source-${Date.now()}` },
    multipart: {
      file: {
        name: "m5-interview-notes.md",
        mimeType: "text/plain",
        buffer: Buffer.from("面试准备：Python、RAG、系统设计与项目取舍都需要准备可验证证据。"),
      },
      kind: "source",
    },
  })
  expect(artifact.status()).toBe(201)
  const artifactBody = await artifact.json() as { id: string }
  const source = await page.request.post("/api/sources", {
    headers: { Authorization: `Bearer ${auth}` },
    data: {
      artifact_id: artifactBody.id,
      source_kind: "manual",
      acquisition_method: "e2e_fixture",
      license_note: "synthetic_fixture",
      locator: "m5-agentic-rag-e2e",
    },
  })
  expect(source.status()).toBe(201)
  const sourceBody = await source.json() as { id: string }
  const indexed = await page.request.post(`/api/knowledge/sources/${sourceBody.id}/index`, {
    headers: { Authorization: `Bearer ${auth}` },
  })
  expect(indexed.status()).toBe(200)
  return sourceBody.id
}

async function createInterview(page: Page, reportId: string): Promise<string> {
  await page.getByRole("button", { name: "投递" }).click()
  await page.getByRole("button", { name: "确认决定" }).click()
  await expect(page.getByRole("heading", { name: "准备投递" })).toBeVisible()
  await page.getByRole("main").getByRole("link", { name: "定制简历" }).click()
  await expect(page).toHaveURL(/\/resumes\/[0-9a-f-]+\/customize\?decision=/)
  await page.getByLabel("字段内容").first().fill("M5 Agent 用户")
  await page.getByRole("button", { name: "创建不可变变体" }).click()
  await expect(page).toHaveURL(/\/resume-variants\/[0-9a-f]{8}-/)
  await page.getByRole("link", { name: "创建投递记录" }).click()
  await page.getByRole("button", { name: "创建待确认记录" }).click()
  await expect(page).toHaveURL(/\/applications\/[0-9a-f]{8}-/)
  await page.getByRole("button", { name: "已投递" }).click()
  await page.getByRole("combobox").selectOption("公司官网")
  await page.getByRole("button", { name: "确认已投递" }).click()
  await page.getByRole("button", { name: "面试中" }).click()
  await page.getByRole("button", { name: "确认面试中" }).click()
  await page.getByRole("link", { name: "记录面试" }).click()

  const date = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
  await page.getByLabel("开始时间").fill(localDate)
  await page.getByLabel("会议链接").fill("https://meet.example.com/m5-private")
  await page.getByLabel("备注（可选）").fill(`报告 ${reportId} 的面试安排`)
  await page.getByRole("button", { name: "保存面试安排" }).click()
  await expect(page).toHaveURL(/\/interviews\/[0-9a-f]{8}-/)
  return page.url().match(/\/interviews\/([0-9a-f-]+)/)![1]
}

test("M5 Agentic RAG 求职闭环：模型降级、检索、审批恢复、记忆回流与隔离", async ({ page }) => {
  const outsideRequests = new Set<string>()
  page.on("request", (request) => {
    const url = new URL(request.url())
    if (["http:", "https:"].includes(url.protocol) && !["localhost", "127.0.0.1"].includes(url.hostname)) {
      outsideRequests.add(`${request.method()} ${url.origin}${url.pathname}`)
    }
  })

  const userA = newUser("m5-agent-a")
  await registerAndLogin(page, userA)
  const resumeId = await prepareProfileAndResume(page)
  const jobId = await prepareJob(page)
  const reportId = await createReport(page, jobId)

  await page.route(`**/api/reports/${reportId}/job-fit-analysis`, async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          error_code: "model_provider_unavailable",
          error_category: "service_unavailable",
          message: "Model provider unavailable",
        }),
      })
    } else await route.continue()
  })
  await page.getByRole("button", { name: "生成 AI 分析" }).click()
  await expect(page.getByRole("alert")).toContainText("AI 分析服务暂时不可用")
  await expect(page.getByRole("heading", { name: "报告 v1" })).toBeVisible()
  await page.unroute(`**/api/reports/${reportId}/job-fit-analysis`)
  await page.getByRole("button", { name: "生成 AI 分析" }).click()
  await expect(page.getByText("AI 分析 v1", { exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "事实" })).toBeVisible()
  const jobFit = page.locator(".job-fit-analysis")
  await expect(jobFit.getByText("模型推断", { exact: true }).first()).toBeVisible()
  await expect(jobFit.getByText("建议", { exact: true }).first()).toBeVisible()
  await expect(jobFit.getByText("未知", { exact: true }).first()).toBeVisible()
  expect(await jobFit.locator(".citation-list span").count()).toBeGreaterThan(0)

  const authA = await token(page)
  const sourceId = await seedKnowledgeSource(page, authA)
  const interviewId = await createInterview(page, reportId)

  await page.getByRole("button", { name: "刷新生成准备计划" }).click()
  await expect(page.getByText("准备计划 v1")).toBeVisible()
  expect(await page.getByText("打开证据").count()).toBeGreaterThan(0)

  await page.getByLabel("面试问题").fill("请解释 Python 服务的系统设计取舍")
  await page.getByLabel("我的回答").fill("我回答了 API、RAG 检索和版本化证据，但系统设计细节不足。")
  await page.getByLabel("自评").fill("需要补强系统设计")
  await page.getByLabel("卡点（逗号分隔）").fill("系统设计")
  await page.getByLabel("面试结果").fill("待跟进")
  await page.getByRole("button", { name: "生成待确认候选" }).click()
  const candidate = page.locator(".review-candidates .preparation-topic").first()
  await expect(candidate.getByRole("button", { name: "确认进入记忆" })).toBeVisible()
  await candidate.getByRole("button", { name: "确认进入记忆" }).click()
  await expect(candidate.getByRole("button", { name: "撤销确认" })).toBeVisible()

  const reviews = await page.request.get(`/api/interviews/${interviewId}/reviews`, {
    headers: { Authorization: `Bearer ${authA}` },
  })
  expect(reviews.status()).toBe(200)
  const reviewBody = await reviews.json() as {
    candidates: Array<{ id: string; status: string; source_id: string | null }>
  }[]
  const confirmedCandidate = reviewBody.flatMap((review) => review.candidates).find((item) => item.status === "confirmed")
  const confirmedSourceId = confirmedCandidate?.source_id
  expect(confirmedSourceId).toBeTruthy()

  await page.getByRole("button", { name: "刷新生成准备计划" }).click()
  await expect(page.getByText("准备计划 v2")).toBeVisible()
  const preparation = await page.request.get(`/api/interviews/${interviewId}/preparation`, {
    headers: { Authorization: `Bearer ${authA}` },
  })
  expect(preparation.status()).toBe(200)
  const preparationBody = await preparation.json() as { version: number; citations: Array<{ source_id: string }> }
  expect(preparationBody.citations.some((item) => item.source_id === confirmedSourceId)).toBe(true)

  const beforeInterview = await page.request.get(`/api/interviews/${interviewId}`, {
    headers: { Authorization: `Bearer ${authA}` },
  })
  const beforeVersion = (await beforeInterview.json() as { version: number }).version
  const fitRunResponse = await page.request.post("/api/agent-runs", {
    headers: { Authorization: `Bearer ${authA}` },
    data: { user_goal: "分析这个岗位是否适合我", job_posting_id: jobId },
  })
  expect(fitRunResponse.status()).toBe(202)
  const fitWaiting = await fitRunResponse.json() as {
    id: string
    approval: { id: string } | null
  }
  expect(fitWaiting.approval).not.toBeNull()
  const fitApproval = await page.request.post(
    `/api/agent-runs/${fitWaiting.id}/approvals/${fitWaiting.approval!.id}/approve`,
    { headers: { Authorization: `Bearer ${authA}` } },
  )
  expect(fitApproval.status()).toBe(200)
  const fitCompleted = await fitApproval.json() as {
    status: string
    tool_calls: Array<{ tool_name: string; status: string }>
  }
  expect(fitCompleted.status).toBe("completed")
  expect(fitCompleted.tool_calls.some((call) => call.tool_name === "analyze_job_fit" && call.status === "succeeded")).toBe(true)

  const run = await page.request.post("/api/agent-runs", {
    headers: { Authorization: `Bearer ${authA}` },
    data: {
      user_goal: "准备面试并检索 Python 系统设计证据",
      interview_case_id: interviewId,
      source_id: sourceId,
      job_posting_id: jobId,
    },
  })
  expect(run.status()).toBe(202)
  const waiting = await run.json() as {
    id: string
    status: string
    approval: { id: string } | null
    checkpoint: { state: Record<string, unknown> } | null
  }
  expect(waiting.status).toBe("waiting_approval")
  expect(waiting.approval).not.toBeNull()
  expect(waiting.checkpoint?.state).not.toHaveProperty("chain_of_thought")
  const beforeApproval = await page.request.get(`/api/interviews/${interviewId}/preparation`, {
    headers: { Authorization: `Bearer ${authA}` },
  })
  expect(beforeApproval.status()).toBe(200)
  expect((await beforeApproval.json() as { version: number }).version).toBe(preparationBody.version)

  const approval = await page.request.post(
    `/api/agent-runs/${waiting.id}/approvals/${waiting.approval!.id}/approve`,
    { headers: { Authorization: `Bearer ${authA}` } },
  )
  expect(approval.status()).toBe(200)
  const completed = await approval.json() as { status: string; approval: unknown; tool_calls: Array<{ tool_name: string; status: string }> }
  expect(completed.status).toBe("completed")
  expect(completed.approval).toBeNull()
  expect(completed.tool_calls.some((call) => call.tool_name === "retrieve_knowledge" && call.status === "succeeded")).toBe(true)
  expect(completed.tool_calls.some((call) => call.tool_name === "prepare_interview" && call.status === "succeeded")).toBe(true)
  const afterApproval = await page.request.get(`/api/interviews/${interviewId}/preparation`, {
    headers: { Authorization: `Bearer ${authA}` },
  })
  expect(afterApproval.status()).toBe(200)
  expect((await afterApproval.json() as { version: number }).version).toBe(preparationBody.version + 1)

  const afterInterview = await page.request.get(`/api/interviews/${interviewId}`, {
    headers: { Authorization: `Bearer ${authA}` },
  })
  expect((await afterInterview.json() as { version: number }).version).toBe(beforeVersion)
  const deleted = await page.request.delete(`/api/agent-runs/${waiting.id}/checkpoint`, {
    headers: { Authorization: `Bearer ${authA}` },
  })
  expect(deleted.status()).toBe(204)
  const afterDelete = await page.request.get(`/api/agent-runs/${waiting.id}`, {
    headers: { Authorization: `Bearer ${authA}` },
  })
  expect((await afterDelete.json() as { checkpoint: unknown }).checkpoint).toBeNull()

  await page.getByRole("button", { name: "退出登录" }).click()
  const userB = newUser("m5-agent-b")
  await registerAndLogin(page, userB)
  const authB = await token(page)
  for (const path of [
    `/api/agent-runs/${waiting.id}`,
    `/api/interviews/${interviewId}`,
    `/api/sources/${sourceId}`,
  ]) {
    const response = await page.request.get(path, { headers: { Authorization: `Bearer ${authB}` } })
    expect(response.status(), path).toBe(404)
  }
  const foreignKnowledge = await page.request.post("/api/knowledge/ask", {
    headers: { Authorization: `Bearer ${authB}` },
    data: { query: "Python 系统设计", source_id: sourceId, limit: 5 },
  })
  expect(foreignKnowledge.status()).toBe(200)
  expect((await foreignKnowledge.json() as { citations: unknown[] }).citations).toEqual([])
  const foreignCandidate = await page.request.post(
    `/api/interviews/memory-candidates/${confirmedCandidate!.id}/revoke`,
    { headers: { Authorization: `Bearer ${authB}` } },
  )
  expect(foreignCandidate.status()).toBe(404)
  await page.goto(`/interviews/${interviewId}`)
  await expect(page.getByText("对象不存在或无权访问")).toBeVisible()

  await page.getByRole("button", { name: "退出登录" }).click()
  await login(page, userA)
  await page.goto(`/interviews/${interviewId}`)
  await expect(page.getByText("准备计划 v3")).toBeVisible()
  await expect(page.getByRole("button", { name: "撤销确认" })).toBeVisible()
  expect([...outsideRequests]).toEqual([])
  void resumeId
})
