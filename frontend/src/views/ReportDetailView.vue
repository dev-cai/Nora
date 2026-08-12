<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowLeft, RefreshCw, ShieldCheck } from "lucide-vue-next"
import { useRoute } from "vue-router"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import DecisionBar from "@/components/DecisionBar.vue"
import ReportContent from "@/components/ReportContent.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useAnalysisStore } from "@/stores/analysis"

const route = useRoute()
const store = useAnalysisStore()
const loadError = ref("")
const decisionError = ref("")
const reportId = computed(() => String(route.params.id))

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
          <span class="analysis-mode-badge"><ShieldCheck :size="16" /> AI 增强未启用</span>
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
      <section class="locked-band">
        <ShieldCheck :size="18" />
        <div><strong>固定版本报告</strong><p>刷新会从服务端重新读取同一报告版本，不会重新计算或覆盖历史。</p></div>
      </section>
    </template>
  </AppShell>
</template>
