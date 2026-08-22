import { expect, test, type Page } from "@playwright/test"

const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

async function registerAndLogin(page: Page, name: string): Promise<void> {
  const username = `jd-${name}-${suffix}`
  await page.goto("/register")
  await page.getByLabel("用户名").fill(username)
  await page.getByLabel("邮箱").fill(`${username}@example.com`)
  await page.getByLabel("密码", { exact: true }).fill("e2e-password-123")
  await page.getByLabel("确认密码").fill("e2e-password-123")
  await page.getByRole("button", { name: "创建账号" }).click()
  await expect(page.getByRole("heading", { name: "登录工作台" })).toBeVisible()
  await page.getByLabel("用户名").fill(username)
  await page.getByLabel("密码", { exact: true }).fill("e2e-password-123")
  await page.getByRole("button", { name: "登录" }).click()
  await expect(page).toHaveURL(/\/$/)
}

test("JD 文本进入 AI 草稿并一次确认导入", async ({ page }) => {
  await registerAndLogin(page, "text")
  await page.goto("/jobs/new")
  await page.getByLabel("岗位描述").fill("Nora 后端工程师\n需要 Python 服务开发经验。")
  await page.getByRole("button", { name: "AI 自动识别" }).click()

  await expect(page.getByText("结构化岗位要求")).toBeVisible()
  await expect(page.getByLabel("职位名称")).toHaveValue("后端工程师")
  await expect(page.getByLabel("公司名称")).toHaveValue("Nora")
  await page.getByRole("button", { name: "确认导入岗位" }).click()
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]{36}$/)
})

test("JD 链接进入同一 AI 草稿和确认流程", async ({ page }) => {
  await registerAndLogin(page, "url")
  await page.goto("/jobs/new")
  await page.route("**/api/job-postings/fetch", async (route) => {
    expect(JSON.parse(route.request().postData() ?? "{}")).toMatchObject({ url: "https://example.com/" })
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        jd_text: "Example JD fixture\n需要 Python 服务开发经验。",
        source_url: "https://example.com/",
        kind: "url",
      }),
    })
  })
  await page.getByRole("button", { name: "链接" }).click()
  await page.getByLabel("岗位链接").fill("https://example.com/")
  await page.getByRole("button", { name: "提取正文" }).click()

  await expect(page.getByLabel("岗位描述")).not.toHaveValue("")
  await expect(page.getByText("结构化岗位要求")).toBeVisible()
  await page.getByRole("button", { name: "确认导入岗位" }).click()
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]{36}$/)
})
