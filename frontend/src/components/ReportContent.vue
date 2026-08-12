<script setup lang="ts">
import { computed } from "vue"
import { AlertTriangle, CheckCircle2, CircleHelp, Lightbulb, Link2 } from "lucide-vue-next"

import type { DecisionReport, ReportCitation } from "@/api/types"
import RuleStatusBadge from "@/components/RuleStatusBadge.vue"

const props = defineProps<{ report: DecisionReport }>()

const citationMap = computed(() => new Map(props.report.citations.map((item) => [item.citation_id, item])))
const sourceLabels = {
  candidate_profile: "用户主档",
  job_requirement_snapshot: "岗位要求",
}
const ruleLabels: Record<string, string> = {
  "skills.coverage": "技能与技术栈",
  "experience.minimum_years": "最低经验年限",
  "location_work_mode.compatibility": "地点与工作方式",
  "degree.minimum": "学历要求",
}

function citations(ids: string[]): ReportCitation[] {
  return ids.flatMap((id) => {
    const citation = citationMap.value.get(id)
    return citation ? [citation] : []
  })
}

function citationLabel(citation: ReportCitation): string {
  return `${sourceLabels[citation.source]} v${citation.version} · ${citation.field_path}`
}
</script>

<template>
  <section
    class="report-summary"
    aria-label="报告结果汇总"
  >
    <article class="summary-cell summary-match">
      <strong>{{ report.summary.match }}</strong><span>满足</span>
    </article>
    <article class="summary-cell summary-partial">
      <strong>{{ report.summary.partial }}</strong><span>部分满足</span>
    </article>
    <article class="summary-cell summary-mismatch">
      <strong>{{ report.summary.mismatch }}</strong><span>不满足</span>
    </article>
    <article class="summary-cell summary-unknown">
      <strong>{{ report.summary.unknown }}</strong><span>未知</span>
    </article>
  </section>

  <section class="report-section">
    <div class="report-section-heading">
      <CheckCircle2 :size="19" />
      <div><h3>事实</h3><p>报告采用的已确认版本化输入。</p></div>
    </div>
    <div class="report-items">
      <article
        v-for="fact in report.facts"
        :key="fact.fact_id"
        class="report-item"
      >
        <strong>{{ fact.label }}</strong>
        <div class="citation-list">
          <span
            v-for="citation in citations(fact.citation_ids)"
            :key="citation.citation_id"
          ><Link2 :size="13" />{{ citationLabel(citation) }}</span>
        </div>
      </article>
    </div>
  </section>

  <section class="report-section">
    <div class="report-section-heading">
      <CheckCircle2 :size="19" />
      <div><h3>规则结果</h3><p>四类确定性规则及其字段级来源。</p></div>
    </div>
    <div class="report-items">
      <article
        v-for="result in report.rule_results"
        :key="result.rule_id"
        class="report-item rule-report-item"
      >
        <div class="report-item-title">
          <strong>{{ ruleLabels[result.rule_id] || result.rule_id }}</strong>
          <RuleStatusBadge :status="result.status" />
        </div>
        <p>{{ result.reason }}</p>
        <div class="citation-list">
          <span
            v-for="citation in citations(result.citation_ids)"
            :key="citation.citation_id"
          ><Link2 :size="13" />{{ citationLabel(citation) }}</span>
        </div>
      </article>
    </div>
  </section>

  <section
    v-if="report.unknowns.length"
    class="report-section"
  >
    <div class="report-section-heading report-heading-unknown">
      <CircleHelp :size="19" />
      <div><h3>未知项</h3><p>输入不足时保持未知，不进行推断。</p></div>
    </div>
    <div class="report-items">
      <article
        v-for="unknown in report.unknowns"
        :key="unknown.unknown_id"
        class="report-item"
      >
        <strong>{{ unknown.reason }}</strong>
        <p>{{ unknown.detail }}</p>
        <div class="citation-list">
          <span
            v-for="citation in citations(unknown.citation_ids)"
            :key="citation.citation_id"
          ><Link2 :size="13" />{{ citationLabel(citation) }}</span>
        </div>
      </article>
    </div>
  </section>

  <section
    v-if="report.recommendations.length"
    class="report-section"
  >
    <div class="report-section-heading report-heading-advice">
      <Lightbulb :size="19" />
      <div><h3>建议</h3><p>由规则结果确定性生成，不是录用概率。</p></div>
    </div>
    <div class="report-items">
      <article
        v-for="recommendation in report.recommendations"
        :key="recommendation.recommendation_id"
        class="report-item"
      >
        <strong>{{ recommendation.action }}</strong>
        <p>{{ recommendation.rationale }}</p>
      </article>
    </div>
  </section>

  <section
    v-if="report.risks.length"
    class="report-section"
  >
    <div class="report-section-heading report-heading-risk">
      <AlertTriangle :size="19" />
      <div><h3>风险</h3><p>需要在做决定前核实的事项。</p></div>
    </div>
    <ul class="report-bullet-list">
      <li
        v-for="risk in report.risks"
        :key="risk"
      >
        {{ risk }}
      </li>
    </ul>
  </section>
</template>
