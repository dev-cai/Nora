<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ArrowRight, ClipboardList, Plus } from "lucide-vue-next"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useApplicationsStore } from "@/stores/applications"

const store = useApplicationsStore()
const error = ref("")
const statusLabels = {
  planned: "待确认",
  applied: "已投递",
  interviewing: "面试中",
  offer_received: "已获 Offer",
  rejected: "未通过",
  withdrawn: "已撤回",
} as const

async function load(): Promise<void> {
  error.value = ""
  try { await store.fetchRecords() }
  catch (reason) { error.value = userMessage(reason) }
}

onMounted(load)
</script>

<template>
  <AppShell>
    <section class="section-toolbar page-toolbar">
      <div>
        <p class="eyebrow">
          手工投递流水
        </p>
        <h2>投递记录</h2>
        <p>共 {{ store.total }} 条记录</p>
      </div>
      <RouterLink
        class="button button-primary"
        to="/templates"
      >
        <Plus :size="17" /> 选择定制简历
      </RouterLink>
    </section>
    <StatePanel
      v-if="store.loading"
      mode="loading"
      title="正在读取投递记录"
    />
    <StatePanel
      v-else-if="error"
      mode="error"
      title="无法读取投递记录"
      :message="error"
      @retry="load"
    />
    <StatePanel
      v-else-if="store.records.length === 0"
      mode="empty"
      title="暂无投递记录"
      message="从一份定制简历创建待确认记录。"
    />
    <div
      v-else
      class="application-list"
    >
      <RouterLink
        v-for="record in store.records"
        :key="record.id"
        class="application-row"
        :to="`/applications/${record.id}`"
      >
        <span class="metric-icon green"><ClipboardList :size="19" /></span>
        <span class="application-row-main">
          <strong>{{ statusLabels[record.status] }}</strong>
          <small>定制简历 {{ record.resume_variant_id }} · v{{ record.resume_variant_version }}</small>
        </span>
        <span class="application-row-meta">
          <time>{{ new Date(record.updated_at).toLocaleString('zh-CN') }}</time>
          <small>记录 v{{ record.version }}</small>
        </span>
        <ArrowRight :size="17" />
      </RouterLink>
    </div>
  </AppShell>
</template>
