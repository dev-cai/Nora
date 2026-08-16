import { flushPromises, mount } from "@vue/test-utils"
import { createPinia, setActivePinia } from "pinia"

import { ApiError, api } from "@/api/client"
import type { Artifact, CompanyAssessment, CompanySnapshot, SourceDocument } from "@/api/types"
import CompanySnapshotCard from "@/components/CompanySnapshotCard.vue"
import { useCompaniesStore, type CompanySnapshotSubmission } from "@/stores/companies"

const artifact: Artifact = {
  id: "artifact-1",
  version: 1,
  kind: "source",
  content_type: "text/plain",
  size_bytes: 12,
  sha256: "a".repeat(64),
  status: "available",
  created_at: "2026-08-16T00:00:00Z",
  deleted_at: null,
}
const source: SourceDocument = {
  id: "source-1",
  version: 1,
  artifact_id: artifact.id,
  artifact_version: 1,
  source_kind: "manual",
  acquisition_method: "user_entry",
  license_note: "用户提供",
  locator: null,
  acquired_at: "2026-08-16T00:00:00Z",
  published_at: "2026-08-01T00:00:00Z",
  content_sha256: artifact.sha256,
  created_at: "2026-08-16T00:00:00Z",
}
const snapshot: CompanySnapshot = {
  id: "company-1",
  version: 1,
  company_name: "Example Inc",
  size: "100-499",
  size_status: "confirmed",
  industry: "Software",
  industry_status: "confirmed",
  review_summary: "工程成长路径清晰",
  review_status: "unconfirmed",
  freshness: "fresh",
  content_sha256: "b".repeat(64),
  created_at: "2026-08-16T00:00:00Z",
  source: {
    id: source.id,
    version: source.version,
    tier: "official/company",
    kind: source.source_kind,
    acquisition_method: source.acquisition_method,
    license_note: source.license_note,
    acquired_at: source.acquired_at,
    published_at: source.published_at,
    content_sha256: source.content_sha256,
  },
}
const submission: CompanySnapshotSubmission = {
  company_name: snapshot.company_name,
  size: snapshot.size,
  size_status: snapshot.size_status,
  industry: snapshot.industry,
  industry_status: snapshot.industry_status,
  review_summary: snapshot.review_summary,
  review_status: snapshot.review_status,
  source: {
    content: "company source",
    kind: "manual",
    locator: null,
    acquisition_method: source.acquisition_method,
    license_note: source.license_note,
    acquired_at: source.acquired_at,
    published_at: source.published_at,
    tier: snapshot.source.tier,
  },
}

describe("company intelligence", () => {
  beforeEach(() => setActivePinia(createPinia()))

  it("reuses the source upload idempotency key after a network failure", async () => {
    vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000001")
    const upload = vi.spyOn(api, "uploadSourceArtifact")
      .mockRejectedValueOnce(new ApiError("网络失败"))
      .mockResolvedValueOnce(artifact)
    vi.spyOn(api, "createSource").mockResolvedValue(source)
    vi.spyOn(api, "createCompanySnapshot").mockResolvedValue(snapshot)
    const store = useCompaniesStore()

    await expect(store.create(submission)).rejects.toThrow("网络失败")
    await expect(store.create(submission)).resolves.toEqual(snapshot)

    expect(upload.mock.calls.map((call) => call[1])).toEqual([
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000001",
    ])
  })

  it("loads an exact historical version while retaining the latest append base", async () => {
    const second = { ...snapshot, version: 2, size: "500-999", content_sha256: "c".repeat(64) }
    vi.spyOn(api, "getLatestCompanySnapshot").mockResolvedValue(second)
    vi.spyOn(api, "listCompanySnapshotVersions").mockResolvedValue([second, snapshot])
    vi.spyOn(api, "getCompanySnapshotVersion").mockResolvedValue(snapshot)
    const store = useCompaniesStore()

    await store.fetch(snapshot.id, 1)

    expect(store.current).toEqual(snapshot)
    expect(store.latest).toEqual(second)
    expect(store.versions.map((item) => item.version)).toEqual([2, 1])
  })

  it("replays report attachment with the same created snapshot after a lost response", async () => {
    vi.spyOn(api, "uploadSourceArtifact").mockResolvedValue(artifact)
    vi.spyOn(api, "createSource").mockResolvedValue(source)
    const createSnapshot = vi.spyOn(api, "createCompanySnapshot").mockResolvedValue(snapshot)
    const assessment = { snapshot } as CompanyAssessment
    const attach = vi.spyOn(api, "createCompanyAssessment")
      .mockRejectedValueOnce(new ApiError("网络失败"))
      .mockResolvedValueOnce(assessment)
    const store = useCompaniesStore()

    await expect(store.createAndAttach("report-1", submission)).rejects.toThrow("网络失败")
    await expect(store.createAndAttach("report-1", submission)).resolves.toBe(assessment)

    expect(createSnapshot).toHaveBeenCalledTimes(1)
    expect(attach).toHaveBeenCalledTimes(2)
    expect(attach.mock.calls.map((call) => call[1])).toEqual([
      { company_snapshot_id: snapshot.id, company_snapshot_version: snapshot.version },
      { company_snapshot_id: snapshot.id, company_snapshot_version: snapshot.version },
    ])
  })

  it("keeps anonymous summaries and stale assessments visibly non-factual", async () => {
    const anonymous = {
      ...snapshot,
      freshness: "stale" as const,
      size_status: "conflicted" as const,
      industry_status: "unknown" as const,
      industry: null,
      source: { ...snapshot.source, tier: "anonymous_platform" as const },
    }
    const assessment = {
      status: "stale",
      status_reason: "snapshot_stale",
    } satisfies Pick<CompanyAssessment, "status" | "status_reason">
    const wrapper = mount(CompanySnapshotCard, { props: { snapshot: anonymous, assessment } })
    await flushPromises()

    expect(wrapper.text()).toContain("匿名来源摘要（非事实）")
    expect(wrapper.text()).toContain("已过期")
    expect(wrapper.text()).toContain("存在冲突")
    expect(wrapper.text()).toContain("未知")
    expect(wrapper.text()).not.toContain("聚合评分")
  })
})
