import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { createMemoryHistory, createRouter } from "vue-router"

import { ApiError, api } from "@/api/client"
import type { ApplicationRecord, InterviewCase } from "@/api/types"
import { useInterviewsStore } from "@/stores/interviews"
import InterviewCreateView from "@/views/InterviewCreateView.vue"
import InterviewDetailView from "@/views/InterviewDetailView.vue"

const application: ApplicationRecord = {
  id: "application-1",
  version: 3,
  status: "interviewing",
  application_decision_id: "decision-1",
  decision_case_id: "case-1",
  resume_variant_id: "variant-1",
  resume_variant_version: 1,
  variant_content_fingerprint: "a".repeat(64),
  resume_pdf_id: null,
  resume_pdf_version: null,
  artifact_id: null,
  artifact_version: null,
  artifact_sha256: null,
  message_draft_id: null,
  message_draft_version: null,
  message_content_fingerprint: null,
  created_by: "user-1",
  created_at: "2026-08-15T00:00:00Z",
  updated_at: "2026-08-16T00:00:00Z",
}

const interview: InterviewCase = {
  id: "interview-1",
  application_record_id: application.id,
  version: 1,
  actor_id: "user-1",
  starts_at: "2026-10-15T01:30:00Z",
  timezone: "Asia/Shanghai",
  mode: "online",
  location: null,
  meeting_url: "https://meet.example.com/private-token",
  round_number: 1,
  note: "准备项目案例",
  source: "user_confirmation",
  status: "scheduled",
  created_at: "2026-08-16T00:00:00Z",
  updated_at: "2026-08-16T00:00:00Z",
}

const updated: InterviewCase = {
  ...interview,
  version: 2,
  starts_at: "2026-10-15T02:30:00Z",
  mode: "onsite",
  location: "上海办公室",
  meeting_url: null,
  round_number: 2,
  updated_at: "2026-08-16T01:00:00Z",
}

describe("interview cases", () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it("reuses the mutation key after failure and rotates it after success", async () => {
    vi.spyOn(crypto, "randomUUID")
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000001")
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000002")
    const create = vi.spyOn(api, "createInterview")
      .mockRejectedValueOnce(new ApiError("暂时失败"))
      .mockResolvedValueOnce(interview)
      .mockResolvedValueOnce({ ...interview, id: "interview-2" })
    const store = useInterviewsStore()
    const input = {
      starts_at: interview.starts_at,
      timezone: interview.timezone,
      mode: interview.mode,
      location: interview.location,
      meeting_url: interview.meeting_url,
      round_number: interview.round_number,
      note: interview.note,
      status: interview.status,
    }

    await expect(store.create(application.id, input)).rejects.toThrow("暂时失败")
    await expect(store.create(application.id, input)).resolves.toBe(interview)
    await store.create(application.id, { ...input, round_number: 2 })

    expect(create.mock.calls.map((call) => call[2])).toEqual([
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000002",
    ])
  })

  it("creates an online interview from an interviewing application", async () => {
    vi.spyOn(api, "getApplicationRecord").mockResolvedValue(application)
    const create = vi.spyOn(api, "createInterview").mockResolvedValue(interview)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/applications", component: { template: "<div />" } },
        { path: "/applications/:id", component: { template: "<div />" } },
        { path: "/interviews/new", component: InterviewCreateView },
        { path: "/interviews/:id", component: { template: "<div />" } },
      ],
    })
    await router.push("/interviews/new?application=application-1")
    const wrapper = mount(InterviewCreateView, {
      global: {
        plugins: [createPinia(), router],
        stubs: {
          AppShell: { template: "<main><slot /></main>" },
          StatePanel: { template: "<div data-state />" },
        },
      },
    })
    await flushPromises()

    await wrapper.get('input[type="url"]').setValue(interview.meeting_url)
    await wrapper.get("form").trigger("submit")
    await flushPromises()

    expect(create).toHaveBeenCalledWith(
      application.id,
      expect.objectContaining({
        mode: "online",
        meeting_url: interview.meeting_url,
        location: null,
      }),
      expect.any(String),
    )
    expect(router.currentRoute.value.path).toBe("/interviews/interview-1")
  })

  it("appends a version and restores it after refresh", async () => {
    const getInterview = vi.spyOn(api, "getInterview")
      .mockResolvedValueOnce(interview)
      .mockResolvedValueOnce(updated)
    vi.spyOn(api, "listInterviewVersions")
      .mockResolvedValueOnce([interview])
      .mockResolvedValue([updated, interview])
    const update = vi.spyOn(api, "updateInterview").mockResolvedValue(updated)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/applications/:id", component: { template: "<div />" } },
        { path: "/interviews", component: { template: "<div />" } },
        { path: "/interviews/:id", component: InterviewDetailView },
      ],
    })
    await router.push("/interviews/interview-1")
    const wrapper = mount(InterviewDetailView, {
      global: {
        plugins: [createPinia(), router],
        stubs: {
          AppShell: { template: "<main><slot /></main>" },
          StatePanel: { template: "<div data-state />" },
        },
      },
    })
    await flushPromises()

    const onsite = wrapper.findAll(".interview-mode-field button")
      .find((button) => button.text() === "线下")
    await onsite?.trigger("click")
    await flushPromises()
    await wrapper.get('input[maxlength="500"]').setValue("上海办公室")
    await wrapper.get(".interview-detail-form").trigger("submit")
    await flushPromises()

    expect(update).toHaveBeenCalledWith(
      "interview-1",
      expect.objectContaining({
        base_version: 1,
        mode: "onsite",
        location: "上海办公室",
        meeting_url: null,
      }),
      expect.any(String),
    )
    expect(wrapper.text()).toContain("安排 v2")
    expect(wrapper.text()).toContain("v1")

    await wrapper.get('button[aria-label="刷新"]').trigger("click")
    await flushPromises()
    expect(getInterview).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain("第 2 轮")
  })
})
