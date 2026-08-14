import { ref } from "vue"
import { defineStore } from "pinia"

import { api } from "@/api/client"
import type {
  ApplicationRecord,
  ApplicationRecordTransition,
  CreateApplicationRecordInput,
  TransitionApplicationRecordInput,
} from "@/api/types"

export const useApplicationsStore = defineStore("applications", () => {
  const records = ref<ApplicationRecord[]>([])
  const current = ref<ApplicationRecord | null>(null)
  const transitions = ref<ApplicationRecordTransition[]>([])
  const total = ref(0)
  const loading = ref(false)
  const saving = ref(false)
  let pendingCreate: { fingerprint: string; key: string } | null = null
  let pendingTransition: { fingerprint: string; key: string } | null = null

  async function fetchRecords(): Promise<void> {
    loading.value = true
    try {
      const response = await api.listApplicationRecords()
      records.value = response.items
      total.value = response.total
    } finally {
      loading.value = false
    }
  }

  async function fetchRecord(id: string): Promise<ApplicationRecord> {
    current.value = null
    transitions.value = []
    loading.value = true
    try {
      const value = await api.getApplicationRecord(id)
      current.value = value
      return value
    } finally {
      loading.value = false
    }
  }

  async function fetchTransitions(id: string): Promise<ApplicationRecordTransition[]> {
    const values = await api.listApplicationRecordTransitions(id)
    transitions.value = values
    return values
  }

  async function create(input: CreateApplicationRecordInput): Promise<ApplicationRecord> {
    const fingerprint = JSON.stringify(input)
    if (!pendingCreate || pendingCreate.fingerprint !== fingerprint) {
      pendingCreate = { fingerprint, key: crypto.randomUUID() }
    }
    saving.value = true
    try {
      const value = await api.createApplicationRecord(input, pendingCreate.key)
      pendingCreate = null
      current.value = value
      records.value = [value, ...records.value.filter((item) => item.id !== value.id)]
      return value
    } finally {
      saving.value = false
    }
  }

  async function transition(
    input: TransitionApplicationRecordInput,
  ): Promise<ApplicationRecord> {
    if (!current.value) throw new Error("Application record is not loaded")
    const recordId = current.value.id
    const fingerprint = JSON.stringify({ recordId, input })
    if (!pendingTransition || pendingTransition.fingerprint !== fingerprint) {
      pendingTransition = { fingerprint, key: crypto.randomUUID() }
    }
    saving.value = true
    try {
      const value = await api.transitionApplicationRecord(
        recordId,
        input,
        pendingTransition.key,
      )
      pendingTransition = null
      current.value = value
      records.value = records.value.map((item) => item.id === value.id ? value : item)
      await fetchTransitions(value.id)
      return value
    } finally {
      saving.value = false
    }
  }

  function reset(): void {
    records.value = []
    current.value = null
    transitions.value = []
    total.value = 0
    loading.value = false
    saving.value = false
    pendingCreate = null
    pendingTransition = null
  }

  return {
    records,
    current,
    transitions,
    total,
    loading,
    saving,
    fetchRecords,
    fetchRecord,
    fetchTransitions,
    create,
    transition,
    reset,
  }
})
