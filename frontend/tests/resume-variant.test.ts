import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { createMemoryHistory, createRouter } from "vue-router"

import { ApiError, api } from "@/api/client"
import type { ResumePdf, ResumeVariant, ResumeVersion, TemplateDefinition } from "@/api/types"
import { resumeBlocks, templateAllows, templateRequires } from "@/features/resume-variant"
import { useVariantsStore } from "@/stores/variants"
import ResumeCustomizeView from "@/views/ResumeCustomizeView.vue"
import ResumeVariantDetailView from "@/views/ResumeVariantDetailView.vue"

const resume: ResumeVersion = {
  id: "resume-1", owner_id: "alice", version: 2, candidate_profile_id: "profile-1", profile_version: 3,
  title: "后端工程师", published_at: "2026-08-13T00:00:00Z",
  content: {
    basic_information: { display_name: "Alice", current_location: "上海" },
    experiences: [{ id: "exp-1", company: "Nora", responsibilities: ["API", "测试"] }],
    education: [], skills: [{ id: "skill-1", name: "Python", years: 5 }],
  },
}

const template: TemplateDefinition = {
  id: "template-1", version: 1, name: "清晰单栏", page_size: "a4", density: "standard", accent: "neutral",
  section_order: ["basic_information", "experiences", "education", "skills"],
  allowed_fields: ["basic_information.*", "experiences.*.*", "skills.*.*"],
  required_fields: ["basic_information.display_name"], definition_hash: "a".repeat(64), published_at: "2026-08-13T00:00:00Z",
}

const variant: ResumeVariant = {
  id: "variant-1", version: 1, application_decision_id: "decision-1", decision_case_id: "case-1",
  job_posting_id: "job-1", job_posting_version: 2, job_requirement_snapshot_id: "requirements-1", job_requirement_snapshot_version: 3,
  resume_version_id: "resume-1", resume_version: 2, template_id: "template-1", template_version: 1,
  title: "后端工程师 · 定制版", blocks: [{ source_path: "basic_information.display_name", label: "姓名", value: "Alice" }],
  generator_version: "m4-resume-variant-v1", content_fingerprint: "b".repeat(64), created_at: "2026-08-13T00:00:00Z",
}

const pdf: ResumePdf = {
  id: "pdf-1", version: 1, resume_variant_id: "variant-1", resume_variant_version: 1,
  template_id: "template-1", template_version: 1, template_definition_hash: "a".repeat(64),
  variant_content_fingerprint: "b".repeat(64), renderer_version: "weasyprint-69.0",
  font_set_version: "noto-cjk-v1", locale: "zh-CN", timezone: "UTC",
  generation_identity: "c".repeat(64), status: "available", artifact_id: "artifact-1",
  artifact_version: 1, artifact_sha256: "d".repeat(64), artifact_size_bytes: 1024,
  created_at: "2026-08-14T00:00:00Z", updated_at: "2026-08-14T00:00:00Z",
}

const stubs = { AppShell: { template: "<main><slot /></main>" }, StatePanel: { template: "<div data-state />" } }

describe("resume variants", () => {
  beforeEach(() => { setActivePinia(createPinia()) })
  afterEach(() => { vi.restoreAllMocks() })

  it("flattens stable source paths and joins scalar arrays into one editable block", () => {
    expect(resumeBlocks(resume)).toEqual([
      { source_path: "basic_information.display_name", label: "姓名", value: "Alice" },
      { source_path: "basic_information.current_location", label: "所在地", value: "上海" },
      { source_path: "experiences.exp-1.company", label: "公司", value: "Nora" },
      { source_path: "experiences.exp-1.responsibilities", label: "职责", value: "API、测试" },
      { source_path: "skills.skill-1.name", label: "技能", value: "Python" },
      { source_path: "skills.skill-1.years", label: "年限", value: "5" },
    ])
    expect(templateAllows(template, "skills.skill-1.name")).toBe(true)
    expect(templateAllows(template, "preferences.target_roles")).toBe(false)
    expect(templateRequires(template, "basic_information.display_name")).toBe(true)
  })

  it("retains the idempotency key after failure and resets it after success", async () => {
    const randomUUID = vi.spyOn(crypto, "randomUUID").mockReturnValueOnce("00000000-0000-4000-8000-000000000001").mockReturnValueOnce("00000000-0000-4000-8000-000000000002")
    const create = vi.spyOn(api, "createResumeVariant")
      .mockRejectedValueOnce(new ApiError("暂时失败"))
      .mockResolvedValueOnce(variant)
      .mockResolvedValueOnce({ ...variant, id: "variant-2" })
    const store = useVariantsStore()
    const input = { application_decision_id: "decision-1", template_id: "template-1", template_version: 1, title: "定制", blocks: variant.blocks }

    await expect(store.createVariant(input)).rejects.toThrow("暂时失败")
    await expect(store.createVariant(input)).resolves.toBe(variant)
    await store.createVariant(input)

    expect(create.mock.calls.map((call) => call[1])).toEqual([
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000002",
    ])
    expect(randomUUID).toHaveBeenCalledTimes(2)
  })

  it("selects, edits, reorders and creates a variant", async () => {
    vi.spyOn(api, "getResume").mockResolvedValue(resume)
    vi.spyOn(api, "listTemplates").mockResolvedValue([template])
    const create = vi.spyOn(api, "createResumeVariant").mockResolvedValue(variant)
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: "/resumes/:id/customize", component: ResumeCustomizeView },
      { path: "/resume-variants/:id", name: "resume-variant-detail", component: { template: "<div />" } },
      { path: "/reports/:id", name: "report-detail", component: { template: "<div />" } },
    ] })
    await router.push("/resumes/resume-1/customize?decision=decision-1")
    const wrapper = mount(ResumeCustomizeView, { global: { plugins: [createPinia(), router], stubs } })
    await flushPromises()

    const editable = wrapper.findAll("textarea")
    await editable[2]!.setValue("负责稳定 API")
    await wrapper.findAll('button[aria-label="下移"]')[0]!.trigger("click")
    await wrapper.get("form").trigger("submit")
    await flushPromises()

    expect(create).toHaveBeenCalledOnce()
    const payload = create.mock.calls[0]![0]
    expect(payload.application_decision_id).toBe("decision-1")
    expect(payload.blocks[0]!.source_path).toBe("basic_information.current_location")
    expect(payload.blocks.find((block) => block.source_path === "experiences.exp-1.company")?.value).toBe("负责稳定 API")
    expect(router.currentRoute.value.params.id).toBe("variant-1")
  })

  it("recovers immutable variant and exact template after a direct detail load", async () => {
    const getVariant = vi.spyOn(api, "getResumeVariant").mockResolvedValue(variant)
    const getTemplate = vi.spyOn(api, "getTemplate").mockResolvedValue(template)
    const getPdf = vi.spyOn(api, "getLatestResumePdf").mockResolvedValue(pdf)
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: "/templates", component: { template: "<div />" } },
      { path: "/resume-variants/:id", component: ResumeVariantDetailView },
    ] })
    await router.push("/resume-variants/variant-1")
    const wrapper = mount(ResumeVariantDetailView, { global: { plugins: [createPinia(), router], stubs } })
    await flushPromises()

    expect(getVariant).toHaveBeenCalledWith("variant-1")
    expect(getTemplate).toHaveBeenCalledWith("template-1", 1)
    expect(getPdf).toHaveBeenCalledWith("variant-1")
    expect(wrapper.text()).toContain("后端工程师 · 定制版")
    expect(wrapper.text()).toContain("清晰单栏")
    expect(wrapper.text()).toContain("weasyprint-69.0")
  })

  it("generates, previews and downloads an authenticated PDF", async () => {
    vi.spyOn(api, "getResumeVariant").mockResolvedValue(variant)
    vi.spyOn(api, "getTemplate").mockResolvedValue(template)
    vi.spyOn(api, "getLatestResumePdf").mockResolvedValue(null)
    const generate = vi.spyOn(api, "generateResumePdf").mockResolvedValue(pdf)
    const content = vi.spyOn(api, "getResumePdfContent").mockResolvedValue(
      new Blob(["pdf"], { type: "application/pdf" }),
    )
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:resume-pdf"),
    })
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(() => undefined),
    })
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined)
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: "/templates", component: { template: "<div />" } },
      { path: "/resume-variants/:id", component: ResumeVariantDetailView },
    ] })
    await router.push("/resume-variants/variant-1")
    const wrapper = mount(ResumeVariantDetailView, { global: { plugins: [createPinia(), router], stubs } })
    await flushPromises()

    await wrapper.get("button.button-primary").trigger("click")
    await flushPromises()
    expect(generate).toHaveBeenCalledWith("variant-1")
    expect(wrapper.text()).toContain("artifact-1")

    await wrapper.get("button.button-secondary").trigger("click")
    await flushPromises()
    await wrapper.findAll("button.button-primary").at(-1)!.trigger("click")
    await flushPromises()

    expect(content.mock.calls.map((call) => call[1])).toEqual([false, true])
    expect(wrapper.get("iframe").attributes("src")).toBe("blob:resume-pdf")
  })
})
