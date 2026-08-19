<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowLeft, Building2, FilePenLine, Plus, RefreshCw, ShieldCheck, Sparkles } from "lucide-vue-next"
import { useRoute } from "vue-router"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import DecisionBar from "@/components/DecisionBar.vue"
import CompanySnapshotCard from "@/components/CompanySnapshotCard.vue"
import JobFitAnalysisPanel from "@/components/JobFitAnalysisPanel.vue"
import ReportContent from "@/components/ReportContent.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useAnalysisStore } from "@/stores/analysis"
import { useCompaniesStore } from "@/stores/companies"

const route = useRoute()
const store = useAnalysisStore()
const companies = useCompaniesStore()
const loadError = ref("")
const decisionError = ref("")
const reportId = computed(() => String(route.params.id))
const companySnapshotId = ref("")
const companySnapshotVersion = ref(1)
const companyError = ref("")

async function load(): Promise<void> {
  loadError.value = ""
  decisionError.value = ""
  try {
    await store.fetchReport(reportId.value)
  } catch (reason) {
    loadError.value = userMessage(reason)
  }
}

async function decide(input: Parameters<typeof store.decide>[1]): Promise<void> {
  decisionError.value = ""
  try {
    await store.decide(reportId.value, input)
  } catch (reason) {
    decisionError.value = userMessage(reason)
  }
}

async function generateJobFit(): Promise<void> {
  try {
    await store.generateJobFit(reportId.value)
  } catch {
    // The AI error is displayed locally; deterministic report actions remain available.
  }
}

async function attachCompany(): Promise<void> {
  companyError.value = ""
  if (!companySnapshotId.value.trim() || companySnapshotVersion.value < 1) {
    companyError.value = "请填写公司情报 ID 和有效版本"
    return
  }
  try {
    const assessment = await companies.attachToReport(
      reportId.value,
      companySnapshotId.value.trim(),
      companySnapshotVersion.value,
    )
    if (store.report) store.report.company_assessment = assessment
  } catch (reason) {
    companyError.value = userMessage(reason)
  }
}

watch(reportId, () => void load(), { immediate: true })
</script>

<template>
  <AppShell>
    <RouterLink
      class="back-link"
      to="/reports"
    >
      <ArrowLeft :size="16" /> 返回报告历史
    </RouterLink>
    <StatePanel
      v-if="store.reportLoading && !store.report"
      mode="loading"
      title="正在读取报告"
    />
    <StatePanel
      v-else-if="loadError"
      mode="error"
      title="无法读取报告"
      :message="loadError"
      @retry="load"
    />
    <template v-else-if="store.report">
      <header class="report-detail-header">
        <div>
          <p class="eyebrow">
            不可变决策报告
          </p>
          <h2>报告 v{{ store.report.version }}</h2>
          <p>生成于 {{ new Date(store.report.generated_at).toLocaleString('zh-CN') }}</p>
        </div>
        <div class="detail-actions">
          <span class="analysis-mode-badge">
            <Sparkles
              v-if="store.jobFitAnalysis"
              :size="16"
            />
            <ShieldCheck
              v-else
              :size="16"
            />
            {{ store.jobFitAnalysis ? `AI 分析 v${store.jobFitAnalysis.version}` : '确定性规则报告' }}
          </span>
          <button
            class="button button-secondary button-small"
            type="button"
            @click="load"
          >
            <RefreshCw :size="16" /> 刷新
          </button>
        </div>
      </header>
      <ReportContent :report="store.report" />
      <section class="job-fit-band">
        <div class="job-fit-band-heading">
          <div class="report-section-heading">
            <Sparkles :size="19" />
            <div><h3>AI 人岗语义分析</h3><p>只读取本报告固定输入；模型推断、建议和未知均显示字段级引用。</p></div>
          </div>
          <button
            class="button button-primary button-small"
            type="button"
            :disabled="store.jobFitGenerating"
            @click="generateJobFit"
          >
            <RefreshCw
              v-if="store.jobFitAnalysis"
              :size="16"
            />
            <Sparkles
              v-else
              :size="16"
            />
            {{ store.jobFitGenerating ? '分析中…' : store.jobFitAnalysis ? '恢复同一版本' : '生成 AI 分析' }}
          </button>
        </div>
        <p
          v-if="store.jobFitError"
          class="job-fit-error"
          role="alert"
        >
          {{ store.jobFitError }}。确定性报告和投递决定不受影响。
        </p>
        <JobFitAnalysisPanel
          v-if="store.jobFitAnalysis"
          :analysis="store.jobFitAnalysis"
        />
        <div
          v-else-if="!store.jobFitError"
          class="job-fit-empty"
        >
          <strong>{{ store.jobFitGenerating ? '正在生成语义分析' : '尚未生成 AI 分析' }}</strong>
          <p>确定性规则结果已经可用，AI 分析是独立的可选增强。</p>
        </div>
      </section>
      <section class="company-report-band">
        <div class="report-section-heading">
          <Building2 :size="19" />
          <div><h3>公司情报</h3><p>报告只读取已绑定的精确快照版本。</p></div>
        </div>
        <template v-if="store.report.company_assessment">
          <CompanySnapshotCard
            :snapshot="store.report.company_assessment.snapshot"
            :assessment="store.report.company_assessment"
          />
          <RouterLink
            class="company-exact-link"
            :to="`/companies/${store.report.company_assessment.snapshot.id}?version=${store.report.company_assessment.snapshot.version}`"
          >
            查看固定的 CompanySnapshot v{{ store.report.company_assessment.snapshot.version }}
          </RouterLink>
        </template>
        <div
          v-else
          class="company-empty-state"
        >
          <div><strong>尚未绑定公司情报</strong><p>缺失保持 unknown，不影响确定性岗位规则结果。</p></div>
          <RouterLink
            class="button button-primary"
            :to="`/companies/new?report=${encodeURIComponent(reportId)}`"
          >
            <Plus :size="16" /> 录入并绑定
          </RouterLink>
        </div>
        <details
          v-if="!store.report.company_assessment"
          class="company-attach-existing"
        >
          <summary>绑定已有版本</summary>
          <form
            class="form-grid two-columns"
            @submit.prevent="attachCompany"
          >
            <label>CompanySnapshot ID<input v-model="companySnapshotId"></label>
            <label>版本<input
              v-model.number="companySnapshotVersion"
              type="number"
              min="1"
            ></label>
            <p
              v-if="companyError"
              class="form-error"
            >
              {{ companyError }}
            </p>
            <button
              class="button button-secondary"
              type="submit"
              :disabled="companies.attaching"
            >
              {{ companies.attaching ? '绑定中…' : '绑定固定版本' }}
            </button>
          </form>
        </details>
      </section>
      <p
        v-if="decisionError"
        class="form-error decision-error"
      >
        {{ decisionError }}
      </p>
      <DecisionBar
        :decision="store.decision"
        :saving="store.deciding"
        @submit="decide"
      />
      <section
        v-if="store.decision?.status === 'apply'"
        class="variant-next-step"
      >
        <div>
          <p class="eyebrow">
            下一步
          </p>
          <h3>为这个岗位定制简历</h3>
          <p>基于本次决定固定的简历版本选择内容和模板。</p>
        </div>
        <RouterLink
          class="button button-primary"
          :to="{ name: 'resume-customize', params: { id: store.decision.resume_version_id }, query: { decision: store.decision.id } }"
        >
          <FilePenLine :size="17" /> 定制简历
        </RouterLink>
      </section>
      <section class="locked-band">
        <ShieldCheck :size="18" />
        <div><strong>固定版本报告</strong><p>刷新会从服务端重新读取同一报告版本，不会重新计算或覆盖历史。</p></div>
      </section>
    </template>
  </AppShell>
</template>
