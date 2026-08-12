import { computed, ref } from "vue"
import { defineStore } from "pinia"

import { api } from "@/api/client"
import type {
  ApplicationDecision,
  CreateApplicationDecisionInput,
  CreateDecisionCaseInput,
  DecisionAnalysis,
  DecisionCase,
  DecisionReport,
} from "@/api/types"

export const useAnalysisStore = defineStore("analysis", () => {
  const currentCase = ref<DecisionCase | null>(null)
  const analysis = ref<DecisionAnalysis | null>(null)
  const report = ref<DecisionReport | null>(null)
  const decision = ref<ApplicationDecision | null>(null)
  const reports = ref<DecisionReport[]>([])
  const total = ref(0)
  const creating = ref(false)
  const analyzing = ref(false)
  const generating = ref(false)
  const listLoading = ref(false)
  const reportLoading = ref(false)
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
    reportLoading.value = true
    try {
      const [loaded, loadedDecision] = await Promise.all([
        api.getDecisionReport(reportId),
        api.getApplicationDecision(reportId),
      ])
      if (request === reportRequest) {
        report.value = loaded
        decision.value = loadedDecision
      }
      return loaded
    } finally {
      if (request === reportRequest) reportLoading.value = false
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
    decision.value = null
    reports.value = []
    total.value = 0
    creating.value = false
    analyzing.value = false
    generating.value = false
    listLoading.value = false
    reportLoading.value = false
    deciding.value = false
    pendingDecision = null
  }

  return {
    currentCase,
    analysis,
    report,
    decision,
    reports,
    total,
    creating,
    analyzing,
    generating,
    listLoading,
    reportLoading,
    deciding,
    isLoading,
    createCase,
    fetchAnalysis,
    generateReport,
    fetchReport,
    decide,
    fetchReports,
    reset,
  }
})
