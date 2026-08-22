import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { createMemoryHistory, createRouter } from "vue-router"

import { api } from "@/api/client"
import type { JdImportDraftResponse, JdInputPreview, JobPosting } from "@/api/types"
import JobCreateView from "@/views/JobCreateView.vue"

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client")
  return {
    ...actual,
    api: {
      createJob: vi.fn(),
      fetchJobPreview: vi.fn(),
      ocrJobPreview: vi.fn(),
      createJdImport: vi.fn(),
      getJdImport: vi.fn(),
      updateJdImportDraft: vi.fn(),
      confirmJdImport: vi.fn(),
    },
  }
})

const stubs = {
  AppShell: { template: "<main><slot /></main>" },
}

function job(): JobPosting {
  return {
    id: "job-1",
    jd_text: "Backend role",
    job_title: "Backend Engineer",
    company_name: "Nora",
    location: "Remote",
    summary: "Backend role",
    source_type: "manual",
    source_url: null,
    status: "active",
    version: 1,
    created_at: "2026-08-03T00:00:00Z",
  }
}

function jdDraft(): JdImportDraftResponse {
  return {
    session_id: "session-1",
    draft_id: "draft-1",
    source_type: "text",
    source_url: null,
    status: "draft_ready",
    version: 1,
    content_fingerprint: "a".repeat(64),
    prompt_version: "jd-import-v1",
    model_version: "qwen3.8-max",
    failure_code: null,
    content: {
      jd_text: "Backend role",
      job_title: "Backend Engineer",
      company_name: "Nora",
      location: "Remote",
      requirements: {
        required_skills: { value: ["Python"], confirmation_status: "unconfirmed", source_type: "text_range", source_range: null },
        minimum_experience_years: { value: null, confirmation_status: "unknown", source_type: "text_range", source_range: null },
        degree_requirement: { value: null, confirmation_status: "unknown", source_type: "text_range", source_range: null },
        location_requirement: { value: null, confirmation_status: "unknown", source_type: "text_range", source_range: null },
        work_mode: { value: null, confirmation_status: "unknown", source_type: "text_range", source_range: null },
      },
    },
  }
}

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/jobs/new", component: JobCreateView },
      { path: "/jobs/:id", name: "job-detail", component: { template: "<div />" } },
      { path: "/jobs", component: { template: "<div />" } },
    ],
  })
  await router.push("/jobs/new")
  const wrapper = mount(JobCreateView, { global: { plugins: [createPinia(), router], stubs } })
  await flushPromises()
  return { wrapper, router }
}

describe("JobCreateView", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorage.removeItem("nora.jd-import.session")
    vi.mocked(api.createJob).mockReset()
    vi.mocked(api.fetchJobPreview).mockReset()
    vi.mocked(api.ocrJobPreview).mockReset()
    vi.mocked(api.createJdImport).mockReset()
    vi.mocked(api.getJdImport).mockReset()
    vi.mocked(api.updateJdImportDraft).mockReset()
    vi.mocked(api.confirmJdImport).mockReset()
  })

  it("fetches a URL preview and fills the JD body for confirmation", async () => {
    const preview: JdInputPreview = {
      jd_text: "Fetched JD body",
      source_url: "https://example.com/jobs/1",
      kind: "url",
    }
    vi.mocked(api.fetchJobPreview).mockResolvedValueOnce(preview)
    const draft = jdDraft()
    draft.content.jd_text = preview.jd_text
    vi.mocked(api.createJdImport).mockResolvedValueOnce({ ...draft, source_type: "url", source_url: preview.source_url })
    const { wrapper } = await mountView()

    await wrapper.findAll(".mode-tab")[2]?.trigger("click")
    await wrapper.get('input[type="url"]').setValue("https://example.com/jobs/1")
    await wrapper.get(".form-section .button-secondary").trigger("click")
    await flushPromises()

    expect(api.fetchJobPreview).toHaveBeenCalledWith("https://example.com/jobs/1")
    expect((wrapper.get("textarea").element as HTMLTextAreaElement).value).toBe("Fetched JD body")
  })

  it("shows a stable error message when a URL preview is rejected as unsafe", async () => {
    const { ApiError } = await vi.importActual<typeof import("@/api/client")>("@/api/client")
    vi.mocked(api.fetchJobPreview).mockRejectedValueOnce(
      new ApiError("链接指向的地址不允许访问", 400, "unsafe_url"),
    )
    const { wrapper } = await mountView()

    await wrapper.findAll(".mode-tab")[2]?.trigger("click")
    await wrapper.get('input[type="url"]').setValue("https://169.254.169.254/")
    await wrapper.get(".form-section .button-secondary").trigger("click")
    await flushPromises()

    expect(wrapper.text()).toContain("链接指向的地址不允许访问")
    expect((wrapper.get("textarea").element as HTMLTextAreaElement).value).toBe("")
  })

  it("extracts OCR text from a selected screenshot and fills the JD body", async () => {
    const preview: JdInputPreview = { jd_text: "OCR extracted JD", source_url: null, kind: "image" }
    vi.mocked(api.ocrJobPreview).mockResolvedValueOnce(preview)
    const draft = jdDraft()
    draft.content.jd_text = preview.jd_text
    vi.mocked(api.createJdImport).mockResolvedValueOnce({ ...draft, source_type: "image" })
    const { wrapper } = await mountView()

    await wrapper.findAll(".mode-tab")[1]?.trigger("click")
    const file = new File(["screenshot"], "jd.png", { type: "image/png" })
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, "files", { value: [file] })
    await input.trigger("change")
    await flushPromises()

    expect(api.ocrJobPreview).toHaveBeenCalledWith(file)
    expect((wrapper.get("textarea").element as HTMLTextAreaElement).value).toBe("OCR extracted JD")
  })

  it("restores an unfinished draft after refresh and rejects invalid experience input", async () => {
    sessionStorage.setItem("nora.jd-import.session", "session-1")
    vi.mocked(api.getJdImport).mockResolvedValueOnce(jdDraft())
    const { wrapper } = await mountView()
    await flushPromises()

    expect(api.getJdImport).toHaveBeenCalledWith("session-1")
    expect(wrapper.text()).toContain("结构化岗位要求")
    const experience = wrapper.get('input[type="number"]')
    await experience.setValue("1.5")
    await wrapper.get("form").trigger("submit")
    await flushPromises()

    expect(wrapper.text()).toContain("最低经验年限必须是非负整数")
    expect(api.updateJdImportDraft).not.toHaveBeenCalled()
    sessionStorage.removeItem("nora.jd-import.session")
  })

  it("creates and confirms an AI draft instead of writing before confirmation", async () => {
    vi.mocked(api.createJdImport).mockResolvedValueOnce(jdDraft())
    vi.mocked(api.updateJdImportDraft).mockResolvedValueOnce({ ...jdDraft(), version: 2, content_fingerprint: "b".repeat(64) })
    vi.mocked(api.confirmJdImport).mockResolvedValueOnce({ job_posting: job(), requirement_snapshot: {} as never })
    const { wrapper, router } = await mountView()

    const textFields = wrapper.findAll('input[maxlength="200"]')
    await textFields[0]?.setValue("Backend Engineer")
    await textFields[1]?.setValue("Nora")
    await textFields[2]?.setValue("Remote")
    await wrapper.get("textarea").setValue("Backend role")
    await wrapper.get("form").trigger("submit")
    await flushPromises()

    expect(api.createJdImport).toHaveBeenCalledWith({ source_type: "text", jd_text: "Backend role", source_url: null })
    expect(api.confirmJdImport).not.toHaveBeenCalled()
    await wrapper.get("form").trigger("submit")
    await flushPromises()

    expect(api.updateJdImportDraft).toHaveBeenCalled()
    expect(api.confirmJdImport).toHaveBeenCalledWith("session-1", 2, "b".repeat(64))
    expect(router.currentRoute.value.path).toBe("/jobs/job-1")
  })
})
