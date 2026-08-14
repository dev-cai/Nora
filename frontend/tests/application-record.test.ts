import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { createMemoryHistory, createRouter } from "vue-router"

import { ApiError, api } from "@/api/client"
import type {
  ApplicationRecord,
  ApplicationRecordTransition,
  MessageDraft,
  ResumePdf,
  ResumeVariant,
} from "@/api/types"
import { useApplicationsStore } from "@/stores/applications"
import ApplicationRecordCreateView from "@/views/ApplicationRecordCreateView.vue"
import ApplicationRecordDetailView from "@/views/ApplicationRecordDetailView.vue"

const record: ApplicationRecord = {
  id: "application-1",
  version: 1,
  status: "planned",
  application_decision_id: "decision-1",
  decision_case_id: "case-1",
  resume_variant_id: "variant-1",
  resume_variant_version: 1,
  variant_content_fingerprint: "a".repeat(64),
  resume_pdf_id: "pdf-1",
  resume_pdf_version: 1,
  artifact_id: "artifact-1",
  artifact_version: 1,
  artifact_sha256: "b".repeat(64),
  message_draft_id: "draft-1",
  message_draft_version: 2,
  message_content_fingerprint: "c".repeat(64),
  created_by: "user-1",
  created_at: "2026-08-15T00:00:00Z",
  updated_at: "2026-08-15T00:00:00Z",
}

const applied: ApplicationRecord = {
  ...record,
  version: 2,
  status: "applied",
  updated_at: "2026-08-15T01:00:00Z",
}

const transition: ApplicationRecordTransition = {
  id: "transition-1",
  record_version: 2,
  actor_id: "user-1",
  from_status: "planned",
  to_status: "applied",
  source: "user_confirmation",
  channel: "公司官网",
  note: "已确认",
  occurred_at: "2026-08-15T01:00:00Z",
  recorded_at: "2026-08-15T01:01:00Z",
}

const variant: ResumeVariant = {
  id: "variant-1",
  version: 1,
  application_decision_id: "decision-1",
  decision_case_id: "case-1",
  job_posting_id: "job-1",
  job_posting_version: 1,
  job_requirement_snapshot_id: "requirement-1",
  job_requirement_snapshot_version: 1,
  resume_version_id: "resume-1",
  resume_version: 1,
  template_id: "template-1",
  template_version: 1,
  title: "后端工程师定制简历",
  blocks: [],
  generator_version: "m4-resume-variant-v1",
  content_fingerprint: "a".repeat(64),
  created_at: "2026-08-15T00:00:00Z",
}

const pdf: ResumePdf = {
  id: "pdf-1",
  version: 1,
  resume_variant_id: "variant-1",
  resume_variant_version: 1,
  template_id: "template-1",
  template_version: 1,
  template_definition_hash: "d".repeat(64),
  variant_content_fingerprint: "a".repeat(64),
  renderer_version: "renderer-v1",
  font_set_version: "fonts-v1",
  locale: "zh-CN",
  timezone: "UTC",
  generation_identity: "e".repeat(64),
  status: "available",
  artifact_id: "artifact-1",
  artifact_version: 1,
  artifact_sha256: "b".repeat(64),
  artifact_size_bytes: 100,
  created_at: "2026-08-15T00:00:00Z",
  updated_at: "2026-08-15T00:00:00Z",
}

const draft = {
  id: "draft-1",
  version: 2,
  resume_variant_id: "variant-1",
} as MessageDraft

describe("application records", () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it("reuses a create idempotency key after failure and rotates it after success", async () => {
    vi.spyOn(crypto, "randomUUID")
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000001")
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000002")
    const create = vi.spyOn(api, "createApplicationRecord")
      .mockRejectedValueOnce(new ApiError("暂时失败"))
      .mockResolvedValueOnce(record)
      .mockResolvedValueOnce({ ...record, id: "application-2" })
    const store = useApplicationsStore()
    const input = {
      application_decision_id: "decision-1",
      resume_variant_id: "variant-1",
      resume_pdf_id: null,
      message_draft_id: null,
      message_draft_version: null,
    }

    await expect(store.create(input)).rejects.toThrow("暂时失败")
    await expect(store.create(input)).resolves.toBe(record)
    await store.create({ ...input, resume_pdf_id: "pdf-1" })

    expect(create.mock.calls.map((call) => call[1])).toEqual([
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000002",
    ])
  })

  it("confirms planned to applied and restores the result after refresh", async () => {
    const getRecord = vi.spyOn(api, "getApplicationRecord")
      .mockResolvedValueOnce(record)
      .mockResolvedValueOnce(applied)
    vi.spyOn(api, "listApplicationRecordTransitions")
      .mockResolvedValueOnce([])
      .mockResolvedValue([transition])
    const update = vi.spyOn(api, "transitionApplicationRecord").mockResolvedValue(applied)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/applications", component: { template: "<div />" } },
        { path: "/applications/:id", component: ApplicationRecordDetailView },
      ],
    })
    await router.push("/applications/application-1")
    const wrapper = mount(ApplicationRecordDetailView, {
      global: {
        plugins: [createPinia(), router],
        stubs: {
          AppShell: { template: "<main><slot /></main>" },
          StatePanel: { template: "<div data-state />" },
        },
      },
    })
    await flushPromises()

    const appliedButton = wrapper.findAll(".application-status-control button")
      .find((button) => button.text() === "已投递")
    await appliedButton?.trigger("click")
    await wrapper.get('select').setValue("公司官网")
    await wrapper.get(".application-transition-band .button-primary").trigger("click")
    await flushPromises()

    expect(update).toHaveBeenCalledWith(
      "application-1",
      expect.objectContaining({
        base_version: 1,
        to_status: "applied",
        channel: "公司官网",
      }),
      expect.any(String),
    )
    expect(wrapper.text()).toContain("已投递")
    expect(wrapper.text()).toContain("待确认 → 已投递")

    await wrapper.get('button[aria-label="刷新"]').trigger("click")
    await flushPromises()
    expect(getRecord).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain("记录 v2")
  })

  it("creates planned records from explicitly selected material versions", async () => {
    vi.spyOn(api, "getResumeVariant").mockResolvedValue(variant)
    vi.spyOn(api, "getLatestResumePdf").mockResolvedValue(pdf)
    vi.spyOn(api, "getLatestMessageDraft").mockResolvedValue(draft)
    const create = vi.spyOn(api, "createApplicationRecord").mockResolvedValue(record)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/templates", component: { template: "<div />" } },
        { path: "/resume-variants/:id", component: { template: "<div />" } },
        { path: "/applications/new", component: ApplicationRecordCreateView },
        { path: "/applications/:id", component: { template: "<div />" } },
      ],
    })
    await router.push("/applications/new?variant=variant-1")
    const wrapper = mount(ApplicationRecordCreateView, {
      global: {
        plugins: [createPinia(), router],
        stubs: {
          AppShell: { template: "<main><slot /></main>" },
          StatePanel: { template: "<div data-state />" },
        },
      },
    })
    await flushPromises()

    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    await checkboxes[1]?.setValue(false)
    await wrapper.get(".form-actions .button-primary").trigger("click")
    await flushPromises()

    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({
        resume_pdf_id: "pdf-1",
        message_draft_id: null,
        message_draft_version: null,
      }),
      expect.any(String),
    )
    expect(router.currentRoute.value.path).toBe("/applications/application-1")
  })
})
