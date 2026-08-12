<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowLeft, FileText, RefreshCw, ShieldCheck } from "lucide-vue-next"
import { useRoute, useRouter } from "vue-router"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import RuleStatusBadge from "@/components/RuleStatusBadge.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useAnalysisStore } from "@/stores/analysis"

const route = useRoute()
const router = useRouter()
const store = useAnalysisStore()
const error = ref("")
const caseId = computed(() => String(route.params.id))
const ruleLabels: Record<string, string> = {
  "skills.coverage": "技能与技术栈",
  "experience.minimum_years": "最低经验年限",
  "location_work_mode.compatibility": "地点与工作方式",
  "degree.minimum": "学历要求",
}
const sourceLabels = {
  candidate_profile: "用户主档",
  job_requirement_snapshot: "岗位要求",
}

async function load(): Promise<void> {
  error.value = ""
  try {
    await store.fetchAnalysis(caseId.value)
  } catch (reason) {
    error.value = userMessage(reason)
  }
}

async function generateReport(): Promise<void> {
  error.value = ""
  try {
    const report = await store.generateReport(caseId.value)
    await router.push({ name: "report-detail", params: { id: report.id } })
  } catch (reason) {
    error.value = userMessage(reason)
  }
}

watch(caseId, () => void load(), { immediate: true })
</script>

<template>
  <AppShell>
    <RouterLink
      class="back-link"
      to="/analysis/new"
    >
      <ArrowLeft :size="16" /> 返回分析创建
    </RouterLink>
    <StatePanel
      v-if="store.analyzing && !store.analysis"
      mode="loading"
      title="正在执行确定性规则"
      message="规则在当前请求中同步完成。"
    />
    <StatePanel
      v-else-if="error"
      mode="error"
      title="分析失败"
      :message="error"
      @retry="load"
    />
    <template v-else-if="store.analysis">
      <section class="analysis-result-header">
        <div>
          <p class="eyebrow">
            同步分析结果
          </p>
          <h2>确定性规则已执行</h2>
          <p>案例 {{ store.analysis.decision.id }} · {{ store.analysis.rule_set_version }}</p>
        </div>
        <div class="detail-actions">
          <span class="analysis-mode-badge"><ShieldCheck :size="16" /> AI 增强未启用</span>
          <button
            class="button button-secondary button-small"
            type="button"
            @click="load"
          >
            <RefreshCw :size="16" /> 刷新
          </button>
        </div>
      </section>

      <section
        class="analysis-rule-list"
        aria-label="规则分析结果"
      >
        <article
          v-for="result in store.analysis.rule_results"
          :key="result.rule_id"
          class="analysis-rule-row"
        >
          <div class="analysis-rule-main">
            <div class="report-item-title">
              <strong>{{ ruleLabels[result.rule_id] || result.rule_id }}</strong>
              <RuleStatusBadge :status="result.status" />
            </div>
            <p>{{ result.reason }}</p>
            <p
              v-if="result.uncertainty"
              class="rule-note"
            >
              {{ result.uncertainty }}
            </p>
            <p
              v-if="result.suggestion"
              class="rule-suggestion"
            >
              {{ result.suggestion }}
            </p>
          </div>
          <div class="analysis-references">
            <span
              v-for="reference in result.input_references"
              :key="`${reference.source}-${reference.field_path}`"
            >
              {{ sourceLabels[reference.source] }} v{{ reference.version }}<small>{{ reference.field_path }}</small>
            </span>
          </div>
        </article>
      </section>

      <section class="analysis-next-step">
        <div>
          <p class="eyebrow">
            版本化输出
          </p>
          <h3>生成决策报告</h3>
          <p>把本次规则结果固化为包含事实、未知项、建议和字段引用的不可变报告。</p>
        </div>
        <button
          class="button button-primary"
          type="button"
          :disabled="store.generating"
          @click="generateReport"
        >
          <FileText :size="17" />{{ store.generating ? '正在生成报告' : '生成报告' }}
        </button>
      </section>
    </template>
  </AppShell>
</template>
