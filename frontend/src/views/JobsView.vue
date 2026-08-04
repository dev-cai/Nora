<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ArrowRight, BriefcaseBusiness, MapPin, Plus } from "lucide-vue-next"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useJobsStore } from "@/stores/jobs"

const store = useJobsStore()
const error = ref("")
async function load(): Promise<void> {
  error.value = ""
  try { await store.fetchJobs() } catch (reason) { error.value = userMessage(reason) }
}
onMounted(load)
</script>

<template>
  <AppShell>
    <section class="section-toolbar page-toolbar">
      <div>
        <p class="eyebrow">
          岗位事实源
        </p><h2>岗位库</h2><p>按创建时间倒序保存的原始 JD 快照。</p>
      </div>
      <RouterLink
        class="button button-primary"
        to="/jobs/new"
      >
        <Plus :size="17" /> 录入岗位
      </RouterLink>
    </section>
    <StatePanel
      v-if="error"
      mode="error"
      title="无法加载岗位"
      :message="error"
      @retry="load"
    />
    <StatePanel
      v-else-if="store.isLoading"
      mode="loading"
      title="正在加载岗位"
    />
    <StatePanel
      v-else-if="store.jobs.length === 0"
      mode="empty"
      title="岗位库还是空的"
      message="录入一份真实 JD 后，它会出现在这里。"
    />
    <section
      v-else
      class="job-grid"
      aria-label="岗位列表"
    >
      <RouterLink
        v-for="job in store.jobs"
        :key="job.id"
        class="job-card"
        :to="`/jobs/${job.id}`"
      >
        <div class="job-card-top">
          <span class="metric-icon green"><BriefcaseBusiness :size="18" /></span><span class="status-dot">有效</span>
        </div>
        <h3>{{ job.job_title }}</h3>
        <p class="company">
          {{ job.company_name }}
        </p>
        <p class="location">
          <MapPin :size="15" /> {{ job.location }}
        </p>
        <p class="summary">
          {{ job.summary }}
        </p>
        <div class="job-card-foot">
          <time>{{ new Date(job.created_at).toLocaleDateString('zh-CN') }}</time><span>查看详情 <ArrowRight :size="15" /></span>
        </div>
      </RouterLink>
    </section>
  </AppShell>
</template>
