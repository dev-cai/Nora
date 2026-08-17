import { computed, ref } from "vue"
import { defineStore } from "pinia"

import { api } from "@/api/client"
import type { CreateJobPostingInput, JdInputPreview, JobPosting } from "@/api/types"

export const useJobsStore = defineStore("jobs", () => {
  const jobs = ref<JobPosting[]>([])
  const current = ref<JobPosting | null>(null)
  const total = ref(0)
  const listLoading = ref(false)
  const detailLoading = ref(false)
  const previewLoading = ref(false)
  const isLoading = computed(() => listLoading.value || detailLoading.value)
  let latestListRequest = 0
  let latestDetailRequest = 0
  let pendingCreate: { fingerprint: string; idempotencyKey: string } | null = null

  async function fetchJobs(page = 1, pageSize = 20): Promise<void> {
    const request = ++latestListRequest
    listLoading.value = true
    try {
      const response = await api.listJobs(page, pageSize)
      if (request === latestListRequest) {
        jobs.value = response.items
        total.value = response.total
      }
    } finally {
      if (request === latestListRequest) listLoading.value = false
    }
  }

  async function fetchJob(id: string): Promise<JobPosting> {
    const request = ++latestDetailRequest
    detailLoading.value = true
    try {
      const job = await api.getJob(id)
      if (request === latestDetailRequest) current.value = job
      return job
    } finally {
      if (request === latestDetailRequest) detailLoading.value = false
    }
  }

  async function createJob(input: CreateJobPostingInput): Promise<JobPosting> {
    const fingerprint = JSON.stringify([
      input.jd_text,
      input.job_title,
      input.company_name,
      input.location,
      input.source_type,
    ])
    if (!pendingCreate || pendingCreate.fingerprint !== fingerprint) {
      pendingCreate = { fingerprint, idempotencyKey: crypto.randomUUID() }
    }

    const job = await api.createJob(input, pendingCreate.idempotencyKey)
    pendingCreate = null
    const alreadyPresent = jobs.value.some((existing) => existing.id === job.id)
    jobs.value = [job, ...jobs.value.filter((existing) => existing.id !== job.id)]
    if (!alreadyPresent) total.value += 1
    return job
  }

  async function fetchPreviewFromUrl(url: string): Promise<JdInputPreview> {
    previewLoading.value = true
    try {
      return await api.fetchJobPreview(url)
    } finally {
      previewLoading.value = false
    }
  }

  async function fetchPreviewFromImage(file: File): Promise<JdInputPreview> {
    previewLoading.value = true
    try {
      return await api.ocrJobPreview(file)
    } finally {
      previewLoading.value = false
    }
  }

  function reset(): void {
    latestListRequest += 1
    latestDetailRequest += 1
    listLoading.value = false
    detailLoading.value = false
    previewLoading.value = false
    pendingCreate = null
    jobs.value = []
    current.value = null
    total.value = 0
  }

  return {
    jobs,
    current,
    total,
    isLoading,
    previewLoading,
    fetchJobs,
    fetchJob,
    createJob,
    fetchPreviewFromUrl,
    fetchPreviewFromImage,
    reset,
  }
})
