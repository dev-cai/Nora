import { computed, ref } from "vue"
import { defineStore } from "pinia"

import { api } from "@/api/client"
import type { CreateResumeVariantInput, ResumeVariant, TemplateDefinition } from "@/api/types"

export const useVariantsStore = defineStore("variants", () => {
  const templates = ref<TemplateDefinition[]>([])
  const variants = ref<ResumeVariant[]>([])
  const current = ref<ResumeVariant | null>(null)
  const currentTemplate = ref<TemplateDefinition | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const total = ref(0)
  let pending: { fingerprint: string; key: string } | null = null
  const isLoading = computed(() => loading.value || saving.value)

  async function fetchTemplates(): Promise<void> {
    templates.value = await api.listTemplates()
  }

  async function fetchTemplate(id: string, version: number): Promise<TemplateDefinition> {
    const value = await api.getTemplate(id, version)
    currentTemplate.value = value
    return value
  }

  async function fetchVariants(): Promise<void> {
    loading.value = true
    try {
      const response = await api.listResumeVariants()
      variants.value = response.items
      total.value = response.total
    } finally { loading.value = false }
  }

  async function fetchVariant(id: string): Promise<ResumeVariant> {
    current.value = null
    currentTemplate.value = null
    loading.value = true
    try {
      const value = await api.getResumeVariant(id)
      current.value = value
      return value
    } finally { loading.value = false }
  }

  async function createVariant(input: CreateResumeVariantInput): Promise<ResumeVariant> {
    const fingerprint = JSON.stringify(input)
    if (!pending || pending.fingerprint !== fingerprint) {
      pending = { fingerprint, key: crypto.randomUUID() }
    }
    saving.value = true
    try {
      const value = await api.createResumeVariant(input, pending.key)
      pending = null
      current.value = value
      variants.value = [value, ...variants.value.filter((item) => item.id !== value.id)]
      return value
    } finally { saving.value = false }
  }

  function reset(): void {
    templates.value = []
    variants.value = []
    current.value = null
    currentTemplate.value = null
    total.value = 0
    loading.value = false
    saving.value = false
    pending = null
  }

  return { templates, variants, current, currentTemplate, total, loading, saving, isLoading, fetchTemplates, fetchTemplate, fetchVariants, fetchVariant, createVariant, reset }
})
