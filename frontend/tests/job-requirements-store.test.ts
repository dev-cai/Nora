import { createPinia, setActivePinia } from "pinia"

import { api, ApiError } from "@/api/client"
import type { JobRequirementSnapshot } from "@/api/types"
import { useJobRequirementsStore } from "@/stores/jobRequirements"

vi.mock("@/api/client", () => {
  class MockApiError extends Error {
    status: number
    errorCode: string
    requestId: string | null
    constructor(message: string, status = 0, errorCode = "network_error", requestId: string | null = null) {
      super(message)
      this.status = status
      this.errorCode = errorCode
      this.requestId = requestId
    }
  }
  return {
    api: {
      getJobRequirementLatest: vi.fn(),
      listJobRequirements: vi.fn(),
      saveJobRequirements: vi.fn(),
    },
    ApiError: MockApiError,
  }
})

function snapshot(version: number, skills: string[] = ["Python"]): JobRequirementSnapshot {
  return {
    id: `snapshot-${version}`,
    job_posting_id: "job-1",
    job_posting_version: 1,
    version,
    content: {
      required_skills: { value: skills, confirmation_status: "confirmed", source_type: "manual", source_range: null },
      minimum_experience_years: { value: 3, confirmation_status: "confirmed", source_type: "manual", source_range: null },
      degree_requirement: { value: "本科", confirmation_status: "confirmed", source_type: "manual", source_range: null },
      location_requirement: { value: "北京", confirmation_status: "confirmed", source_type: "manual", source_range: null },
      work_mode: { value: "hybrid", confirmation_status: "confirmed", source_type: "manual", source_range: null },
    },
    content_hash: `hash-${version}`,
    created_at: "2026-08-06T00:00:00Z",
    updated_at: "2026-08-06T00:00:00Z",
  }
}

describe("job requirements store", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(api.getJobRequirementLatest).mockReset()
    vi.mocked(api.listJobRequirements).mockReset()
    vi.mocked(api.saveJobRequirements).mockReset()
  })

  it("loads the latest snapshot when it exists", async () => {
    vi.mocked(api.getJobRequirementLatest).mockResolvedValue(snapshot(2, ["Python", "FastAPI"]))
    const store = useJobRequirementsStore()

    const latest = await store.fetchLatest("job-1")

    expect(latest?.version).toBe(2)
    expect(store.latest?.content.required_skills.value).toEqual(["Python", "FastAPI"])
    expect(store.latestLoading).toBe(false)
  })

  it("treats a missing snapshot as no requirements", async () => {
    vi.mocked(api.getJobRequirementLatest).mockRejectedValue(
      new ApiError("not found", 404, "entity_not_found"),
    )
    const store = useJobRequirementsStore()

    const latest = await store.fetchLatest("job-1")

    expect(latest).toBeNull()
    expect(store.latest).toBeNull()
  })

  it("propagates unexpected failures while loading the latest", async () => {
    vi.mocked(api.getJobRequirementLatest).mockRejectedValue(new ApiError("down", 503, "database_unavailable"))
    const store = useJobRequirementsStore()

    await expect(store.fetchLatest("job-1")).rejects.toMatchObject({ errorCode: "database_unavailable" })
  })

  it("prepends the saved version to history and updates latest", async () => {
    vi.mocked(api.listJobRequirements).mockResolvedValue({
      items: [snapshot(2), snapshot(1)],
      page: 1,
      page_size: 100,
      total: 2,
    })
    vi.mocked(api.saveJobRequirements).mockResolvedValue(snapshot(3, ["Python", "Go"]))
    const store = useJobRequirementsStore()
    await store.fetchVersions("job-1")

    await store.save("job-1", {
      content: snapshot(3).content,
      job_posting_version: 1,
    })

    expect(store.latest?.version).toBe(3)
    expect(store.versions.map((item) => item.version)).toEqual([3, 2, 1])
    expect(store.total).toBe(3)
  })

  it("clears state on reset", async () => {
    vi.mocked(api.getJobRequirementLatest).mockResolvedValue(snapshot(1))
    const store = useJobRequirementsStore()
    await store.fetchLatest("job-1")

    store.reset()

    expect(store.latest).toBeNull()
    expect(store.versions).toEqual([])
    expect(store.latestLoading).toBe(false)
    expect(store.saving).toBe(false)
  })
})
