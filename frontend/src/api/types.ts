import type { components } from "./generated/schema"

export interface User {
  id: string
  username: string
  email: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface JobPosting {
  id: string
  jd_text: string
  job_title: string
  company_name: string
  location: string
  summary: string
  source_type: "manual" | "url"
  source_url: string | null
  status: "active" | "archived"
  version: number
  created_at: string
}

export interface JobPostingList {
  items: JobPosting[]
  page: number
  page_size: number
  total: number
}

export interface CreateJobPostingInput {
  jd_text: string
  job_title: string
  company_name: string
  location: string
  source_type: "manual"
}

export type ConfirmationStatus = "unconfirmed" | "confirmed" | "rejected" | "superseded"

export interface ProfileFact<T> {
  value: T
  confirmation_status: ConfirmationStatus
  source_type: "user_input"
  updated_at: string
}

export interface ProfileFactInput<T> {
  value: T
  confirmation_status: ConfirmationStatus
}

export interface EducationInput {
  id: string
  school: ProfileFactInput<string>
  degree: ProfileFactInput<string>
  major: ProfileFactInput<string>
  start_date: ProfileFactInput<string | null>
  end_date: ProfileFactInput<string | null>
}

export interface ExperienceInput {
  id: string
  company: ProfileFactInput<string>
  job_title: ProfileFactInput<string>
  start_date: ProfileFactInput<string | null>
  end_date: ProfileFactInput<string | null>
  responsibilities: ProfileFactInput<string[]>
  achievements: ProfileFactInput<string[]>
}

export interface SkillInput {
  id: string
  name: ProfileFactInput<string>
  proficiency: ProfileFactInput<string | null>
  years: ProfileFactInput<number | null>
}

export interface CandidateProfileInput {
  basic_information: {
    display_name: ProfileFactInput<string>
    current_location: ProfileFactInput<string>
  }
  preferences: {
    target_locations: ProfileFactInput<string[]>
    accepts_remote: ProfileFactInput<boolean>
    target_roles: ProfileFactInput<string[]>
  }
  education: EducationInput[]
  experiences: ExperienceInput[]
  skills: SkillInput[]
}

export type CandidateProfileContent = {
  basic_information: {
    display_name: ProfileFact<string>
    current_location: ProfileFact<string>
  }
  preferences: {
    target_locations: ProfileFact<string[]>
    accepts_remote: ProfileFact<boolean>
    target_roles: ProfileFact<string[]>
  }
  education: Array<{ id: string } & { [K in Exclude<keyof EducationInput, "id">]: ProfileFact<EducationInput[K]["value"]> }>
  experiences: Array<{ id: string } & { [K in Exclude<keyof ExperienceInput, "id">]: ProfileFact<ExperienceInput[K]["value"]> }>
  skills: Array<{ id: string } & { [K in Exclude<keyof SkillInput, "id">]: ProfileFact<SkillInput[K]["value"]> }>
}

export interface CandidateProfile {
  id: string
  owner_id: string
  version: number
  content: CandidateProfileContent
  created_at: string
  updated_at: string
}

export interface ResumeVersion {
  id: string
  owner_id: string
  version: number
  candidate_profile_id: string
  profile_version: number
  title: string
  content: Record<string, unknown>
  published_at: string
}

export interface ResumeVersionList {
  items: ResumeVersion[]
  page: number
  page_size: number
  total: number
}

export type RequirementConfirmationStatus = "unknown" | "unconfirmed" | "confirmed"
export type RequirementSourceType = "manual" | "text_range" | "ocr_preview"
export type WorkMode = "onsite" | "hybrid" | "remote"

export interface JobRequirementFact<T> {
  value: T
  confirmation_status: RequirementConfirmationStatus
  source_type: RequirementSourceType
  source_range: string | null
}

export interface JobRequirementContent {
  required_skills: JobRequirementFact<string[] | null>
  minimum_experience_years: JobRequirementFact<number | null>
  degree_requirement: JobRequirementFact<string | null>
  location_requirement: JobRequirementFact<string | null>
  work_mode: JobRequirementFact<WorkMode | null>
}

export interface JobRequirementSnapshot {
  id: string
  job_posting_id: string
  job_posting_version: number
  version: number
  content: JobRequirementContent
  content_hash: string
  created_at: string
  updated_at: string
}

export interface JobRequirementSnapshotList {
  items: JobRequirementSnapshot[]
  page: number
  page_size: number
  total: number
}

export interface JobRequirementSaveInput {
  content: JobRequirementContent
  job_posting_version: number
}

export type DecisionCaseStatus = "created" | "completed" | "failed"
export type RuleStatus = "match" | "partial" | "mismatch" | "unknown"
export type RuleInputSource = "candidate_profile" | "job_requirement_snapshot"

export interface CreateDecisionCaseInput {
  job_posting_id: string
  job_posting_version: number
  job_requirement_snapshot_id: string
  job_requirement_snapshot_version: number
  candidate_profile_id: string
  candidate_profile_version: number
  resume_version_id: string
  resume_version: number
}

export interface DecisionCase {
  id: string
  job_posting_id: string
  job_posting_version: number
  job_requirement_snapshot_id: string
  job_requirement_snapshot_version: number
  candidate_profile_id: string
  candidate_profile_version: number
  resume_version_id: string
  resume_version: number
  rule_set_version: string
  status: DecisionCaseStatus
  created_at: string
  completed_at: string | null
  failure_code: string | null
  failure_message: string | null
}

export interface RuleInputReference {
  source: RuleInputSource
  object_id: string
  version: number
  field_path: string
}

export interface RuleResult {
  rule_id: string
  rule_version: string
  status: RuleStatus
  input_references: RuleInputReference[]
  reason: string
  uncertainty: string | null
  suggestion: string | null
}

export interface DecisionAnalysis {
  decision: DecisionCase
  rule_set_version: string
  rule_results: RuleResult[]
}

export interface ReportCitation {
  citation_id: string
  source: RuleInputSource
  object_id: string
  version: number
  field_path: string
}

export interface ReportFact {
  fact_id: string
  label: string
  citation_ids: string[]
}

export interface ReportRuleResult {
  rule_id: string
  rule_version: string
  status: RuleStatus
  reason: string
  citation_ids: string[]
}

export interface ReportUnknown {
  unknown_id: string
  reason: string
  detail: string
  citation_ids: string[]
}

export interface ReportRecommendation {
  recommendation_id: string
  action: string
  rationale: string
  source_rule_id: string
}

export interface DecisionReport {
  id: string
  decision_case_id: string
  version: number
  rule_set_version: string
  generator_version: string
  summary: Record<RuleStatus, number>
  facts: ReportFact[]
  rule_results: ReportRuleResult[]
  unknowns: ReportUnknown[]
  recommendations: ReportRecommendation[]
  citations: ReportCitation[]
  satisfied_conditions: string[]
  gaps: string[]
  risks: string[]
  next_steps: string[]
  generated_at: string
  company_assessment?: CompanyAssessment | null
}

export interface DecisionReportList {
  items: DecisionReport[]
  page: number
  page_size: number
  total: number
}

export type Artifact = components["schemas"]["ArtifactResponse"]
export type SourceDocument = components["schemas"]["SourceResponse"]
export type CreateSourceInput = components["schemas"]["CreateSourceRequest"]
export type CompanyFieldStatus = components["schemas"]["CompanyFieldStatus"]
export type CompanySourceTier = components["schemas"]["CompanySourceTier"]
export type CompanyFreshness = components["schemas"]["Freshness"]
export type CompanySnapshot = components["schemas"]["CompanySnapshotResponse"]
export type CreateCompanySnapshotInput = components["schemas"]["CreateCompanySnapshotRequest"]
export type AppendCompanySnapshotInput = components["schemas"]["AppendCompanySnapshotRequest"]
export type CompanyAssessment = components["schemas"]["CompanyAssessmentResponse"]
export type CreateCompanyAssessmentInput = components["schemas"]["CreateCompanyAssessmentRequest"]

export type ApplicationDecisionStatus = "apply" | "skip"

export interface CreateApplicationDecisionInput {
  status: ApplicationDecisionStatus
  reason: string | null
}

export interface ApplicationDecision {
  id: string
  report_id: string
  report_version: number
  decision_case_id: string
  resume_version_id: string
  resume_version: number
  status: ApplicationDecisionStatus
  reason: string | null
  actor_id: string
  decided_at: string
}

export interface TemplateDefinition {
  id: string
  version: number
  name: string
  page_size: "a4" | "letter"
  density: "compact" | "standard"
  accent: "neutral" | "blue"
  section_order: string[]
  allowed_fields: string[]
  required_fields: string[]
  definition_hash: string
  published_at: string
}

export interface VariantBlock {
  source_path: string
  label: string
  value: string
}

export interface CreateResumeVariantInput {
  application_decision_id: string
  template_id: string
  template_version: number
  title: string
  blocks: VariantBlock[]
}

export interface ResumeVariant extends CreateResumeVariantInput {
  id: string
  version: number
  decision_case_id: string
  job_posting_id: string
  job_posting_version: number
  job_requirement_snapshot_id: string
  job_requirement_snapshot_version: number
  resume_version_id: string
  resume_version: number
  generator_version: string
  content_fingerprint: string
  created_at: string
}

export interface ResumeVariantList {
  items: ResumeVariant[]
  page: number
  page_size: number
  total: number
}

export type ResumePdfStatus = "pending" | "available" | "failed"

export interface ResumePdf {
  id: string
  version: number
  resume_variant_id: string
  resume_variant_version: number
  template_id: string
  template_version: number
  template_definition_hash: string
  variant_content_fingerprint: string
  renderer_version: string
  font_set_version: string
  locale: string
  timezone: string
  generation_identity: string
  status: ResumePdfStatus
  artifact_id: string | null
  artifact_version: number | null
  artifact_sha256: string | null
  artifact_size_bytes: number | null
  created_at: string
  updated_at: string
}

export type MessageDraftStyle = "professional" | "concise" | "referral"
export type MessageDraftRevisionType = "generated" | "edited"

export interface GenerateMessageDraftInput {
  style: MessageDraftStyle
  user_note: string | null
  referral_context: string | null
}

export interface EditMessageDraftInput {
  base_version: number
  text: string
}

export interface MessageDraft {
  id: string
  version: number
  application_decision_id: string
  report_id: string
  report_version: number
  decision_case_id: string
  resume_variant_id: string
  resume_variant_version: number
  variant_content_fingerprint: string
  candidate_profile_id: string
  candidate_profile_version: number
  resume_version_id: string
  resume_version: number
  job_posting_id: string
  job_posting_version: number
  company_snapshot_id: string | null
  company_snapshot_version: number | null
  company_snapshot_hash: string | null
  company_freshness: string | null
  style: MessageDraftStyle
  user_note: string | null
  referral_context: string | null
  generator_version: string
  template_version: string
  generation_identity: string
  text: string
  content_fingerprint: string
  revision_type: MessageDraftRevisionType
  previous_version: number | null
  created_at: string
}

export interface MessageDraftList {
  items: MessageDraft[]
  page: number
  page_size: number
  total: number
}

export type ApplicationRecordStatus =
  | "planned"
  | "applied"
  | "interviewing"
  | "offer_received"
  | "rejected"
  | "withdrawn"

export interface CreateApplicationRecordInput {
  application_decision_id: string
  resume_variant_id: string
  resume_pdf_id: string | null
  message_draft_id: string | null
  message_draft_version: number | null
}

export interface TransitionApplicationRecordInput {
  base_version: number
  to_status: ApplicationRecordStatus
  occurred_at: string
  channel: string | null
  note: string | null
}

export interface ApplicationRecord {
  id: string
  version: number
  status: ApplicationRecordStatus
  application_decision_id: string
  decision_case_id: string
  resume_variant_id: string
  resume_variant_version: number
  variant_content_fingerprint: string
  resume_pdf_id: string | null
  resume_pdf_version: number | null
  artifact_id: string | null
  artifact_version: number | null
  artifact_sha256: string | null
  message_draft_id: string | null
  message_draft_version: number | null
  message_content_fingerprint: string | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface ApplicationRecordTransition {
  id: string
  record_version: number
  actor_id: string
  from_status: ApplicationRecordStatus
  to_status: ApplicationRecordStatus
  source: "user_confirmation"
  channel: string | null
  note: string | null
  occurred_at: string
  recorded_at: string
}

export interface ApplicationRecordList {
  items: ApplicationRecord[]
  page: number
  page_size: number
  total: number
}
