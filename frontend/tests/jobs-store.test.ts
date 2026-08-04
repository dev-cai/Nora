import { createPinia, setActivePinia } from "pinia"

import { api } from "@/api/client"
import type { CreateJobPostingInput, JobPosting, JobPostingList } from "@/api/types"
import { useJobsStore } from "@/stores/jobs"

vi.mock("@/api/client", () => ({
  api: {
    listJobs: vi.fn(),
    getJob: vi.fn(),
    createJob: vi.fn(),
  },
}))

const input: CreateJobPostingInput = {
  jd_text: "Build reliable services",
  job_title: "Backend Engineer",
  company_name: "Nora",
  location: "Remote",
  source_type: "manual",
}

function job(id: string): JobPosting {
  return {
    id,
    ...input,
    summary: input.jd_text,
    source_url: null,
    status: "active",
    version: 1,
    created_at: "2026-08-03T00:00:00Z",
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((onResolve, onReject) => {
    resolve = onResolve
    reject = onReject
  })
  return { promise, resolve, reject }
}

describe("jobs store", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(api.listJobs).mockReset()
    vi.mocked(api.getJob).mockReset()
    vi.mocked(api.createJob).mockReset()
  })

  it("ignores an older list response that completes after the latest request", async () => {
    const older = deferred<JobPostingList>()
    const latest = deferred<JobPostingList>()
    vi.mocked(api.listJobs).mockReturnValueOnce(older.promise).mockReturnValueOnce(latest.promise)
    const store = useJobsStore()

    const olderLoad = store.fetchJobs(1, 5)
    const latestLoad = store.fetchJobs(1, 20)
    latest.resolve({ items: [job("latest")], page: 1, page_size: 20, total: 1 })
    await latestLoad

    expect(store.jobs.map((item) => item.id)).toEqual(["latest"])
    expect(store.isLoading).toBe(false)

    older.resolve({ items: [job("older")], page: 1, page_size: 5, total: 1 })
    await olderLoad
    expect(store.jobs.map((item) => item.id)).toEqual(["latest"])
  })

  it("reuses the idempotency key when the same payload is retried", async () => {
    const randomUUID = vi.spyOn(crypto, "randomUUID").mockReturnValue("11111111-1111-4111-8111-111111111111")
    vi.mocked(api.createJob).mockRejectedValueOnce(new TypeError("response lost")).mockResolvedValueOnce(job("created"))
    const store = useJobsStore()

    await expect(store.createJob(input)).rejects.toThrow("response lost")
    await expect(store.createJob({ ...input })).resolves.toMatchObject({ id: "created" })

    expect(randomUUID).toHaveBeenCalledOnce()
    expect(vi.mocked(api.createJob).mock.calls.map((call) => call[1])).toEqual([
      "11111111-1111-4111-8111-111111111111",
      "11111111-1111-4111-8111-111111111111",
    ])
  })

  it("uses a new idempotency key when the failed payload changes", async () => {
    vi.spyOn(crypto, "randomUUID")
      .mockReturnValueOnce("11111111-1111-4111-8111-111111111111")
      .mockReturnValueOnce("22222222-2222-4222-8222-222222222222")
    vi.mocked(api.createJob).mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(job("changed"))
    const store = useJobsStore()

    await expect(store.createJob(input)).rejects.toThrow("offline")
    await store.createJob({ ...input, jd_text: "Changed JD" })

    expect(vi.mocked(api.createJob).mock.calls.map((call) => call[1])).toEqual([
      "11111111-1111-4111-8111-111111111111",
      "22222222-2222-4222-8222-222222222222",
    ])
  })

  it("clears user-scoped data and invalidates pending responses on reset", async () => {
    const pending = deferred<JobPostingList>()
    vi.mocked(api.listJobs).mockReturnValueOnce(pending.promise)
    const store = useJobsStore()
    const load = store.fetchJobs()

    store.reset()
    pending.resolve({ items: [job("old-user")], page: 1, page_size: 20, total: 1 })
    await load

    expect(store.jobs).toEqual([])
    expect(store.total).toBe(0)
    expect(store.isLoading).toBe(false)
  })
})
