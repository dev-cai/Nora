import { mount } from "@vue/test-utils"

import type { DecisionReport } from "@/api/types"
import ReportContent from "@/components/ReportContent.vue"

const report: DecisionReport = {
  id: "report-1",
  decision_case_id: "case-1",
  version: 1,
  rule_set_version: "m3-rules-v1",
  generator_version: "m3-report-v1",
  summary: { match: 1, partial: 0, mismatch: 0, unknown: 1 },
  facts: [{ fact_id: "fact-1", label: "已确认岗位技能", citation_ids: ["citation-1"] }],
  rule_results: [{
    rule_id: "skills.coverage",
    rule_version: "1",
    status: "match",
    reason: "技能完全覆盖。",
    citation_ids: ["citation-1"],
  }],
  unknowns: [{
    unknown_id: "unknown-1",
    reason: "经验年限未知",
    detail: "缺少 confirmed 的经验输入。",
    citation_ids: ["citation-2"],
  }],
  recommendations: [{
    recommendation_id: "recommendation-1",
    action: "确认经验年限",
    rationale: "补齐后可重新分析。",
    source_rule_id: "experience.minimum_years",
  }],
  citations: [
    { citation_id: "citation-1", source: "job_requirement_snapshot", object_id: "requirements-1", version: 2, field_path: "required_skills" },
    { citation_id: "citation-2", source: "candidate_profile", object_id: "profile-1", version: 3, field_path: "experiences[*]" },
  ],
  satisfied_conditions: ["技能完全覆盖"],
  gaps: [],
  risks: ["经验输入不完整"],
  next_steps: ["确认经验年限"],
  generated_at: "2026-08-12T00:00:00Z",
}

describe("ReportContent", () => {
  it("renders report sections, statuses, and field-level citations", () => {
    const wrapper = mount(ReportContent, { props: { report } })

    expect(wrapper.text()).toContain("事实")
    expect(wrapper.text()).toContain("技能与技术栈")
    expect(wrapper.text()).toContain("满足")
    expect(wrapper.text()).toContain("未知项")
    expect(wrapper.text()).toContain("建议")
    expect(wrapper.text()).toContain("岗位要求 v2 · required_skills")
    expect(wrapper.text()).toContain("用户主档 v3 · experiences[*]")
  })
})
