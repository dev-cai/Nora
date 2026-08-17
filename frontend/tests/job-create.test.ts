import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { createMemoryHistory, createRouter } from "vue-router"

import { api } from "@/api/client"
import type { JdInputPreview, JobPosting } from "@/api/types"
import JobCreateView from "@/views/JobCreateView.vue"

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client")
  return {
    ...actual,
    api: {
      createJob: vi.fn(),
      fetchJobPreview: vi.fn(),
      ocrJobPreview: vi.fn(),
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
    vi.mocked(api.createJob).mockReset()
    vi.mocked(api.fetchJobPreview).mockReset()
    vi.mocked(api.ocrJobPreview).mockReset()
  })

  it("fetches a URL preview and fills the JD body for confirmation", async () => {
    const preview: JdInputPreview = {
      jd_text: "Fetched JD body",
      source_url: "https://example.com/jobs/1",
      kind: "url",
    }
    vi.mocked(api.fetchJobPreview).mockResolvedValueOnce(preview)
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

  it("still creates the job snapshot through the existing manual text path", async () => {
    vi.mocked(api.createJob).mockResolvedValueOnce(job())
    const { wrapper, router } = await mountView()

    const textFields = wrapper.findAll('input[maxlength="200"]')
    await textFields[0]?.setValue("Backend Engineer")
    await textFields[1]?.setValue("Nora")
    await textFields[2]?.setValue("Remote")
    await wrapper.get("textarea").setValue("Backend role")
    await wrapper.get("form").trigger("submit")
    await flushPromises()

    expect(api.createJob).toHaveBeenCalledWith(
      expect.objectContaining({ source_type: "manual", jd_text: "Backend role" }),
      expect.any(String),
    )
    expect(router.currentRoute.value.path).toBe("/jobs/job-1")
  })
})
