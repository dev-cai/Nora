import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"
import { createMemoryHistory, createRouter } from "vue-router"

import { ApiError, api } from "@/api/client"
import type { MessageDraft } from "@/api/types"
import { useMessagesStore } from "@/stores/messages"
import MessageDraftView from "@/views/MessageDraftView.vue"

const draft: MessageDraft = {
  id: "draft-1",
  version: 1,
  application_decision_id: "decision-1",
  report_id: "report-1",
  report_version: 1,
  decision_case_id: "case-1",
  resume_variant_id: "variant-1",
  resume_variant_version: 1,
  variant_content_fingerprint: "a".repeat(64),
  candidate_profile_id: "profile-1",
  candidate_profile_version: 2,
  resume_version_id: "resume-1",
  resume_version: 3,
  job_posting_id: "job-1",
  job_posting_version: 1,
  company_snapshot_id: null,
  company_snapshot_version: null,
  company_snapshot_hash: null,
  company_freshness: null,
  style: "professional",
  user_note: null,
  referral_context: null,
  generator_version: "m4-message-draft-v1",
  template_version: "message-template-v1",
  generation_identity: "b".repeat(64),
  text: "您好，我是 Alice。",
  content_fingerprint: "c".repeat(64),
  revision_type: "generated",
  previous_version: null,
  created_at: "2026-08-14T00:00:00Z",
}

describe("message drafts", () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it("reuses idempotency keys after failure and rotates them after success", async () => {
    vi.spyOn(crypto, "randomUUID")
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000001")
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000002")
    const generate = vi.spyOn(api, "generateMessageDraft")
      .mockRejectedValueOnce(new ApiError("暂时失败"))
      .mockResolvedValueOnce(draft)
      .mockResolvedValueOnce({ ...draft, id: "draft-2", style: "concise" })
    const store = useMessagesStore()
    const professional = { style: "professional", user_note: null, referral_context: null } as const

    await expect(store.generate("variant-1", professional)).rejects.toThrow("暂时失败")
    await expect(store.generate("variant-1", professional)).resolves.toBe(draft)
    await store.generate("variant-1", { ...professional, style: "concise" })

    expect(generate.mock.calls.map((call) => call[2])).toEqual([
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000002",
    ])
  })

  it("clears stale detail state before loading another draft", async () => {
    const store = useMessagesStore()
    store.current = draft
    store.versions = [draft]
    vi.spyOn(api, "getMessageDraft").mockRejectedValue(new ApiError("对象不存在", 404))

    await expect(store.fetchDraft("foreign-draft")).rejects.toThrow("对象不存在")

    expect(store.current).toBeNull()
    expect(store.versions).toEqual([])
  })

  it("loads, refreshes, saves a new version and copies in the browser", async () => {
    const edited = {
      ...draft,
      version: 2,
      text: `${draft.text}\n\n期待您的回复。`,
      revision_type: "edited" as const,
      previous_version: 1,
    }
    const getDraft = vi.spyOn(api, "getMessageDraft").mockResolvedValueOnce(draft).mockResolvedValueOnce(edited)
    const versions = vi.spyOn(api, "listMessageDraftVersions")
      .mockResolvedValueOnce([draft])
      .mockResolvedValueOnce([edited, draft])
      .mockResolvedValueOnce([edited, draft])
    const edit = vi.spyOn(api, "editMessageDraft").mockResolvedValue(edited)
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } })
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: "/resume-variants/:id", component: { template: "<div />" } },
      { path: "/messages/:id", component: MessageDraftView },
    ] })
    await router.push("/messages/draft-1")
    const wrapper = mount(MessageDraftView, {
      global: {
        plugins: [createPinia(), router],
        stubs: {
          AppShell: { template: "<main><slot /></main>" },
          StatePanel: { template: "<div data-state />" },
        },
      },
    })
    await flushPromises()

    await wrapper.get('textarea[aria-label="消息草稿内容"]').setValue(edited.text)
    await wrapper.get(".message-editor-actions .button-primary").trigger("click")
    await flushPromises()

    expect(edit).toHaveBeenCalledWith(
      "draft-1",
      { base_version: 1, text: edited.text },
      expect.any(String),
    )
    expect(wrapper.text()).toContain("版本 2")
    expect(wrapper.text()).toContain("v2 · 编辑")

    await wrapper.get(".message-editor-actions .button-secondary").trigger("click")
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith(edited.text)
    expect(wrapper.text()).toContain("已复制")

    await wrapper.get("textarea").setValue(`${edited.text}\n继续修改`)
    expect(wrapper.text()).toContain("复制")
    expect(wrapper.text()).not.toContain("已复制")
    await wrapper.get("textarea").setValue(edited.text)

    await wrapper.get('button[aria-label="刷新"]').trigger("click")
    await flushPromises()
    expect(getDraft).toHaveBeenCalledTimes(2)
    expect(versions).toHaveBeenCalledTimes(3)
    expect(wrapper.get("textarea").element.value).toBe(edited.text)
  })
})
