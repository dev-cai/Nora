import { createPinia, setActivePinia } from "pinia"

import { api } from "@/api/client"
import { ApiError } from "@/api/client"
import type { ApplicationDecision, DecisionAnalysis, DecisionCase, DecisionReport, JobFitAnalysis } from "@/api/types"
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

const decision: ApplicationDecision = {
  id: "decision-1",
  report_id: "report-1",
  report_version: 1,
  decision_case_id: "case-1",
  resume_version_id: "resume-1",
  resume_version: 1,
  status: "skip",
  reason: "岗位地点不合适",
  actor_id: "user-1",
  decided_at: "2026-08-12T00:00:03Z",
}

const jobFit: JobFitAnalysis = {
  id: "job-fit-1",
  report_id: "report-1",
  report_version: 1,
  decision_case_id: "case-1",
  version: 1,
  prompt_version: "job-fit-v1",
  provider: "dashscope-cn-beijing",
  model: "qwen3.8-max",
  generator_version: "job-fit-analysis-v1",
  generation_identity: "a".repeat(64),
  overall_fit: "moderate",
  overall_fit_reason: { text: "Python 匹配。", citation_ids: ["skill"] },
  strong_matches: [],
  transferable_evidence: [],
  critical_gaps: [],
  non_blocking_gaps: [],
  resume_actions: [],
  project_deep_dive_risks: [],
  interview_focus: [],
  unknowns: [],
  citations: [{ citation_id: "skill", source: "candidate_profile", object_id: "profile-1", version: 3, field_path: "skills" }],
  generated_at: "2026-08-12T00:00:04Z",
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

  it("clears stale detail content while another immutable object is loading", async () => {
    let resolveAnalysis: ((value: DecisionAnalysis) => void) | undefined
    let resolveReport: ((value: DecisionReport) => void) | undefined
    vi.spyOn(api, "getDecisionAnalysis").mockImplementation(() => new Promise((resolve) => {
      resolveAnalysis = resolve
    }))
    vi.spyOn(api, "getDecisionReport").mockImplementation(() => new Promise((resolve) => {
      resolveReport = resolve
    }))
    vi.spyOn(api, "getApplicationDecision").mockResolvedValue(null)
    vi.spyOn(api, "getJobFitAnalysis").mockResolvedValue(null)
    const store = useAnalysisStore()
    store.$patch({
      currentCase: decisionCase,
      analysis: { decision: decisionCase, rule_set_version: "m3-rules-v1", rule_results: [] },
      report,
    })

    const analysisRequest = store.fetchAnalysis("case-2")
    const reportRequest = store.fetchReport("report-2")

    expect(store.currentCase).toBeNull()
    expect(store.analysis).toBeNull()
    expect(store.report).toBeNull()
    expect(store.analyzing).toBe(true)
    expect(store.reportLoading).toBe(true)

    resolveAnalysis?.({ decision: decisionCase, rule_set_version: "m3-rules-v1", rule_results: [] })
    resolveReport?.(report)
    await Promise.all([analysisRequest, reportRequest])
  })

  it("restores and records the immutable application decision", async () => {
    vi.spyOn(api, "getDecisionReport").mockResolvedValue(report)
    vi.spyOn(api, "getApplicationDecision").mockResolvedValue(decision)
    vi.spyOn(api, "getJobFitAnalysis").mockResolvedValue(jobFit)
    const createDecision = vi.spyOn(api, "createApplicationDecision").mockResolvedValue(decision)
    const store = useAnalysisStore()

    await store.fetchReport("report-1")
    await store.decide("report-1", { status: "skip", reason: "岗位地点不合适" })

    expect(store.decision).toEqual(decision)
    expect(store.jobFitAnalysis).toEqual(jobFit)
    expect(createDecision).toHaveBeenCalledWith(
      "report-1",
      { status: "skip", reason: "岗位地点不合适" },
      expect.any(String),
    )
  })

  it("generates and recovers one immutable AI analysis", async () => {
    vi.spyOn(api, "getDecisionReport").mockResolvedValue(report)
    vi.spyOn(api, "getApplicationDecision").mockResolvedValue(null)
    vi.spyOn(api, "getJobFitAnalysis").mockResolvedValue(jobFit)
    const generate = vi.spyOn(api, "generateJobFitAnalysis").mockResolvedValue(jobFit)
    const store = useAnalysisStore()

    await store.fetchReport("report-1")
    await store.generateJobFit("report-1")

    expect(store.jobFitAnalysis).toEqual(jobFit)
    expect(generate).toHaveBeenCalledWith("report-1")
    expect(store.jobFitGenerating).toBe(false)
  })

  it("keeps the deterministic report when AI recovery and generation fail", async () => {
    const unavailable = new ApiError(
      "AI 分析服务暂时不可用，请稍后重试",
      503,
      "model_provider_unavailable",
    )
    vi.spyOn(api, "getDecisionReport").mockResolvedValue(report)
    vi.spyOn(api, "getApplicationDecision").mockResolvedValue(null)
    vi.spyOn(api, "getJobFitAnalysis").mockRejectedValue(unavailable)
    vi.spyOn(api, "generateJobFitAnalysis").mockRejectedValue(unavailable)
    const store = useAnalysisStore()

    await store.fetchReport("report-1")
    await expect(store.generateJobFit("report-1")).rejects.toBe(unavailable)

    expect(store.report).toEqual(report)
    expect(store.decision).toBeNull()
    expect(store.jobFitAnalysis).toBeNull()
    expect(store.jobFitError).toContain("暂时不可用")
  })
})
