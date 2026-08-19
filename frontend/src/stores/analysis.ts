import { computed, ref } from "vue"
import { defineStore } from "pinia"

import { api, userMessage } from "@/api/client"
import type {
  ApplicationDecision,
  CreateApplicationDecisionInput,
  CreateDecisionCaseInput,
  DecisionAnalysis,
  DecisionCase,
  DecisionReport,
  JobFitAnalysis,
} from "@/api/types"

export const useAnalysisStore = defineStore("analysis", () => {
  const currentCase = ref<DecisionCase | null>(null)
  const analysis = ref<DecisionAnalysis | null>(null)
  const report = ref<DecisionReport | null>(null)
  const jobFitAnalysis = ref<JobFitAnalysis | null>(null)
  const jobFitError = ref("")
  const decision = ref<ApplicationDecision | null>(null)
  const reports = ref<DecisionReport[]>([])
  const total = ref(0)
  const creating = ref(false)
  const analyzing = ref(false)
  const generating = ref(false)
  const listLoading = ref(false)
  const reportLoading = ref(false)
  const jobFitGenerating = ref(false)
  const deciding = ref(false)
  const isLoading = computed(
    () => creating.value || analyzing.value || generating.value || listLoading.value || reportLoading.value || deciding.value,
  )
  let analysisRequest = 0
  let reportRequest = 0
  let listRequest = 0
  let pendingDecision: { fingerprint: string; idempotencyKey: string } | null = null

  async function createCase(input: CreateDecisionCaseInput): Promise<DecisionCase> {
    creating.value = true
    try {
      const created = await api.createDecisionCase(input)
      currentCase.value = created
      analysis.value = null
      report.value = null
      jobFitAnalysis.value = null
      jobFitError.value = ""
      decision.value = null
      return created
    } finally {
      creating.value = false
    }
  }

  async function fetchAnalysis(caseId: string): Promise<DecisionAnalysis> {
    const request = ++analysisRequest
    analysis.value = null
    currentCase.value = null
    analyzing.value = true
    try {
      const result = await api.getDecisionAnalysis(caseId)
      if (request === analysisRequest) {
        analysis.value = result
        currentCase.value = result.decision
      }
      return result
    } finally {
      if (request === analysisRequest) analyzing.value = false
    }
  }

  async function generateReport(caseId: string): Promise<DecisionReport> {
    generating.value = true
    try {
      const generated = await api.generateDecisionReport(caseId)
      report.value = generated
      reports.value = [generated, ...reports.value.filter((item) => item.id !== generated.id)]
      if (total.value < reports.value.length) total.value = reports.value.length
      return generated
    } finally {
      generating.value = false
    }
  }

  async function fetchReport(reportId: string): Promise<DecisionReport> {
    const request = ++reportRequest
    report.value = null
    decision.value = null
    jobFitAnalysis.value = null
    jobFitError.value = ""
    reportLoading.value = true
    const jobFitRequest = api.getJobFitAnalysis(reportId).then(
      (value) => ({ value } as const),
      (error: unknown) => ({ error } as const),
    )
    try {
      const [loaded, loadedDecision] = await Promise.all([
        api.getDecisionReport(reportId),
        api.getApplicationDecision(reportId),
      ])
      if (request === reportRequest) {
        report.value = loaded
        decision.value = loadedDecision
      }
      const recoveredJobFit = await jobFitRequest
      if (request === reportRequest) {
        if ("value" in recoveredJobFit) {
          jobFitAnalysis.value = recoveredJobFit.value
        } else {
          jobFitError.value = userMessage(recoveredJobFit.error)
        }
      }
      return loaded
    } finally {
      if (request === reportRequest) reportLoading.value = false
    }
  }

  async function generateJobFit(reportId: string): Promise<JobFitAnalysis> {
    jobFitGenerating.value = true
    jobFitError.value = ""
    try {
      const generated = await api.generateJobFitAnalysis(reportId)
      if (report.value?.id === reportId) jobFitAnalysis.value = generated
      return generated
    } catch (error) {
      if (report.value?.id === reportId) jobFitError.value = userMessage(error)
      throw error
    } finally {
      jobFitGenerating.value = false
    }
  }

  async function decide(
    reportId: string,
    input: CreateApplicationDecisionInput,
  ): Promise<ApplicationDecision> {
    const fingerprint = JSON.stringify(input)
    if (!pendingDecision || pendingDecision.fingerprint !== fingerprint) {
      pendingDecision = { fingerprint, idempotencyKey: crypto.randomUUID() }
    }
    deciding.value = true
    try {
      const created = await api.createApplicationDecision(
        reportId,
        input,
        pendingDecision.idempotencyKey,
      )
      decision.value = created
      pendingDecision = null
      return created
    } finally {
      deciding.value = false
    }
  }

  async function fetchReports(page = 1, pageSize = 20): Promise<void> {
    const request = ++listRequest
    listLoading.value = true
    try {
      const response = await api.listDecisionReports(page, pageSize)
      if (request === listRequest) {
        reports.value = response.items
        total.value = response.total
      }
    } finally {
      if (request === listRequest) listLoading.value = false
    }
  }

  function reset(): void {
    analysisRequest += 1
    reportRequest += 1
    listRequest += 1
    currentCase.value = null
    analysis.value = null
    report.value = null
    jobFitAnalysis.value = null
    jobFitError.value = ""
    decision.value = null
    reports.value = []
    total.value = 0
    creating.value = false
    analyzing.value = false
    generating.value = false
    listLoading.value = false
    reportLoading.value = false
    jobFitGenerating.value = false
    deciding.value = false
    pendingDecision = null
  }

  return {
    currentCase,
    analysis,
    report,
    jobFitAnalysis,
    jobFitError,
    decision,
    reports,
    total,
    creating,
    analyzing,
    generating,
    listLoading,
    reportLoading,
    jobFitGenerating,
    deciding,
    isLoading,
    createCase,
    fetchAnalysis,
    generateReport,
    fetchReport,
    generateJobFit,
    decide,
    fetchReports,
    reset,
  }
})
