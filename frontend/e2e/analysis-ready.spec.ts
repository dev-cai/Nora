import { expect, test } from "@playwright/test"

/**
 * M2 分析就绪输入 E2E：覆盖真实浏览器下的注册、主档与简历、JD 文本输入、
 * 岗位要求确认（版本追加）、刷新恢复与双用户隔离。
 *
 * 截图 OCR 与受控链接预览的前端页面不在 M2 范围；其 API 链路由集成测试
 * （#136/#137）以受控 Adapter 覆盖，本用例聚焦浏览器可到达的 M2 输入主流程。
 */

function newUser(prefix: string): { username: string; email: string; password: string } {
  const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
  const username = `${prefix}-${suffix}`
  return { username, email: `${username}@example.com`, password: "e2e-password-123" }
}

async function registerAndLogin(page: import("@playwright/test").Page, user: { username: string; email: string; password: string }): Promise<void> {
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
  await expect(page.getByRole("button", { name: "退出登录" })).toBeVisible()
}

async function setupConfirmedProfile(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/profile")
  await page.getByLabel("姓名").fill("M2F 用户")
  await page.getByLabel("当前所在地").fill("上海")
  // 基本信息区前两个 ConfirmationSelect 对应姓名与所在地
  await page.locator(".fact-field").nth(0).locator("select").selectOption("confirmed")
  await page.locator(".fact-field").nth(1).locator("select").selectOption("confirmed")
  await page.getByRole("button", { name: "保存主档新版本" }).click()
  await expect(page.getByText(/主档第 \d+ 版已保存/)).toBeVisible()
}

async function publishResume(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/resumes/new")
  await page.getByLabel("简历标题").fill("M2F 后端工程师简历")
  await page.getByRole("button", { name: "发布不可变版本" }).click()
  await expect(page).toHaveURL(/\/resumes\/[0-9a-f]{8}-/)
}

async function createJob(page: import("@playwright/test").Page): Promise<string> {
  await page.goto("/jobs/new")
  await page.getByLabel("职位名称").fill("M2F 后端工程师")
  await page.getByLabel("公司名称").fill("M2F Corp")
  await page.getByLabel("工作地点").fill("上海 / 远程")
  await page.getByLabel("岗位描述").fill("E2E 分析就绪输入集成验证岗位：要求 Python、三年以上经验、本科、上海、混合办公。")
  await page.getByRole("button", { name: "保存岗位快照" }).click()
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f]{8}-/)
  return page.url().match(/\/jobs\/([0-9a-f]{8}-[0-9a-f-]+)/)![1]
}

test("分析就绪输入：主档简历、JD 文本、岗位要求确认、版本、刷新恢复与隔离", async ({ page }) => {
  const userA = newUser("m2f-a")
  await registerAndLogin(page, userA)
  await setupConfirmedProfile(page)
  await publishResume(page)
  const jobId = await createJob(page)

  // 岗位详情 → 进入岗位要求确认
  await page.goto(`/jobs/${jobId}/requirements`)
  await expect(page.getByRole("heading", { name: "确认岗位要求" })).toBeVisible()

  // 技能要求：添加 Python 并确认
  const skillsSection = page.locator(".form-section").filter({ hasText: "技能要求" })
  await skillsSection.getByRole("button", { name: "添加技能" }).click()
  await skillsSection.locator(".skill-row input").fill("Python")
  await skillsSection.locator(".field-meta select").selectOption("confirmed")

  // 最低经验年限：先确认状态启用输入，再填值
  const experienceSection = page.locator(".form-section").filter({ hasText: "最低经验年限" })
  await experienceSection.locator(".field-meta select").selectOption("confirmed")
  await experienceSection.locator('input[type="number"]').fill("3")

  // 学历要求
  const degreeSection = page.locator(".form-section").filter({ hasText: "学历要求" })
  await degreeSection.locator(".field-meta select").selectOption("confirmed")
  await degreeSection.locator(".fact-field input").fill("本科")

  // 地点要求
  const locationSection = page.locator(".form-section").filter({ hasText: "地点要求" })
  await locationSection.locator(".field-meta select").selectOption("confirmed")
  await locationSection.locator(".fact-field input").fill("上海")

  // 工作方式
  const workModeSection = page.locator(".form-section").filter({ hasText: "工作方式" })
  await workModeSection.locator(".field-meta select").selectOption("confirmed")
  await workModeSection.locator(".fact-field select").selectOption("hybrid")

  // 保存 v1 → 岗位要求已确认
  await page.getByRole("button", { name: "保存为新版本" }).click()
  await expect(page.getByText("已创建岗位要求快照")).toBeVisible()
  await expect(page.getByText("岗位要求已确认（5/5）")).toBeVisible()

  // 修改技能 → 保存 v2
  await skillsSection.getByRole("button", { name: "添加技能" }).click()
  await skillsSection.locator(".skill-row input").nth(1).fill("FastAPI")
  await page.getByRole("button", { name: "保存为新版本" }).click()
  await expect(page.getByText("已创建新版本 v2")).toBeVisible()
  await expect(page.locator(".version-list li").first()).toContainText("v2")

  // 刷新后恢复：表单载入最新版本，历史保留 v2
  await page.reload()
  await expect(page.getByRole("heading", { name: "确认岗位要求" })).toBeVisible()
  await expect(page.locator(".version-list li").first()).toContainText("v2")
  await expect(skillsSection.locator(".skill-row input")).toHaveCount(2)
  await expect(page.getByText("岗位要求已确认（5/5）")).toBeVisible()

  // 双用户隔离：用户 B 无法访问用户 A 的岗位要求
  const userB = newUser("m2f-b")
  await page.getByRole("button", { name: "退出登录" }).click()
  await registerAndLogin(page, userB)
  await page.goto(`/jobs/${jobId}/requirements`)
  await expect(page.getByText("无法加载岗位要求")).toBeVisible()
  await expect(page.getByText("对象不存在或无权访问")).toBeVisible()
})
