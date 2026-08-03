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
