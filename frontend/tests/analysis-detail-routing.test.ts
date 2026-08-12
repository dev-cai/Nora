import { flushPromises, mount } from "@vue/test-utils"
import { createPinia } from "pinia"
import { createMemoryHistory, createRouter } from "vue-router"

import { api } from "@/api/client"
import type { DecisionAnalysis, DecisionCase, DecisionReport } from "@/api/types"
import AnalysisDetailView from "@/views/AnalysisDetailView.vue"
import ReportDetailView from "@/views/ReportDetailView.vue"

const decisionCase: DecisionCase = {
  id: "case-1",
  job_posting_id: "job-1",
  job_posting_version: 1,
  job_requirement_snapshot_id: "requirements-1",
  job_requirement_snapshot_version: 1,
  candidate_profile_id: "profile-1",
  candidate_profile_version: 1,
  resume_version_id: "resume-1",
  resume_version: 1,
  rule_set_version: "m3-rules-v1",
  status: "completed",
  created_at: "2026-08-12T00:00:00Z",
  completed_at: "2026-08-12T00:00:01Z",
  failure_code: null,
  failure_message: null,
}

const analysis: DecisionAnalysis = {
  decision: decisionCase,
  rule_set_version: "m3-rules-v1",
  rule_results: [],
}

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

const stubs = {
  AppShell: { template: "<main><slot /></main>" },
  ReportContent: { template: "<div />" },
  RuleStatusBadge: { template: "<span />" },
  StatePanel: { template: "<div />" },
}

describe("analysis detail route changes", () => {
  it("reloads the report when the reused route changes its id", async () => {
    const getReport = vi.spyOn(api, "getDecisionReport").mockResolvedValue(report)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/reports", component: { template: "<div />" } },
        { path: "/reports/:id", component: ReportDetailView },
      ],
    })
    await router.push("/reports/report-1")
    const wrapper = mount(ReportDetailView, { global: { plugins: [createPinia(), router], stubs } })
    await flushPromises()

    await router.push("/reports/report-2")
    await flushPromises()

    expect(getReport).toHaveBeenNthCalledWith(1, "report-1")
    expect(getReport).toHaveBeenNthCalledWith(2, "report-2")
    wrapper.unmount()
  })

  it("reloads the analysis when the reused route changes its id", async () => {
    const getAnalysis = vi.spyOn(api, "getDecisionAnalysis").mockResolvedValue(analysis)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/analysis/new", component: { template: "<div />" } },
        { path: "/analysis/:id", component: AnalysisDetailView },
      ],
    })
    await router.push("/analysis/case-1")
    const wrapper = mount(AnalysisDetailView, { global: { plugins: [createPinia(), router], stubs } })
    await flushPromises()

    await router.push("/analysis/case-2")
    await flushPromises()

    expect(getAnalysis).toHaveBeenNthCalledWith(1, "case-1")
    expect(getAnalysis).toHaveBeenNthCalledWith(2, "case-2")
    wrapper.unmount()
  })
})
