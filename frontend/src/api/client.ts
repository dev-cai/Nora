import type {
  ApiProblem,
  CandidateProfile,
  CandidateProfileInput,
  CreateJobPostingInput,
  JobPosting,
  JobPostingList,
  JobRequirementSaveInput,
  JobRequirementSnapshot,
  JobRequirementSnapshotList,
  ResumeVersion,
  ResumeVersionList,
  TokenResponse,
  User,
} from "./types"

const apiBaseUrl = (import.meta.env.VITE_NORA_API_BASE_URL || "/api").replace(/\/$/, "")
let accessToken: string | null = null
let unauthorizedHandler: (() => void) | null = null
export const API_REQUEST_TIMEOUT_MS = 10_000

const fallbackMessages: Record<number, string> = {
  401: "登录状态已失效，请重新登录",
  404: "对象不存在或无权访问",
  409: "当前内容与服务端状态冲突",
  422: "提交内容未通过校验",
  503: "服务暂时不可用，请稍后重试",
}

const errorCodeMessages: Record<string, string> = {
  authentication_failed: "用户名或密码不正确",
  username_conflict: "该用户名已被使用",
  email_conflict: "该邮箱已被注册",
  idempotency_conflict: "本次请求与已有操作冲突",
  entity_not_found: "对象不存在或无权访问",
  database_unavailable: "服务暂时不可用，请稍后重试",
  network_timeout: "请求超时，请检查网络后重试",
  job_requirement_version_conflict: "岗位要求已更新，请刷新后重试",
  invalid_requirement: "岗位要求内容未通过校验",
  invalid_requirement_field: "岗位要求字段未通过校验",
  invalid_confirmation_status: "确认状态无效",
  invalid_source_type: "字段来源无效",
}

export class ApiError extends Error {
  readonly status: number
  readonly errorCode: string
  readonly requestId: string | null

  constructor(message: string, status = 0, errorCode = "network_error", requestId: string | null = null) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.errorCode = errorCode
    this.requestId = requestId
  }
}

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

export function userMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "发生未知错误，请重试"
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set("Accept", "application/json")
  if (init.body !== undefined) headers.set("Content-Type", "application/json")
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`)

  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), API_REQUEST_TIMEOUT_MS)
  const abortCaller = () => controller.abort()
  init.signal?.addEventListener("abort", abortCaller, { once: true })
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers, signal: controller.signal })
  } catch {
    if (controller.signal.aborted && !init.signal?.aborted) {
      throw new ApiError("请求超时，请检查网络后重试", 0, "network_timeout")
    }
    throw new ApiError("无法连接 Nora 服务，请检查网络后重试")
  } finally {
    window.clearTimeout(timeout)
    init.signal?.removeEventListener("abort", abortCaller)
  }

  const requestId = response.headers.get("X-Request-ID")
  if (!response.ok) {
    let problem: ApiProblem = {}
    try {
      problem = (await response.json()) as ApiProblem
    } catch {
      problem = {}
    }
    const errorCode = problem.error_code || (response.status === 422 ? "validation_error" : "http_error")
    const message = errorCodeMessages[errorCode] || fallbackMessages[response.status] || problem.message || "请求失败"
    if (response.status === 401) unauthorizedHandler?.()
    throw new ApiError(message, response.status, errorCode, requestId)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  register: (username: string, email: string, password: string) =>
    request<User>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, email, password }),
    }),
  login: (username: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<User>("/auth/me"),
  listJobs: (page = 1, pageSize = 20) =>
    request<JobPostingList>(`/job-postings?page=${page}&page_size=${pageSize}`),
  getJob: (id: string) => request<JobPosting>(`/job-postings/${encodeURIComponent(id)}`),
  createJob: (input: CreateJobPostingInput, idempotencyKey: string) =>
    request<JobPosting>("/job-postings", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(input),
    }),
  getProfile: (version?: number) =>
    request<CandidateProfile>(`/profile${version ? `?version=${version}` : ""}`),
  saveProfile: (input: CandidateProfileInput) =>
    request<CandidateProfile>("/profile", { method: "PUT", body: JSON.stringify(input) }),
  listResumes: (page = 1, pageSize = 20) =>
    request<ResumeVersionList>(`/resumes?page=${page}&page_size=${pageSize}`),
  getResume: (id: string) => request<ResumeVersion>(`/resumes/${encodeURIComponent(id)}`),
  publishResume: (title: string, profileVersion: number) =>
    request<ResumeVersion>("/resumes", {
      method: "POST",
      body: JSON.stringify({ title, profile_version: profileVersion }),
    }),
  listJobRequirements: (jobId: string, page = 1, pageSize = 20) =>
    request<JobRequirementSnapshotList>(
      `/job-postings/${encodeURIComponent(jobId)}/requirements?page=${page}&page_size=${pageSize}`,
    ),
  getJobRequirementLatest: (jobId: string) =>
    request<JobRequirementSnapshot>(
      `/job-postings/${encodeURIComponent(jobId)}/requirements/latest`,
    ),
  getJobRequirementVersion: (jobId: string, version: number) =>
    request<JobRequirementSnapshot>(
      `/job-postings/${encodeURIComponent(jobId)}/requirements/${version}`,
    ),
  saveJobRequirements: (jobId: string, input: JobRequirementSaveInput) =>
    request<JobRequirementSnapshot>(`/job-postings/${encodeURIComponent(jobId)}/requirements`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
}
