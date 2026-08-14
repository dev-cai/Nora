import { ref } from "vue"
import { defineStore } from "pinia"

import { api } from "@/api/client"
import type {
  GenerateMessageDraftInput,
  MessageDraft,
} from "@/api/types"

export const useMessagesStore = defineStore("messages", () => {
  const current = ref<MessageDraft | null>(null)
  const versions = ref<MessageDraft[]>([])
  const latestForVariant = ref<MessageDraft | null>(null)
  const loading = ref(false)
  const generating = ref(false)
  const saving = ref(false)
  let pendingGeneration: { fingerprint: string; key: string } | null = null
  let pendingEdit: { fingerprint: string; key: string } | null = null

  async function fetchLatestForVariant(variantId: string): Promise<MessageDraft | null> {
    const value = await api.getLatestMessageDraft(variantId)
    latestForVariant.value = value
    return value
  }

  async function generate(
    variantId: string,
    input: GenerateMessageDraftInput,
  ): Promise<MessageDraft> {
    const fingerprint = JSON.stringify({ variantId, input })
    if (!pendingGeneration || pendingGeneration.fingerprint !== fingerprint) {
      pendingGeneration = { fingerprint, key: crypto.randomUUID() }
    }
    generating.value = true
    try {
      const value = await api.generateMessageDraft(
        variantId,
        input,
        pendingGeneration.key,
      )
      pendingGeneration = null
      latestForVariant.value = value
      current.value = value
      return value
    } finally {
      generating.value = false
    }
  }

  async function fetchDraft(draftId: string): Promise<MessageDraft> {
    current.value = null
    versions.value = []
    loading.value = true
    try {
      const value = await api.getMessageDraft(draftId)
      current.value = value
      return value
    } finally {
      loading.value = false
    }
  }

  async function fetchVersions(draftId: string): Promise<MessageDraft[]> {
    const values = await api.listMessageDraftVersions(draftId)
    versions.value = values
    return values
  }

  async function save(text: string): Promise<MessageDraft> {
    if (!current.value) throw new Error("Message draft is not loaded")
    const fingerprint = JSON.stringify({
      draftId: current.value.id,
      baseVersion: current.value.version,
      text,
    })
    if (!pendingEdit || pendingEdit.fingerprint !== fingerprint) {
      pendingEdit = { fingerprint, key: crypto.randomUUID() }
    }
    saving.value = true
    try {
      const value = await api.editMessageDraft(
        current.value.id,
        { base_version: current.value.version, text },
        pendingEdit.key,
      )
      pendingEdit = null
      current.value = value
      latestForVariant.value = value
      await fetchVersions(value.id)
      return value
    } finally {
      saving.value = false
    }
  }

  function reset(): void {
    current.value = null
    versions.value = []
    latestForVariant.value = null
    loading.value = false
    generating.value = false
    saving.value = false
    pendingGeneration = null
    pendingEdit = null
  }

  return {
    current,
    versions,
    latestForVariant,
    loading,
    generating,
    saving,
    fetchLatestForVariant,
    generate,
    fetchDraft,
    fetchVersions,
    save,
    reset,
  }
})
