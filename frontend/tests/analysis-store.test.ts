import { createPinia, setActivePinia } from "pinia"

import { api } from "@/api/client"
import type { DecisionAnalysis, DecisionCase, DecisionReport } from "@/api/types"
import { useAnalysisStore } from "@/stores/analysis"

const decisionCase: DecisionCase = {
  id: "case-1",
  job_posting_id: "job-1",
  job_posting_version: 1,
  job_requirement_snapshot_id: "requirements-1",
  job_requirement_snapshot_version: 2,
  candidate_profile_id: "profile-1",
  candidate_profile_version: 3,
  resume_version_id: "resume-1",
  resume_version: 1,
  rule_set_version: "m3-rules-v1",
  status: "completed",
  created_at: "2026-08-12T00:00:00Z",
  completed_at: "2026-08-12T00:00:01Z",
  failure_code: null,
  failure_message: null,
}

const report: DecisionReport = {
  id: "report-1",
  decision_case_id: "case-1",
  version: 1,
  rule_set_version: "m3-rules-v1",
  generator_version: "m3-report-v1",
  summary: { match: 1, partial: 1, mismatch: 0, unknown: 2 },
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

describe("analysis store", () => {
  beforeEach(() => setActivePinia(createPinia()))

  it("creates and synchronously loads an analysis", async () => {
    const analysis: DecisionAnalysis = {
      decision: decisionCase,
      rule_set_version: "m3-rules-v1",
      rule_results: [],
    }
    vi.spyOn(api, "createDecisionCase").mockResolvedValue(decisionCase)
    vi.spyOn(api, "getDecisionAnalysis").mockResolvedValue(analysis)
    const store = useAnalysisStore()

    await store.createCase({} as never)
    await store.fetchAnalysis("case-1")

    expect(store.currentCase).toEqual(decisionCase)
    expect(store.analysis).toEqual(analysis)
    expect(store.analyzing).toBe(false)
  })

  it("keeps report history newest-first without duplicating an idempotent report", async () => {
    vi.spyOn(api, "listDecisionReports").mockResolvedValue({ items: [report], page: 1, page_size: 20, total: 1 })
    vi.spyOn(api, "generateDecisionReport").mockResolvedValue(report)
    const store = useAnalysisStore()

    await store.fetchReports()
    await store.generateReport("case-1")

    expect(store.reports).toEqual([report])
    expect(store.total).toBe(1)
  })
})
