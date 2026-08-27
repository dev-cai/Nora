import { mount } from "@vue/test-utils"

import type { JobFitAnalysis } from "@/api/types"
import JobFitAnalysisPanel from "@/components/JobFitAnalysisPanel.vue"

const analysis: JobFitAnalysis = {
  id: "job-fit-1",
  report_id: "report-1",
  report_version: 1,
  decision_case_id: "case-1",
  version: 1,
  prompt_version: "job-fit-v1",
  provider: "deepseek",
  model: "deepseek-v4-flash",
  generator_version: "job-fit-analysis-v1",
  generation_identity: "a".repeat(64),
  overall_fit: "moderate",
  overall_fit_reason: {
    text: "搜索 API 经验可以迁移，但向量检索证据不足。",
    citation_ids: ["experience", "required"],
  },
  strong_matches: [],
  transferable_evidence: [{
    text: "搜索 API 的接口与性能经验可迁移到向量检索服务。",
    citation_ids: ["experience", "required"],
  }],
  critical_gaps: [],
  non_blocking_gaps: [],
  resume_actions: [{ text: "补充搜索 API 的量化结果。", citation_ids: ["experience"] }],
  project_deep_dive_risks: [],
  interview_focus: [],
  unknowns: [{ text: "缺少真实向量检索项目证据。", citation_ids: ["required"] }],
  citations: [
    { citation_id: "experience", source: "candidate_profile", object_id: "profile-1", version: 3, field_path: "experiences" },
    { citation_id: "required", source: "job_requirement_snapshot", object_id: "requirement-1", version: 2, field_path: "required_skills" },
  ],
  generated_at: "2026-08-12T00:00:04Z",
}

describe("job fit analysis panel", () => {
  it("separates inference, advice and unknowns with fixed-input citations", () => {
    const wrapper = mount(JobFitAnalysisPanel, { props: { analysis } })

    expect(wrapper.text()).toContain("可迁移证据")
    expect(wrapper.text()).toContain("模型推断")
    expect(wrapper.text()).toContain("建议")
    expect(wrapper.text()).toContain("未知")
    expect(wrapper.text()).toContain("用户主档 v3 · 工作经历")
    expect(wrapper.text()).toContain("岗位要求 v2 · 必需技能")
  })
})
