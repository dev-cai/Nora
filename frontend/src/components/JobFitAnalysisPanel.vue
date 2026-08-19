<script setup lang="ts">
import { computed } from "vue"
import { CircleHelp, Link2, Lightbulb, Sparkles, TriangleAlert } from "lucide-vue-next"

import type { JobFitAnalysis, JobFitCitation, JobFitInsight } from "@/api/types"

const props = defineProps<{ analysis: JobFitAnalysis }>()

interface InsightSection {
  key: string
  title: string
  description: string
  kind: "模型推断" | "建议" | "未知"
  tone: "inference" | "advice" | "risk" | "unknown"
  items: JobFitInsight[]
}

const citationMap = computed(
  () => new Map(props.analysis.citations.map((item) => [item.citation_id, item])),
)
const fitLabels = {
  strong: "高度匹配",
  moderate: "部分匹配",
  weak: "匹配较弱",
  unknown: "信息不足",
}
const sourceLabels = {
  candidate_profile: "用户主档",
  resume_version: "简历版本",
  job_posting: "岗位原文",
  job_requirement_snapshot: "岗位要求",
  decision_report: "确定性报告",
  company_snapshot: "公司情报",
}
const fieldLabels: Record<string, string> = {
  basic_information: "基本信息",
  preferences: "求职偏好",
  experiences: "工作经历",
  skills: "技能",
  education: "教育经历",
  content: "简历内容",
  jd_text: "JD 原文",
  job_title: "岗位名称",
  company_name: "公司名称",
  location: "工作地点",
  required_skills: "必需技能",
  minimum_experience_years: "最低经验年限",
  degree_requirement: "学历要求",
  location_requirement: "地点要求",
  work_mode: "工作方式",
  summary: "规则汇总",
  rule_results: "规则结果",
  gaps: "确定性缺口",
  risks: "确定性风险",
  size: "公司规模",
  industry: "所属行业",
  review_summary: "评价摘要",
}

const sections = computed<InsightSection[]>(() => {
  const values: InsightSection[] = [
    {
    key: "strong-matches",
    title: "强匹配",
    description: "模型从固定输入中识别的直接相关证据。",
    kind: "模型推断",
    tone: "inference",
    items: props.analysis.strong_matches,
  },
  {
    key: "transferable-evidence",
    title: "可迁移证据",
    description: "不依赖关键词完全一致的能力迁移判断。",
    kind: "模型推断",
    tone: "inference",
    items: props.analysis.transferable_evidence,
  },
  {
    key: "critical-gaps",
    title: "关键缺口",
    description: "可能直接影响岗位胜任的证据缺口。",
    kind: "模型推断",
    tone: "risk",
    items: props.analysis.critical_gaps,
  },
  {
    key: "non-blocking-gaps",
    title: "非阻塞缺口",
    description: "值得补强，但不应单独决定是否投递。",
    kind: "模型推断",
    tone: "risk",
    items: props.analysis.non_blocking_gaps,
  },
  {
    key: "resume-actions",
    title: "简历行动",
    description: "基于当前证据的简历表达建议。",
    kind: "建议",
    tone: "advice",
    items: props.analysis.resume_actions,
  },
  {
    key: "project-risks",
    title: "项目深挖风险",
    description: "面试中可能被继续追问的薄弱环节。",
    kind: "模型推断",
    tone: "risk",
    items: props.analysis.project_deep_dive_risks,
  },
  {
    key: "interview-focus",
    title: "面试准备",
    description: "建议优先准备的解释与证明材料。",
    kind: "建议",
    tone: "advice",
    items: props.analysis.interview_focus,
  },
  {
    key: "unknowns",
    title: "未知项",
    description: "固定输入不足，模型不能确认的事项。",
    kind: "未知",
    tone: "unknown",
    items: props.analysis.unknowns,
    },
  ]
  return values.filter((section) => section.items.length > 0)
})

function citations(ids: string[]): JobFitCitation[] {
  return ids.flatMap((id) => {
    const citation = citationMap.value.get(id)
    return citation ? [citation] : []
  })
}

function citationLabel(citation: JobFitCitation): string {
  const field = fieldLabels[citation.field_path] || citation.field_path
  return `${sourceLabels[citation.source]} v${citation.version} · ${field}`
}
</script>

<template>
  <div class="job-fit-analysis">
    <div class="job-fit-overall">
      <div>
        <span class="job-fit-kind">模型推断</span>
        <strong>{{ fitLabels[analysis.overall_fit] }}</strong>
      </div>
      <p>{{ analysis.overall_fit_reason.text }}</p>
      <div class="citation-list">
        <span
          v-for="citation in citations(analysis.overall_fit_reason.citation_ids)"
          :key="citation.citation_id"
        ><Link2 :size="13" />{{ citationLabel(citation) }}</span>
      </div>
    </div>

    <section
      v-for="section in sections"
      :key="section.key"
      class="job-fit-section"
      :class="`job-fit-${section.tone}`"
    >
      <div class="report-section-heading">
        <CircleHelp
          v-if="section.tone === 'unknown'"
          :size="19"
        />
        <Lightbulb
          v-else-if="section.tone === 'advice'"
          :size="19"
        />
        <TriangleAlert
          v-else-if="section.tone === 'risk'"
          :size="19"
        />
        <Sparkles
          v-else
          :size="19"
        />
        <div><h3>{{ section.title }}</h3><p>{{ section.description }}</p></div>
        <span class="job-fit-kind">{{ section.kind }}</span>
      </div>
      <div class="report-items">
        <article
          v-for="(insight, index) in section.items"
          :key="`${section.key}-${index}`"
          class="report-item"
        >
          <p class="job-fit-insight-text">
            {{ insight.text }}
          </p>
          <div class="citation-list">
            <span
              v-for="citation in citations(insight.citation_ids)"
              :key="citation.citation_id"
            ><Link2 :size="13" />{{ citationLabel(citation) }}</span>
          </div>
        </article>
      </div>
    </section>

    <p class="job-fit-generation-meta">
      AI 分析 v{{ analysis.version }} · {{ analysis.model }} ·
      {{ new Date(analysis.generated_at).toLocaleString('zh-CN') }}
    </p>
  </div>
</template>
