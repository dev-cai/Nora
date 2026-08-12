<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ArrowUpRight, BriefcaseBusiness, ChartNoAxesCombined, Sparkles } from "lucide-vue-next"
import { RouterLink } from "vue-router"

import { userMessage } from "@/api/client"
import StatePanel from "@/components/StatePanel.vue"
import { useAnalysisStore } from "@/stores/analysis"
import AppShell from "@/components/AppShell.vue"
import { useJobsStore } from "@/stores/jobs"

const jobs = useJobsStore()
const analysis = useAnalysisStore()
const error = ref("")
onMounted(async () => {
  try { await Promise.all([jobs.fetchJobs(1, 5), analysis.fetchReports(1, 5)]) } catch (reason) { error.value = userMessage(reason) }
})
</script>

<template>
  <AppShell>
    <section class="welcome-band">
      <div>
        <p class="eyebrow">
          今日焦点
        </p><h2>从一个清晰的岗位快照开始。</h2><p>把 JD、来源和上下文放在一起，后续的事实与决策才有可靠起点。</p>
      </div>
      <RouterLink
        class="button button-dark"
        to="/analysis/new"
      >
        发起适配分析 <ArrowUpRight :size="17" />
      </RouterLink>
    </section>
    <section
      class="metric-grid"
      aria-label="工作台概览"
    >
      <article class="metric">
        <span class="metric-icon green"><BriefcaseBusiness :size="18" /></span><span class="metric-label">岗位快照</span><strong>{{ jobs.total }}</strong><small>已保存到你的账号</small>
      </article>
      <article class="metric">
        <span class="metric-icon orange"><ChartNoAxesCombined :size="18" /></span><span class="metric-label">分析报告</span><strong>{{ analysis.total }}</strong><small>确定性版本记录</small>
      </article>
      <article class="metric">
        <span class="metric-icon blue"><Sparkles :size="18" /></span><span class="metric-label">主档与简历</span><strong>可管理</strong><small>维护你的求职资产</small>
      </article>
    </section>
    <section class="content-section">
      <div class="section-toolbar">
        <div>
          <p class="eyebrow">
            最近记录
          </p><h2>岗位快照</h2>
        </div><RouterLink
          class="inline-link"
          to="/jobs"
        >
          查看全部 <ArrowUpRight :size="15" />
        </RouterLink>
      </div>
      <StatePanel
        v-if="error"
        mode="error"
        title="岗位加载失败"
        :message="error"
        @retry="jobs.fetchJobs()"
      />
      <StatePanel
        v-else-if="jobs.isLoading"
        mode="loading"
        title="正在加载岗位"
      />
      <StatePanel
        v-else-if="jobs.jobs.length === 0"
        mode="empty"
        title="还没有岗位快照"
        message="录入第一份 JD，建立你的求职上下文。"
      />
      <div
        v-else
        class="job-list compact-list"
      >
        <RouterLink
          v-for="job in jobs.jobs"
          :key="job.id"
          class="job-row"
          :to="`/jobs/${job.id}`"
        >
          <span class="job-row-main"><strong>{{ job.job_title }}</strong><small>{{ job.company_name }} · {{ job.location }}</small></span><span class="job-row-meta">{{ new Date(job.created_at).toLocaleDateString('zh-CN') }} <ArrowUpRight :size="15" /></span>
        </RouterLink>
      </div>
    </section>
    <section class="locked-band">
      <ChartNoAxesCombined :size="18" />
      <div>
        <strong>从版本化输入生成报告</strong>
        <p>选择岗位要求、主档与简历版本，执行可追溯的确定性规则。</p>
        <div class="asset-links">
          <RouterLink
            class="inline-link"
            to="/analysis/new"
          >
            发起分析 <ArrowUpRight :size="15" />
          </RouterLink>
          <RouterLink
            class="inline-link"
            to="/reports"
          >
            查看报告历史 <ArrowUpRight :size="15" />
          </RouterLink>
        </div>
      </div>
    </section>
  </AppShell>
</template>
