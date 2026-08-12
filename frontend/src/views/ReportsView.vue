<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ArrowRight, FilePlus2, FileText, ShieldCheck } from "lucide-vue-next"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useAnalysisStore } from "@/stores/analysis"

const store = useAnalysisStore()
const error = ref("")

async function load(): Promise<void> {
  error.value = ""
  try {
    await store.fetchReports()
  } catch (reason) {
    error.value = userMessage(reason)
  }
}

onMounted(load)
</script>

<template>
  <AppShell>
    <section class="section-toolbar page-toolbar">
      <div>
        <p class="eyebrow">
          版本化决策记录
        </p>
        <h2>分析报告</h2>
        <p>按生成时间倒序读取，不可变版本可在刷新后恢复。</p>
      </div>
      <RouterLink
        class="button button-primary"
        to="/analysis/new"
      >
        <FilePlus2 :size="17" /> 发起分析
      </RouterLink>
    </section>
    <StatePanel
      v-if="error"
      mode="error"
      title="无法加载报告"
      :message="error"
      @retry="load"
    />
    <StatePanel
      v-else-if="store.listLoading"
      mode="loading"
      title="正在加载报告"
    />
    <StatePanel
      v-else-if="store.reports.length === 0"
      mode="empty"
      title="还没有分析报告"
      message="选择已经确认的岗位要求、主档与简历版本，发起第一份确定性分析。"
    />
    <section
      v-else
      class="report-list"
      aria-label="分析报告列表"
    >
      <RouterLink
        v-for="report in store.reports"
        :key="report.id"
        class="report-row"
        :to="`/reports/${report.id}`"
      >
        <span class="metric-icon green"><FileText :size="18" /></span>
        <span class="report-row-main">
          <strong>决策报告 v{{ report.version }}</strong>
          <small>{{ report.summary.match }} 满足 · {{ report.summary.partial }} 部分满足 · {{ report.summary.mismatch }} 不满足 · {{ report.summary.unknown }} 未知</small>
        </span>
        <span class="report-row-meta">
          <time>{{ new Date(report.generated_at).toLocaleString('zh-CN') }}</time>
          <span><ShieldCheck :size="14" /> 确定性规则</span>
        </span>
        <ArrowRight :size="17" />
      </RouterLink>
    </section>
  </AppShell>
</template>
