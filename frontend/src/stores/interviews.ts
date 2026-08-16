import { ref } from "vue"
import { defineStore } from "pinia"

import { api } from "@/api/client"
import type {
  CreateInterviewCaseInput,
  InterviewCase,
  UpdateInterviewCaseInput,
} from "@/api/types"

export const useInterviewsStore = defineStore("interviews", () => {
  const items = ref<InterviewCase[]>([])
  const current = ref<InterviewCase | null>(null)
  const versions = ref<InterviewCase[]>([])
  const total = ref(0)
  const loading = ref(false)
  const saving = ref(false)
  let pendingMutation: { fingerprint: string; key: string } | null = null

  async function fetchInterviews(): Promise<void> {
    loading.value = true
    try {
      const response = await api.listInterviews()
      items.value = response.items
      total.value = response.total
    } finally {
      loading.value = false
    }
  }

  async function fetchInterview(id: string): Promise<InterviewCase> {
    current.value = null
    versions.value = []
    loading.value = true
    try {
      const value = await api.getInterview(id)
      current.value = value
      return value
    } finally {
      loading.value = false
    }
  }

  async function fetchVersions(id: string): Promise<InterviewCase[]> {
    const values = await api.listInterviewVersions(id)
    versions.value = values
    return values
  }

  async function create(
    applicationRecordId: string,
    input: CreateInterviewCaseInput,
  ): Promise<InterviewCase> {
    const fingerprint = JSON.stringify({ applicationRecordId, input })
    const key = mutationKey(fingerprint)
    saving.value = true
    try {
      const value = await api.createInterview(applicationRecordId, input, key)
      pendingMutation = null
      current.value = value
      items.value = [value, ...items.value.filter((item) => item.id !== value.id)]
      return value
    } finally {
      saving.value = false
    }
  }

  async function update(input: UpdateInterviewCaseInput): Promise<InterviewCase> {
    if (!current.value) throw new Error("Interview is not loaded")
    const interviewId = current.value.id
    const fingerprint = JSON.stringify({ interviewId, input })
    const key = mutationKey(fingerprint)
    saving.value = true
    try {
      const value = await api.updateInterview(interviewId, input, key)
      pendingMutation = null
      current.value = value
      items.value = items.value.map((item) => item.id === value.id ? value : item)
      await fetchVersions(value.id)
      return value
    } finally {
      saving.value = false
    }
  }

  function mutationKey(fingerprint: string): string {
    if (!pendingMutation || pendingMutation.fingerprint !== fingerprint) {
      pendingMutation = { fingerprint, key: crypto.randomUUID() }
    }
    return pendingMutation.key
  }

  function reset(): void {
    items.value = []
    current.value = null
    versions.value = []
    total.value = 0
    loading.value = false
    saving.value = false
    pendingMutation = null
  }

  return {
    items,
    current,
    versions,
    total,
    loading,
    saving,
    fetchInterviews,
    fetchInterview,
    fetchVersions,
    create,
    update,
    reset,
  }
})
