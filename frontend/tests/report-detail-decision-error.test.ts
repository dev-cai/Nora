import { flushPromises, mount } from "@vue/test-utils"
import { createPinia } from "pinia"
import { createMemoryHistory, createRouter } from "vue-router"

import { ApiError, api } from "@/api/client"
import type { DecisionReport } from "@/api/types"
import ReportDetailView from "@/views/ReportDetailView.vue"

const report: DecisionReport = {
  id: "report-1",
  decision_case_id: "case-1",
  version: 1,
  rule_set_version: "m3-rules-v1",
  generator_version: "m3-report-v1",
  summary: { match: 0, partial: 0, mismatch: 0, unknown: 0 },
  facts: [],
  rule_results: [],
  unknowns: [],
  recommendations: [],
  citations: [],
  satisfied_conditions: [],
  gaps: [],
  risks: [],
  next_steps: [],
  generated_at: "2026-08-12T00:00:02Z",
}

describe("report decision errors", () => {
  it("keeps the report visible when the decision conflicts", async () => {
    vi.spyOn(api, "getDecisionReport").mockResolvedValue(report)
    vi.spyOn(api, "getApplicationDecision").mockResolvedValue(null)
    vi.spyOn(api, "createApplicationDecision").mockRejectedValue(
      new ApiError("该报告已经记录了不同决定", 409, "application_decision_conflict"),
    )
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/reports", component: { template: "<div />" } },
        { path: "/reports/:id", component: ReportDetailView },
        { path: "/companies/new", component: { template: "<div />" } },
      ],
    })
    await router.push("/reports/report-1")
    const wrapper = mount(ReportDetailView, {
      global: {
        plugins: [createPinia(), router],
        stubs: {
          AppShell: { template: "<main><slot /></main>" },
          ReportContent: { template: "<div data-report />" },
          DecisionBar: {
            template: "<button data-decide @click=\"$emit('submit', { status: 'apply', reason: null })\" />",
          },
          StatePanel: { template: "<div data-state />" },
        },
      },
    })
    await flushPromises()

    await wrapper.get("[data-decide]").trigger("click")
    await flushPromises()

    expect(wrapper.find("[data-report]").exists()).toBe(true)
    expect(wrapper.text()).toContain("该报告已经记录了不同决定")
    expect(wrapper.find("[data-state]").exists()).toBe(false)
  })
})
