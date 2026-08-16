<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ArrowRight, CalendarClock } from "lucide-vue-next"

import { userMessage } from "@/api/client"
import type { InterviewCaseStatus, InterviewMode } from "@/api/types"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useInterviewsStore } from "@/stores/interviews"

const store = useInterviewsStore()
const error = ref("")
const modeLabels: Record<InterviewMode, string> = {
  onsite: "线下面试",
  online: "线上面试",
  phone: "电话面试",
}
const statusLabels: Record<InterviewCaseStatus, string> = {
  scheduled: "已安排",
  cancelled: "已取消",
}

async function load(): Promise<void> {
  error.value = ""
  try { await store.fetchInterviews() }
  catch (reason) { error.value = userMessage(reason) }
}

onMounted(load)
</script>

<template>
  <AppShell>
    <section class="section-toolbar page-toolbar">
      <div>
        <p class="eyebrow">
          用户确认通知
        </p>
        <h2>面试安排</h2>
        <p>共 {{ store.total }} 条安排</p>
      </div>
    </section>
    <StatePanel
      v-if="store.loading"
      mode="loading"
      title="正在读取面试安排"
    />
    <StatePanel
      v-else-if="error"
      mode="error"
      title="无法读取面试安排"
      :message="error"
      @retry="load"
    />
    <StatePanel
      v-else-if="store.items.length === 0"
      mode="empty"
      title="暂无面试安排"
      message="在面试中的投递记录里添加通知。"
    />
    <div
      v-else
      class="interview-list"
    >
      <RouterLink
        v-for="interview in store.items"
        :key="interview.id"
        class="interview-row"
        :to="`/interviews/${interview.id}`"
      >
        <span class="metric-icon blue"><CalendarClock :size="19" /></span>
        <span class="interview-row-main">
          <strong>第 {{ interview.round_number }} 轮 · {{ modeLabels[interview.mode] }}</strong>
          <small>{{ statusLabels[interview.status] }} · {{ interview.timezone }}</small>
        </span>
        <span class="interview-row-meta">
          <time>{{ new Date(interview.starts_at).toLocaleString('zh-CN') }}</time>
          <small>安排 v{{ interview.version }}</small>
        </span>
        <ArrowRight :size="17" />
      </RouterLink>
    </div>
  </AppShell>
</template>
