import type {
  AppendCompanySnapshotInput,
  ApplicationDecision,
  ApplicationRecord,
  ApplicationRecordList,
  ApplicationRecordTransition,
  Artifact,
  CandidateProfile,
  CandidateProfileInput,
  CompanyAssessment,
  CompanySnapshot,
  CreateCompanyAssessmentInput,
  CreateCompanySnapshotInput,
  CreateDecisionCaseInput,
  CreateApplicationDecisionInput,
  CreateApplicationRecordInput,
  CreateInterviewCaseInput,
  CreateJobPostingInput,
  CreateResumeVariantInput,
  CreateSourceInput,
  JdInputPreview,
  DecisionAnalysis,
  DecisionCase,
  DecisionReport,
  DecisionReportList,
  JobPosting,
  JobPostingList,
  JobFitAnalysis,
  JobRequirementSaveInput,
  JobRequirementSnapshot,
  JobRequirementSnapshotList,
  InterviewCase,
  InterviewCaseList,
  InterviewPreparation,
  EditMessageDraftInput,
  GenerateMessageDraftInput,
  MessageDraft,
  MessageDraftList,
  ResumePdf,
  ResumeVersion,
  ResumeVersionList,
  ResumeVariant,
  ResumeVariantList,
  SourceDocument,
  TemplateDefinition,
  TransitionApplicationRecordInput,
  UpdateInterviewCaseInput,
  TokenResponse,
  User,
} from "./types"
import type { components } from "./generated/schema"

type ServerErrorCode = components["schemas"]["ErrorCode"]
type ServerErrorCategory = components["schemas"]["ErrorCategory"]
type ServerProblem = Partial<components["schemas"]["ApiProblem"]>

export type TransportErrorCode = "network_error" | "network_timeout" | "http_error"
export type ApiErrorCode = ServerErrorCode | TransportErrorCode

const apiBaseUrl = (import.meta.env.VITE_NORA_API_BASE_URL || "/api").replace(/\/$/, "")
let accessToken: string | null = null
let unauthorizedHandler: (() => void) | null = null
export const API_REQUEST_TIMEOUT_MS = 10_000

const fallbackMessages: Record<number, string> = {
  400: "提交内容不符合要求",
  401: "登录状态已失效，请重新登录",
  404: "对象不存在或无权访问",
  409: "当前内容与服务端状态冲突",
  413: "上传内容超过大小限制",
  415: "上传内容类型不受支持",
  422: "提交内容未通过校验",
  429: "登录尝试过于频繁，请稍后重试",
  500: "服务发生内部错误，请稍后重试",
  502: "上游服务返回失败，请稍后重试",
  503: "服务暂时不可用，请稍后重试",
  504: "上游服务响应超时，请稍后重试",
}

const errorCodeMessages: Partial<Record<ServerErrorCode, string>> = {
  authentication_failed: "用户名或密码不正确",
  authentication_rate_limited: "登录尝试过于频繁，请稍后重试",
  origin_not_allowed: "当前页面来源不允许访问服务",
  username_conflict: "该用户名已被使用",
  email_conflict: "该邮箱已被注册",
  idempotency_conflict: "本次请求与已有操作冲突",
  entity_not_found: "对象不存在或无权访问",
  database_unavailable: "服务暂时不可用，请稍后重试",
  job_requirement_version_conflict: "岗位要求已更新，请刷新后重试",
  invalid_requirement: "岗位要求内容未通过校验",
  invalid_requirement_field: "岗位要求字段未通过校验",
  invalid_confirmation_status: "确认状态无效",
  invalid_source_type: "字段来源无效",
  application_decision_conflict: "该报告已经记录了不同决定",
  application_record_key_taken: "该操作标识已用于其他投递更新",
  application_record_transition_conflict: "当前投递状态不允许此操作",
  application_record_version_conflict: "投递记录已更新，请刷新后重试",
  company_assessment_conflict: "报告已经固定了另一版公司情报",
  company_assessment_unavailable: "公司情报暂时无法用于当前报告",
  company_snapshot_version_conflict: "公司情报已更新，请刷新后重试",
  invalid_company_assessment_status: "公司评估状态无效",
  invalid_company_fact_status: "公司字段值与确认状态不一致",
  invalid_company_name: "公司名称无效",
  invalid_company_text: "公司情报文本无效",
  invalid_application_record: "投递记录的材料或确认信息无效",
  invalid_variant_field: "定制字段不在来源简历或模板允许范围内",
  required_variant_field: "定制内容缺少模板必填字段",
  pdf_generation_failed: "PDF 生成失败，请重试",
  artifact_storage_unavailable: "PDF 存储暂时不可用，请重试",
  artifact_corrupt: "PDF 完整性校验失败",
  referral_context_required: "内推风格需要填写上下文",
  invalid_referral_context: "只有内推风格可以填写内推上下文",
  message_draft_version_conflict: "草稿已更新，请刷新后重试",
  invalid_draft_text: "消息草稿内容无效",
  skip_reason_required: "选择不投时需要填写原因",
  unsupported_image: "图片格式不受支持，请使用 PNG 或 JPEG",
  image_too_large: "图片超过 10 MiB 大小限制",
  decode_failed: "图片无法解码，请更换图片后重试",
  invalid_url: "链接格式不合法",
  unsafe_url: "链接指向的地址不允许访问",
  too_many_redirects: "链接跳转次数过多",
  response_too_large: "页面内容超过大小限制",
  fetch_timeout: "抓取页面超时，请稍后重试",
  fetch_failed: "无法抓取该链接，请稍后重试",
  ocr_failed: "图片识别失败，请更换图片后重试",
  empty_content: "未能从图片或链接中提取到有效内容",
  content_too_large: "提取的正文超过长度限制",
  model_not_configured: "AI 分析服务尚未配置，确定性报告仍可正常使用",
  model_provider_failed: "AI 分析服务调用失败，请稍后重试",
  model_provider_unavailable: "AI 分析服务暂时不可用，请稍后重试",
  model_timeout: "AI 分析服务响应超时，请稍后重试",
  model_output_invalid: "AI 返回内容未通过引用校验，请重新生成",
  model_budget_exceeded: "本次 AI 分析超过调用预算，未生成结果",
}

const categoryMessages: Record<ServerErrorCategory, string> = {
  invalid_input: "提交内容不符合要求",
  authentication: "登录状态已失效，请重新登录",
  forbidden: "当前请求不被允许",
  not_found: "对象不存在或无权访问",
  conflict: "当前内容与服务端状态冲突",
  payload_too_large: "上传内容超过大小限制",
  unsupported_media_type: "上传内容类型不受支持",
  request_validation: "提交内容未通过校验",
  rate_limited: "请求过于频繁，请稍后重试",
  upstream_failure: "上游服务返回失败，请稍后重试",
  service_unavailable: "服务暂时不可用，请稍后重试",
  upstream_timeout: "上游服务响应超时，请稍后重试",
  internal: "服务发生内部错误，请稍后重试",
}

function codeMessage(value: ServerErrorCode | undefined): string | undefined {
  if (!value || !Object.hasOwn(errorCodeMessages, value)) return undefined
  return errorCodeMessages[value]
}

function knownCategory(value: ServerErrorCategory | undefined): ServerErrorCategory | null {
  return value && Object.hasOwn(categoryMessages, value) ? value : null
}

export class ApiError extends Error {
  readonly status: number
  readonly errorCode: ApiErrorCode
  readonly requestId: string | null
  readonly errorCategory: ServerErrorCategory | null
  readonly retryAfter: number | null

  constructor(
    message: string,
    status = 0,
    errorCode: ApiErrorCode = "network_error",
    requestId: string | null = null,
    errorCategory: ServerErrorCategory | null = null,
    retryAfter: number | null = null,
  ) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.errorCode = errorCode
    this.requestId = requestId
    this.errorCategory = errorCategory
    this.retryAfter = retryAfter
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
  const response = await requestResponse(path, init)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

async function requestBlob(path: string): Promise<Blob> {
  return (await requestResponse(path)).blob()
}

async function requestResponse(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  headers.set("Accept", "application/json")
  const hasFormData = typeof FormData !== "undefined" && init.body instanceof FormData
  if (init.body !== undefined && !hasFormData) headers.set("Content-Type", "application/json")
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
    let problem: ServerProblem = {}
    try {
      problem = (await response.json()) as ServerProblem
    } catch {
      problem = {}
    }
    const errorCategory = knownCategory(problem.error_category)
    const retryAfterHeader = response.headers.get("Retry-After")
    const retryAfter = retryAfterHeader && /^\d+$/.test(retryAfterHeader)
      ? Number(retryAfterHeader)
      : null
    const exactMessage = codeMessage(problem.error_code)
    const errorCode: ApiErrorCode = problem.error_code && (errorCategory || exactMessage)
      ? problem.error_code
      : "http_error"
    const message = exactMessage
      ?? (errorCategory ? categoryMessages[errorCategory] : undefined)
      ?? fallbackMessages[response.status]
      ?? "请求失败"
    if (response.status === 401) unauthorizedHandler?.()
    throw new ApiError(message, response.status, errorCode, requestId, errorCategory, retryAfter)
  }

  return response
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
  fetchJobPreview: (url: string) =>
    request<JdInputPreview>("/job-postings/fetch", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),
  ocrJobPreview: (file: File) => {
    const body = new FormData()
    body.set("file", file)
    return request<JdInputPreview>("/job-postings/image", { method: "POST", body })
  },
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
  createDecisionCase: (input: CreateDecisionCaseInput) =>
    request<DecisionCase>("/decisions", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  getDecisionAnalysis: (caseId: string) =>
    request<DecisionAnalysis>(`/decisions/${encodeURIComponent(caseId)}`),
  generateDecisionReport: (caseId: string) =>
    request<DecisionReport>(`/decisions/${encodeURIComponent(caseId)}/reports`, {
      method: "POST",
    }),
  listDecisionReports: (page = 1, pageSize = 20) =>
    request<DecisionReportList>(`/reports?page=${page}&page_size=${pageSize}`),
  getDecisionReport: (reportId: string) =>
    request<DecisionReport>(`/reports/${encodeURIComponent(reportId)}`),
  getJobFitAnalysis: async (reportId: string) =>
    (await request<JobFitAnalysis | undefined>(
      `/reports/${encodeURIComponent(reportId)}/job-fit-analysis`,
    )) ?? null,
  generateJobFitAnalysis: (reportId: string) =>
    request<JobFitAnalysis>(`/reports/${encodeURIComponent(reportId)}/job-fit-analysis`, {
      method: "POST",
    }),
  getApplicationDecision: async (reportId: string) =>
    (await request<ApplicationDecision | undefined>(
      `/reports/${encodeURIComponent(reportId)}/decision`,
    )) ?? null,
  createApplicationDecision: (
    reportId: string,
    input: CreateApplicationDecisionInput,
    idempotencyKey: string,
  ) => request<ApplicationDecision>(`/reports/${encodeURIComponent(reportId)}/decision`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(input),
  }),
  uploadSourceArtifact: (file: File, idempotencyKey: string) => {
    const body = new FormData()
    body.set("file", file)
    body.set("kind", "source")
    return request<Artifact>("/artifacts", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body,
    })
  },
  createSource: (input: CreateSourceInput) =>
    request<SourceDocument>("/sources", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  createCompanySnapshot: (input: CreateCompanySnapshotInput) =>
    request<CompanySnapshot>("/companies", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  appendCompanySnapshot: (snapshotId: string, input: AppendCompanySnapshotInput) =>
    request<CompanySnapshot>(`/companies/${encodeURIComponent(snapshotId)}/versions`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  getLatestCompanySnapshot: (snapshotId: string) =>
    request<CompanySnapshot>(`/companies/${encodeURIComponent(snapshotId)}`),
  getCompanySnapshotVersion: (snapshotId: string, version: number) =>
    request<CompanySnapshot>(
      `/companies/${encodeURIComponent(snapshotId)}/versions/${version}`,
    ),
  listCompanySnapshotVersions: (snapshotId: string) =>
    request<CompanySnapshot[]>(`/companies/${encodeURIComponent(snapshotId)}/versions`),
  getCompanyAssessment: async (reportId: string) =>
    (await request<CompanyAssessment | undefined>(
      `/reports/${encodeURIComponent(reportId)}/company-assessment`,
    )) ?? null,
  createCompanyAssessment: (reportId: string, input: CreateCompanyAssessmentInput) =>
    request<CompanyAssessment>(`/reports/${encodeURIComponent(reportId)}/company-assessment`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  listTemplates: () => request<TemplateDefinition[]>("/templates"),
  getTemplate: (id: string, version: number) =>
    request<TemplateDefinition>(`/templates/${encodeURIComponent(id)}/versions/${version}`),
  listResumeVariants: (page = 1, pageSize = 20) =>
    request<ResumeVariantList>(`/resume-variants?page=${page}&page_size=${pageSize}`),
  getResumeVariant: (id: string) =>
    request<ResumeVariant>(`/resume-variants/${encodeURIComponent(id)}`),
  createResumeVariant: (input: CreateResumeVariantInput, idempotencyKey: string) =>
    request<ResumeVariant>("/resume-variants", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(input),
    }),
  getLatestResumePdf: async (variantId: string) =>
    (await request<ResumePdf | undefined>(
      `/resume-variants/${encodeURIComponent(variantId)}/pdf`,
    )) ?? null,
  generateResumePdf: (variantId: string) =>
    request<ResumePdf>(`/resume-variants/${encodeURIComponent(variantId)}/pdf`, {
      method: "POST",
    }),
  getResumePdf: (pdfId: string) =>
    request<ResumePdf>(`/resume-pdfs/${encodeURIComponent(pdfId)}`),
  getResumePdfContent: (pdfId: string, download: boolean) =>
    requestBlob(
      `/resume-pdfs/${encodeURIComponent(pdfId)}/content?download=${download ? "true" : "false"}`,
    ),
  getLatestMessageDraft: async (variantId: string) =>
    (await request<MessageDraft | undefined>(
      `/resume-variants/${encodeURIComponent(variantId)}/message-draft`,
    )) ?? null,
  generateMessageDraft: (
    variantId: string,
    input: GenerateMessageDraftInput,
    idempotencyKey: string,
  ) => request<MessageDraft>(
    `/resume-variants/${encodeURIComponent(variantId)}/message-drafts`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(input),
    },
  ),
  listMessageDrafts: (page = 1, pageSize = 20) =>
    request<MessageDraftList>(`/message-drafts?page=${page}&page_size=${pageSize}`),
  getMessageDraft: (draftId: string) =>
    request<MessageDraft>(`/message-drafts/${encodeURIComponent(draftId)}`),
  getMessageDraftVersion: (draftId: string, version: number) =>
    request<MessageDraft>(
      `/message-drafts/${encodeURIComponent(draftId)}/versions/${version}`,
    ),
  listMessageDraftVersions: (draftId: string) =>
    request<MessageDraft[]>(`/message-drafts/${encodeURIComponent(draftId)}/versions`),
  editMessageDraft: (
    draftId: string,
    input: EditMessageDraftInput,
    idempotencyKey: string,
  ) => request<MessageDraft>(`/message-drafts/${encodeURIComponent(draftId)}/revisions`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(input),
  }),
  listApplicationRecords: (page = 1, pageSize = 20) =>
    request<ApplicationRecordList>(
      `/application-records?page=${page}&page_size=${pageSize}`,
    ),
  getApplicationRecord: (recordId: string) =>
    request<ApplicationRecord>(`/application-records/${encodeURIComponent(recordId)}`),
  listApplicationRecordTransitions: (recordId: string) =>
    request<ApplicationRecordTransition[]>(
      `/application-records/${encodeURIComponent(recordId)}/transitions`,
    ),
  createApplicationRecord: (input: CreateApplicationRecordInput, idempotencyKey: string) =>
    request<ApplicationRecord>("/application-records", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(input),
    }),
  transitionApplicationRecord: (
    recordId: string,
    input: TransitionApplicationRecordInput,
    idempotencyKey: string,
  ) => request<ApplicationRecord>(
    `/application-records/${encodeURIComponent(recordId)}/transitions`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(input),
    },
  ),
  listInterviews: (page = 1, pageSize = 20) =>
    request<InterviewCaseList>(`/interviews?page=${page}&page_size=${pageSize}`),
  getInterview: (interviewId: string) =>
    request<InterviewCase>(`/interviews/${encodeURIComponent(interviewId)}`),
  getInterviewVersion: (interviewId: string, version: number) =>
    request<InterviewCase>(
      `/interviews/${encodeURIComponent(interviewId)}/versions/${version}`,
    ),
  listInterviewVersions: (interviewId: string) =>
    request<InterviewCase[]>(
      `/interviews/${encodeURIComponent(interviewId)}/versions`,
    ),
  createInterview: (
    applicationRecordId: string,
    input: CreateInterviewCaseInput,
    idempotencyKey: string,
  ) => request<InterviewCase>(
    `/application-records/${encodeURIComponent(applicationRecordId)}/interviews`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(input),
    },
  ),
  updateInterview: (
    interviewId: string,
    input: UpdateInterviewCaseInput,
    idempotencyKey: string,
  ) => request<InterviewCase>(
    `/interviews/${encodeURIComponent(interviewId)}/versions`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(input),
    },
  ),
  getInterviewPreparation: (interviewId: string) =>
    request<InterviewPreparation>(`/interviews/${encodeURIComponent(interviewId)}/preparation`),
  listInterviewPreparationVersions: (interviewId: string) =>
    request<InterviewPreparation[]>(
      `/interviews/${encodeURIComponent(interviewId)}/preparation/versions`,
    ),
  generateInterviewPreparation: (interviewId: string) =>
    request<InterviewPreparation>(
      `/interviews/${encodeURIComponent(interviewId)}/preparation`,
      { method: "POST" },
    ),
}
