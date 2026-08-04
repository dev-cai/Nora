import { ref } from "vue"
import { defineStore } from "pinia"

import { api, ApiError } from "@/api/client"
import type { CandidateProfile, CandidateProfileInput } from "@/api/types"

export const useProfileStore = defineStore("profile", () => {
  const current = ref<CandidateProfile | null>(null)
  const isLoading = ref(false)
  let requestVersion = 0

  async function fetchProfile(version?: number): Promise<CandidateProfile | null> {
    const request = ++requestVersion
    isLoading.value = true
    try {
      const profile = await api.getProfile(version)
      if (request === requestVersion) current.value = profile
      return profile
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        if (request === requestVersion) current.value = null
        return null
      }
      throw error
    } finally {
      if (request === requestVersion) isLoading.value = false
    }
  }

  async function saveProfile(input: CandidateProfileInput): Promise<CandidateProfile> {
    const profile = await api.saveProfile(input)
    current.value = profile
    return profile
  }

  function reset(): void {
    requestVersion += 1
    current.value = null
    isLoading.value = false
  }

  return { current, isLoading, fetchProfile, saveProfile, reset }
})
