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

export interface ApiProblem {
  error_code?: string
  message?: string
  detail?: unknown
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
