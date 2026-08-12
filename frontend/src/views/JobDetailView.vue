<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ArrowLeft, Building2, CalendarDays, ChartNoAxesCombined, MapPin, ShieldCheck } from "lucide-vue-next"
import { useRoute } from "vue-router"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useJobsStore } from "@/stores/jobs"

const route = useRoute()
const store = useJobsStore()
const error = ref("")
async function load(): Promise<void> {
  error.value = ""
  try { await store.fetchJob(String(route.params.id)) } catch (reason) { error.value = userMessage(reason) }
}
onMounted(load)
</script>

<template>
  <AppShell>
    <RouterLink
      class="back-link"
      to="/jobs"
    >
      <ArrowLeft :size="16" /> 返回岗位库
    </RouterLink>
    <StatePanel
      v-if="error"
      mode="error"
      title="无法读取岗位"
      :message="error"
      @retry="load"
    />
    <StatePanel
      v-else-if="store.isLoading || !store.current"
      mode="loading"
      title="正在读取岗位"
    />
    <template v-else>
      <section class="detail-header">
        <div><span class="status-dot">有效快照</span><h2>{{ store.current.job_title }}</h2><p>{{ store.current.company_name }}</p></div>
        <div class="detail-actions">
          <span class="version-badge">版本 {{ store.current.version }}</span>
          <RouterLink
            class="button button-primary button-small"
            :to="{ name: 'job-requirements', params: { id: store.current.id } }"
          >
            确认岗位要求
          </RouterLink>
          <RouterLink
            class="button button-secondary button-small"
            :to="{ name: 'analysis-new', query: { jobId: store.current.id } }"
          >
            <ChartNoAxesCombined :size="16" /> 发起分析
          </RouterLink>
        </div>
      </section>
      <section class="detail-meta">
        <span><Building2 :size="16" /> {{ store.current.company_name }}</span>
        <span><MapPin :size="16" /> {{ store.current.location }}</span>
        <span><CalendarDays :size="16" /> {{ new Date(store.current.created_at).toLocaleString('zh-CN') }}</span>
        <span><ShieldCheck :size="16" /> 用户隔离</span>
      </section>
      <section class="content-section detail-content">
        <div class="section-toolbar">
          <div>
            <p class="eyebrow">
              原始事实
            </p><h2>岗位描述</h2>
          </div>
        </div><pre>{{ store.current.jd_text }}</pre>
      </section>
      <section class="locked-band">
        <ShieldCheck :size="18" /><div><strong>这是不可变岗位快照</strong><p>后续分析会引用当前版本，不会静默改写原始 JD。</p></div>
      </section>
    </template>
  </AppShell>
</template>
