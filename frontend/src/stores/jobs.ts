import { ref } from "vue"
import { defineStore } from "pinia"

import { api } from "@/api/client"
import type { CreateJobPostingInput, JobPosting } from "@/api/types"

export const useJobsStore = defineStore("jobs", () => {
  const jobs = ref<JobPosting[]>([])
  const current = ref<JobPosting | null>(null)
  const total = ref(0)
  const isLoading = ref(false)

  async function fetchJobs(page = 1, pageSize = 20): Promise<void> {
    isLoading.value = true
    try {
      const response = await api.listJobs(page, pageSize)
      jobs.value = response.items
      total.value = response.total
    } finally {
      isLoading.value = false
    }
  }

  async function fetchJob(id: string): Promise<JobPosting> {
    isLoading.value = true
    try {
      current.value = await api.getJob(id)
      return current.value
    } finally {
      isLoading.value = false
    }
  }

  async function createJob(input: CreateJobPostingInput): Promise<JobPosting> {
    const job = await api.createJob(input, crypto.randomUUID())
    jobs.value = [job, ...jobs.value]
    total.value += 1
    return job
  }

  return { jobs, current, total, isLoading, fetchJobs, fetchJob, createJob }
})
