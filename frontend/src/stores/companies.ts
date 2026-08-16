import { computed, ref } from "vue"
import { defineStore } from "pinia"

import { api } from "@/api/client"
import type {
  CompanyAssessment,
  CompanyFieldStatus,
  CompanySnapshot,
  CompanySourceTier,
  SourceDocument,
} from "@/api/types"

export interface CompanySnapshotSubmission {
  company_name: string
  size: string | null
  size_status: CompanyFieldStatus
  industry: string | null
  industry_status: CompanyFieldStatus
  review_summary: string | null
  review_status: CompanyFieldStatus
  source: {
    content: string
    kind: "manual" | "web"
    locator: string | null
    acquisition_method: string
    license_note: string
    acquired_at: string
    published_at: string | null
    tier: CompanySourceTier
  }
}

export const useCompaniesStore = defineStore("companies", () => {
  const latest = ref<CompanySnapshot | null>(null)
  const current = ref<CompanySnapshot | null>(null)
  const versions = ref<CompanySnapshot[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const attaching = ref(false)
  const isBusy = computed(() => loading.value || saving.value || attaching.value)
  let loadRequest = 0
  let pendingSource: {
    fingerprint: string
    idempotencyKey: string
    source: SourceDocument | null
  } | null = null
  let pendingCreation: {
    fingerprint: string
    snapshot: CompanySnapshot
  } | null = null

  function sourceFingerprint(input: CompanySnapshotSubmission): string {
    return JSON.stringify(input.source)
  }

  async function prepareSource(input: CompanySnapshotSubmission): Promise<SourceDocument> {
    const fingerprint = sourceFingerprint(input)
    if (!pendingSource || pendingSource.fingerprint !== fingerprint) {
      pendingSource = {
        fingerprint,
        idempotencyKey: crypto.randomUUID(),
        source: null,
      }
    }
    if (pendingSource.source) return pendingSource.source

    const file = new File([input.source.content], "company-source.txt", { type: "text/plain" })
    const artifact = await api.uploadSourceArtifact(file, pendingSource.idempotencyKey)
    const source = await api.createSource({
      artifact_id: artifact.id,
      source_kind: input.source.kind,
      acquisition_method: input.source.acquisition_method,
      license_note: input.source.license_note,
      locator: input.source.locator,
      acquired_at: input.source.acquired_at,
      published_at: input.source.published_at,
    })
    pendingSource.source = source
    return source
  }

  async function create(input: CompanySnapshotSubmission): Promise<CompanySnapshot> {
    saving.value = true
    try {
      const source = await prepareSource(input)
      const created = await api.createCompanySnapshot({
        company_name: input.company_name,
        size: input.size,
        size_status: input.size_status,
        industry: input.industry,
        industry_status: input.industry_status,
        review_summary: input.review_summary,
        review_status: input.review_status,
        source_id: source.id,
        source_version: source.version,
        source_tier: input.source.tier,
      })
      latest.value = created
      current.value = created
      versions.value = [created]
      pendingSource = null
      return created
    } finally {
      saving.value = false
    }
  }

  async function append(
    snapshotId: string,
    expectedVersion: number,
    input: CompanySnapshotSubmission,
  ): Promise<CompanySnapshot> {
    saving.value = true
    try {
      const source = await prepareSource(input)
      const created = await api.appendCompanySnapshot(snapshotId, {
        expected_version: expectedVersion,
        size: input.size,
        size_status: input.size_status,
        industry: input.industry,
        industry_status: input.industry_status,
        review_summary: input.review_summary,
        review_status: input.review_status,
        source_id: source.id,
        source_version: source.version,
        source_tier: input.source.tier,
      })
      latest.value = created
      current.value = created
      versions.value = [created, ...versions.value.filter((item) => item.version !== created.version)]
      pendingSource = null
      return created
    } finally {
      saving.value = false
    }
  }

  async function fetch(snapshotId: string, version?: number): Promise<CompanySnapshot> {
    const request = ++loadRequest
    latest.value = null
    current.value = null
    versions.value = []
    loading.value = true
    try {
      const [loadedLatest, loadedVersions, selected] = await Promise.all([
        api.getLatestCompanySnapshot(snapshotId),
        api.listCompanySnapshotVersions(snapshotId),
        version ? api.getCompanySnapshotVersion(snapshotId, version) : Promise.resolve(null),
      ])
      if (request === loadRequest) {
        latest.value = loadedLatest
        versions.value = loadedVersions
        current.value = selected ?? loadedLatest
      }
      return selected ?? loadedLatest
    } finally {
      if (request === loadRequest) loading.value = false
    }
  }

  async function attachToReport(
    reportId: string,
    snapshotId: string,
    snapshotVersion: number,
  ): Promise<CompanyAssessment> {
    attaching.value = true
    try {
      return await api.createCompanyAssessment(reportId, {
        company_snapshot_id: snapshotId,
        company_snapshot_version: snapshotVersion,
      })
    } finally {
      attaching.value = false
    }
  }

  async function createAndAttach(
    reportId: string,
    input: CompanySnapshotSubmission,
  ): Promise<CompanyAssessment> {
    const fingerprint = JSON.stringify(input)
    if (!pendingCreation || pendingCreation.fingerprint !== fingerprint) {
      pendingCreation = { fingerprint, snapshot: await create(input) }
    }
    const assessment = await attachToReport(
      reportId,
      pendingCreation.snapshot.id,
      pendingCreation.snapshot.version,
    )
    pendingCreation = null
    return assessment
  }

  function reset(): void {
    loadRequest += 1
    latest.value = null
    current.value = null
    versions.value = []
    loading.value = false
    saving.value = false
    attaching.value = false
    pendingSource = null
    pendingCreation = null
  }

  return {
    latest,
    current,
    versions,
    loading,
    saving,
    attaching,
    isBusy,
    create,
    append,
    fetch,
    attachToReport,
    createAndAttach,
    reset,
  }
})
