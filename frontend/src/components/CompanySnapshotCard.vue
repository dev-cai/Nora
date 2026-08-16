<script setup lang="ts">
import { computed } from "vue"
import { AlertTriangle, Building2, Clock3, Link2, ShieldCheck } from "lucide-vue-next"

import type { CompanyAssessment, CompanyFieldStatus, CompanySnapshot } from "@/api/types"

const props = defineProps<{
  snapshot: CompanySnapshot
  assessment?: Pick<CompanyAssessment, "status" | "status_reason"> | null
}>()

const fieldLabels: Record<CompanyFieldStatus, string> = {
  confirmed: "已确认",
  unconfirmed: "待确认",
  unknown: "未知",
  conflicted: "存在冲突",
  superseded: "已被替代",
}
const freshnessLabels = {
  fresh: "新鲜",
  aging: "临近过期",
  stale: "已过期",
  unknown: "时效未知",
}
const tierLabels = {
  "official/company": "公司官方",
  reputable_media: "可信媒体",
  verified_platform: "已验证平台",
  anonymous_platform: "匿名平台",
}
const assessmentLabels = {
  available: "可用",
  unknown: "信息不足",
  conflicted: "存在冲突",
  stale: "已过期",
}

const anonymous = computed(() => props.snapshot.source.tier === "anonymous_platform")
const shortenedHash = (value: string) => `${value.slice(0, 12)}…${value.slice(-8)}`
</script>

<template>
  <article class="company-snapshot-card">
    <header class="company-card-heading">
      <span class="metric-icon green"><Building2 :size="18" /></span>
      <div>
        <p class="eyebrow">
          CompanySnapshot · v{{ snapshot.version }}
        </p>
        <h3>{{ snapshot.company_name }}</h3>
      </div>
      <span
        class="company-freshness"
        :class="`freshness-${snapshot.freshness}`"
      >
        <Clock3 :size="14" /> {{ freshnessLabels[snapshot.freshness] }}
      </span>
    </header>

    <div
      v-if="assessment"
      class="company-assessment-state"
      :class="`assessment-${assessment.status}`"
    >
      <ShieldCheck
        v-if="assessment.status === 'available'"
        :size="16"
      />
      <AlertTriangle
        v-else
        :size="16"
      />
      <span>报告评估：{{ assessmentLabels[assessment.status] }} · {{ assessment.status_reason }}</span>
    </div>

    <dl class="company-facts">
      <div>
        <dt>公司规模</dt>
        <dd>{{ snapshot.size || '未提供' }} <span :class="`field-${snapshot.size_status}`">{{ fieldLabels[snapshot.size_status] }}</span></dd>
      </div>
      <div>
        <dt>行业</dt>
        <dd>{{ snapshot.industry || '未提供' }} <span :class="`field-${snapshot.industry_status}`">{{ fieldLabels[snapshot.industry_status] }}</span></dd>
      </div>
      <div class="company-summary-fact">
        <dt>{{ anonymous ? '匿名来源摘要（非事实）' : '来源摘要' }}</dt>
        <dd>{{ snapshot.review_summary || '未提供' }} <span :class="`field-${snapshot.review_status}`">{{ fieldLabels[snapshot.review_status] }}</span></dd>
      </div>
    </dl>

    <footer class="company-source-meta">
      <div><Link2 :size="14" /><span>{{ tierLabels[snapshot.source.tier] }} · {{ snapshot.source.kind }} · {{ snapshot.source.acquisition_method }}</span></div>
      <div><span>来源 v{{ snapshot.source.version }} · 获取 {{ new Date(snapshot.source.acquired_at).toLocaleString('zh-CN') }}</span></div>
      <div><span>发布 {{ snapshot.source.published_at ? new Date(snapshot.source.published_at).toLocaleString('zh-CN') : '未知' }} · 许可 {{ snapshot.source.license_note }}</span></div>
      <div><code :title="snapshot.source.content_sha256">来源 {{ shortenedHash(snapshot.source.content_sha256) }}</code><code :title="snapshot.content_sha256">快照 {{ shortenedHash(snapshot.content_sha256) }}</code></div>
    </footer>
  </article>
</template>
