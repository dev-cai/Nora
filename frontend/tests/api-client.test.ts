import { ApiError, api, setAccessToken, setUnauthorizedHandler } from "@/api/client"

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

  it("injects the bearer token without persisting it", async () => {
    setAccessToken("secret-token")
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ id: "1" }))

    await api.me()

    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers)
    expect(headers.get("Authorization")).toBe("Bearer secret-token")
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it("captures request IDs and maps stable API errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ error_code: "email_conflict" }, 409, "conflict-7"))

    const error = await api.register("alice", "alice@example.com", "password-123").catch((reason: unknown) => reason)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 409, errorCode: "email_conflict", requestId: "conflict-7" })
    expect((error as Error).message).toBe("该邮箱已被注册")
  })

  it("notifies the application when a request is unauthorized", async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({}, 401))

    await expect(api.me()).rejects.toMatchObject({ status: 401 })
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  it("returns a stable network failure", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline"))

    await expect(api.me()).rejects.toMatchObject({ status: 0, errorCode: "network_error" })
  })
})
