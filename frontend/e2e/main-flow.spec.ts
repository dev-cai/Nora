import { expect, test } from "@playwright/test"

/**
 * M2 浏览器级基础 E2E：覆盖真实浏览器下的注册/登录、会话保持、岗位、
 * 主档、简历列表与登出路径。运行前提见 playwright.config.ts。
 */
const suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
const username = `e2e-${suffix}`
const email = `${username}@example.com`
const password = "e2e-password-123"

test("基础主流程：注册、登录、会话保持、岗位、主档、简历与登出", async ({ page }) => {
  // 未登录访问受保护路由 → 重定向到登录页
  await page.goto("/jobs")
  await expect(page).toHaveURL(/\/login/)

  // 注册 → 跳转登录页（等待登录组件挂载完成，避免懒加载竞态）
  await page.goto("/register")
  await page.getByLabel("用户名").fill(username)
  await page.getByLabel("邮箱").fill(email)
  await page.getByLabel("密码", { exact: true }).fill(password)
  await page.getByLabel("确认密码").fill(password)
  await page.getByRole("button", { name: "创建账号" }).click()
  await expect(page.getByRole("heading", { name: "登录工作台" })).toBeVisible()

  // 登录 → 进入工作台
  await page.getByLabel("用户名").fill(username)
  await page.getByLabel("密码", { exact: true }).fill(password)
  await page.getByRole("button", { name: "登录" }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole("button", { name: "退出登录" })).toBeVisible()

  // 刷新后仍保持登录（sessionStorage + /auth/me 恢复）
  await page.reload()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole("button", { name: "退出登录" })).toBeVisible()

  // 创建岗位 → 进入岗位详情
  await page.goto("/jobs/new")
  await page.getByLabel("职位名称").fill("E2E 后端工程师")
  await page.getByLabel("公司名称").fill("E2E Corp")
  await page.getByLabel("工作地点").fill("上海 / 远程")
  await page.getByLabel("岗位描述").fill("E2E 浏览器级基础流程集成验证岗位。")
  await page.getByRole("button", { name: "保存岗位快照" }).click()
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f]{8}-/)

  // 主档：填写姓名与所在地并保存
  await page.goto("/profile")
  await page.getByLabel("姓名").fill("E2E 用户")
  await page.getByLabel("当前所在地").fill("上海")
  await page.getByRole("button", { name: "保存主档新版本" }).click()
  await expect(page.getByText(/主档第 \d+ 版已保存/)).toBeVisible()

  // 简历列表页可访问（顶栏标题与页面标题同名，取首个）
  await page.goto("/resumes")
  await expect(page.getByRole("heading", { name: "简历版本" }).first()).toBeVisible()

  // 登出 → 跳转登录页
  await page.getByRole("button", { name: "退出登录" }).click()
  await expect(page).toHaveURL(/\/login/)

  // 登出后访问受保护路由 → 再次重定向到登录页
  await page.goto("/jobs")
  await expect(page).toHaveURL(/\/login/)
})
