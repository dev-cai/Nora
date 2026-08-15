import { API_REQUEST_TIMEOUT_MS, ApiError, api, setAccessToken, setUnauthorizedHandler } from "@/api/client"

function response(body: unknown, status = 200, requestId = "request-123"): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "X-Request-ID": requestId },
  })
}

describe("API client", () => {
  afterEach(() => {
    setAccessToken(null)
    setUnauthorizedHandler(null)
  })

  it("injects the bearer token", async () => {
    setAccessToken("secret-token")
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ id: "1" }))

    await api.me()

    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers)
    expect(headers.get("Authorization")).toBe("Bearer secret-token")
  })

  it("maps an aborted request caused by the timeout to a stable error", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true })
    }))
    vi.useFakeTimers()
    const pending = api.me().catch((reason: unknown) => reason)
    await vi.advanceTimersByTimeAsync(API_REQUEST_TIMEOUT_MS)
    await expect(pending).resolves.toMatchObject({ errorCode: "network_timeout" })
    vi.useRealTimers()
  })

  it("captures request IDs and maps stable API errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({
      error_code: "email_conflict",
      error_category: "conflict",
      message: "Email already exists",
    }, 409, "conflict-7"))

    const error = await api.register("alice", "alice@example.com", "password-123").catch((reason: unknown) => reason)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 409, errorCode: "email_conflict", requestId: "conflict-7" })
    expect((error as Error).message).toBe("该邮箱已被注册")
  })

  it("falls back from an unmapped server code to its generated category", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({
      error_code: "invalid_job_title",
      error_category: "invalid_input",
      message: "Job title is invalid",
    }, 400))

    const error = await api.me().catch((reason: unknown) => reason)

    expect(error).toMatchObject({
      errorCode: "invalid_job_title",
      errorCategory: "invalid_input",
      message: "提交内容不符合要求",
    })
  })

  it("falls back from unknown response values to the HTTP status", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({
      error_code: "future_code",
      error_category: "future_category",
      message: "Untrusted server detail",
    }, 409))

    const error = await api.me().catch((reason: unknown) => reason)

    expect(error).toMatchObject({ errorCategory: null, message: "当前内容与服务端状态冲突" })
  })

  it("uses a generic fallback for an unknown response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({
      error_code: "toString",
      error_category: "constructor",
      message: "Untrusted detail",
    }, 418))

    const error = await api.me().catch((reason: unknown) => reason)

    expect(error).toMatchObject({ errorCode: "http_error", message: "请求失败" })
  })

  it("notifies the application when a request is unauthorized", async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({}, 401))

    await expect(api.me()).rejects.toMatchObject({ status: 401 })
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  it("keeps the integer retry delay for authentication rate limits", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      error_code: "authentication_rate_limited",
      error_category: "rate_limited",
      message: "Authentication rate limit exceeded",
    }), {
      status: 429,
      headers: { "Content-Type": "application/json", "Retry-After": "42" },
    }))

    await expect(api.login("alice", "wrong")).rejects.toMatchObject({
      status: 429,
      retryAfter: 42,
      message: "登录尝试过于频繁，请稍后重试",
    })
  })

  it("returns a stable network failure", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline"))

    await expect(api.me()).rejects.toMatchObject({ status: 0, errorCode: "network_error" })
  })

  it("uses the profile and resume resource contracts", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(response({})))

    await api.getProfile()
    await api.saveProfile({} as never)
    await api.listResumes()
    await api.getResume("resume-1")
    await api.publishResume("Backend", 2)

    expect(fetchMock.mock.calls.map(([url, init]) => [String(url), init?.method || "GET"])).toEqual([
      ["/api/profile", "GET"],
      ["/api/profile", "PUT"],
      ["/api/resumes?page=1&page_size=20", "GET"],
      ["/api/resumes/resume-1", "GET"],
      ["/api/resumes", "POST"],
    ])
  })

  it("uses the synchronous analysis and report resource contracts", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(response({})))

    await api.createDecisionCase({} as never)
    await api.getDecisionAnalysis("case/1")
    await api.generateDecisionReport("case/1")
    await api.listDecisionReports(2, 10)
    await api.getDecisionReport("report/1")
    await api.getApplicationDecision("report/1")
    await api.createApplicationDecision(
      "report/1",
      { status: "skip", reason: "地点不合适" },
      "decision-key",
    )

    expect(fetchMock.mock.calls.map(([url, init]) => [String(url), init?.method || "GET"])).toEqual([
      ["/api/decisions", "POST"],
      ["/api/decisions/case%2F1", "GET"],
      ["/api/decisions/case%2F1/reports", "POST"],
      ["/api/reports?page=2&page_size=10", "GET"],
      ["/api/reports/report%2F1", "GET"],
      ["/api/reports/report%2F1/decision", "GET"],
      ["/api/reports/report%2F1/decision", "POST"],
    ])
    const decisionHeaders = new Headers(fetchMock.mock.calls[6]?.[1]?.headers)
    expect(decisionHeaders.get("Idempotency-Key")).toBe("decision-key")
  })

  it("uses exact template versions and an idempotent resume variant contract", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(response({})))

    await api.listTemplates()
    await api.getTemplate("template/1", 2)
    await api.listResumeVariants(2, 10)
    await api.getResumeVariant("variant/1")
    await api.createResumeVariant({} as never, "variant-key")

    expect(fetchMock.mock.calls.map(([url, init]) => [String(url), init?.method || "GET"])).toEqual([
      ["/api/templates", "GET"],
      ["/api/templates/template%2F1/versions/2", "GET"],
      ["/api/resume-variants?page=2&page_size=10", "GET"],
      ["/api/resume-variants/variant%2F1", "GET"],
      ["/api/resume-variants", "POST"],
    ])
    const variantHeaders = new Headers(fetchMock.mock.calls[4]?.[1]?.headers)
    expect(variantHeaders.get("Idempotency-Key")).toBe("variant-key")
  })

  it("uses deterministic PDF status, generation, metadata and content routes", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(response({})))

    await api.getLatestResumePdf("variant/1")
    await api.generateResumePdf("variant/1")
    await api.getResumePdf("pdf/1")
    await api.getResumePdfContent("pdf/1", false)
    await api.getResumePdfContent("pdf/1", true)

    expect(fetchMock.mock.calls.map(([url, init]) => [String(url), init?.method || "GET"])).toEqual([
      ["/api/resume-variants/variant%2F1/pdf", "GET"],
      ["/api/resume-variants/variant%2F1/pdf", "POST"],
      ["/api/resume-pdfs/pdf%2F1", "GET"],
      ["/api/resume-pdfs/pdf%2F1/content?download=false", "GET"],
      ["/api/resume-pdfs/pdf%2F1/content?download=true", "GET"],
    ])
  })

  it("uses versioned message draft routes and idempotency keys", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.resolve(response({})))

    await api.getLatestMessageDraft("variant/1")
    await api.generateMessageDraft(
      "variant/1",
      { style: "professional", user_note: null, referral_context: null },
      "generate-key",
    )
    await api.listMessageDrafts(2, 10)
    await api.getMessageDraft("draft/1")
    await api.getMessageDraftVersion("draft/1", 2)
    await api.listMessageDraftVersions("draft/1")
    await api.editMessageDraft(
      "draft/1",
      { base_version: 1, text: "更新后的草稿" },
      "edit-key",
    )

    expect(fetchMock.mock.calls.map(([url, init]) => [String(url), init?.method || "GET"])).toEqual([
      ["/api/resume-variants/variant%2F1/message-draft", "GET"],
      ["/api/resume-variants/variant%2F1/message-drafts", "POST"],
      ["/api/message-drafts?page=2&page_size=10", "GET"],
      ["/api/message-drafts/draft%2F1", "GET"],
      ["/api/message-drafts/draft%2F1/versions/2", "GET"],
      ["/api/message-drafts/draft%2F1/versions", "GET"],
      ["/api/message-drafts/draft%2F1/revisions", "POST"],
    ])
    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get("Idempotency-Key")).toBe("generate-key")
    expect(new Headers(fetchMock.mock.calls[6]?.[1]?.headers).get("Idempotency-Key")).toBe("edit-key")
  })
})
