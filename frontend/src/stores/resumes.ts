import { computed, ref } from "vue"
import { defineStore } from "pinia"

import { api } from "@/api/client"
import type { ResumeVersion } from "@/api/types"

export const useResumesStore = defineStore("resumes", () => {
  const resumes = ref<ResumeVersion[]>([])
  const current = ref<ResumeVersion | null>(null)
  const total = ref(0)
  const listLoading = ref(false)
  const detailLoading = ref(false)
  const isLoading = computed(() => listLoading.value || detailLoading.value)
  let listRequest = 0
  let detailRequest = 0

  async function fetchResumes(page = 1, pageSize = 20): Promise<void> {
    const request = ++listRequest
    listLoading.value = true
    try {
      const response = await api.listResumes(page, pageSize)
      if (request === listRequest) {
        resumes.value = response.items
        total.value = response.total
      }
    } finally {
      if (request === listRequest) listLoading.value = false
    }
  }

  async function fetchResume(id: string): Promise<ResumeVersion> {
    const request = ++detailRequest
    detailLoading.value = true
    try {
      const resume = await api.getResume(id)
      if (request === detailRequest) current.value = resume
      return resume
    } finally {
      if (request === detailRequest) detailLoading.value = false
    }
  }

  async function publishResume(title: string, profileVersion: number): Promise<ResumeVersion> {
    const resume = await api.publishResume(title, profileVersion)
    resumes.value = [resume, ...resumes.value.filter((item) => item.id !== resume.id)]
    total.value += 1
    return resume
  }

  function reset(): void {
    listRequest += 1
    detailRequest += 1
    resumes.value = []
    current.value = null
    total.value = 0
    listLoading.value = false
    detailLoading.value = false
  }

  return { resumes, current, total, isLoading, fetchResumes, fetchResume, publishResume, reset }
})
