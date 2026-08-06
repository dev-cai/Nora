import { ref } from "vue"
import { defineStore } from "pinia"

import { api, ApiError } from "@/api/client"
import type { JobRequirementSaveInput, JobRequirementSnapshot } from "@/api/types"

export const useJobRequirementsStore = defineStore("jobRequirements", () => {
  const latest = ref<JobRequirementSnapshot | null>(null)
  const versions = ref<JobRequirementSnapshot[]>([])
  const total = ref(0)
  const latestLoading = ref(false)
  const saving = ref(false)

  async function fetchLatest(jobId: string): Promise<JobRequirementSnapshot | null> {
    latestLoading.value = true
    try {
      try {
        latest.value = await api.getJobRequirementLatest(jobId)
      } catch (reason) {
        if (reason instanceof ApiError && reason.errorCode === "entity_not_found") {
          latest.value = null
        } else {
          throw reason
        }
      }
      return latest.value
    } finally {
      latestLoading.value = false
    }
  }

  async function fetchVersions(jobId: string, page = 1, pageSize = 100): Promise<void> {
    const response = await api.listJobRequirements(jobId, page, pageSize)
    versions.value = response.items
    total.value = response.total
  }

  async function save(jobId: string, input: JobRequirementSaveInput): Promise<JobRequirementSnapshot> {
    saving.value = true
    try {
      const snapshot = await api.saveJobRequirements(jobId, input)
      latest.value = snapshot
      versions.value = [snapshot, ...versions.value.filter((item) => item.version !== snapshot.version)]
      if (total.value < versions.value.length) total.value = versions.value.length
      return snapshot
    } finally {
      saving.value = false
    }
  }

  function reset(): void {
    latest.value = null
    versions.value = []
    total.value = 0
    latestLoading.value = false
    saving.value = false
  }

  return { latest, versions, total, latestLoading, saving, fetchLatest, fetchVersions, save, reset }
})
