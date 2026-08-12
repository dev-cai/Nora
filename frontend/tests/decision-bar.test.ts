import { mount } from "@vue/test-utils"

import type { ApplicationDecision } from "@/api/types"
import DecisionBar from "@/components/DecisionBar.vue"

const decision: ApplicationDecision = {
  id: "decision-1",
  report_id: "report-1",
  report_version: 1,
  decision_case_id: "case-1",
  resume_version_id: "resume-1",
  resume_version: 2,
  status: "skip",
  reason: "地点不合适",
  actor_id: "user-1",
  decided_at: "2026-08-12T00:00:03Z",
}

describe("DecisionBar", () => {
  it("requires a reason for skip and emits the normalized decision", async () => {
    const wrapper = mount(DecisionBar, { props: { decision: null, saving: false } })

    await wrapper.get(".decision-segments button:nth-child(2)").trigger("click")
    expect(wrapper.get("button[type='submit']").attributes("disabled")).toBeDefined()
    await wrapper.get("textarea").setValue("  地点不合适  ")
    await wrapper.get("form").trigger("submit")

    expect(wrapper.emitted("submit")?.[0]).toEqual([{ status: "skip", reason: "地点不合适" }])
  })

  it("renders an immutable recorded decision", () => {
    const wrapper = mount(DecisionBar, { props: { decision, saving: false } })

    expect(wrapper.text()).toContain("暂不投递")
    expect(wrapper.text()).toContain("地点不合适")
    expect(wrapper.text()).toContain("报告 v1")
    expect(wrapper.find("form").exists()).toBe(false)
  })
})
