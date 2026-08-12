<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { ArrowLeft, Play, ShieldCheck } from "lucide-vue-next"
import { useRoute, useRouter } from "vue-router"

import { userMessage } from "@/api/client"
import type { JobRequirementSnapshot } from "@/api/types"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useAnalysisStore } from "@/stores/analysis"
import { useJobRequirementsStore } from "@/stores/jobRequirements"
import { useJobsStore } from "@/stores/jobs"
import { useProfileStore } from "@/stores/profile"
import { useResumesStore } from "@/stores/resumes"

const route = useRoute()
const router = useRouter()
const analysisStore = useAnalysisStore()
const jobsStore = useJobsStore()
const requirementsStore = useJobRequirementsStore()
const profileStore = useProfileStore()
const resumesStore = useResumesStore()
const error = ref("")
const selectedJobId = ref("")
const selectedRequirementVersion = ref<number | null>(null)
const selectedResumeId = ref("")
const loadingInputs = ref(false)

const selectedJob = computed(() => jobsStore.jobs.find((item) => item.id === selectedJobId.value) || null)
const selectedRequirement = computed<JobRequirementSnapshot | null>(
  () => requirementsStore.versions.find((item) => item.version === selectedRequirementVersion.value) || null,
)
const compatibleResumes = computed(() => {
  const profile = profileStore.current
  if (!profile) return []
  return resumesStore.resumes.filter(
    (item) => item.candidate_profile_id === profile.id && item.profile_version === profile.version,
  )
})
const canSubmit = computed(
  () => Boolean(selectedJob.value && selectedRequirement.value && profileStore.current && selectedResumeId.value),
)

function confirmedCount(snapshot: JobRequirementSnapshot): number {
  return Object.values(snapshot.content).filter((item) => item.confirmation_status === "confirmed").length
}

async function loadRequirements(jobId: string): Promise<void> {
  selectedRequirementVersion.value = null
  requirementsStore.reset()
  if (!jobId) return
  try {
    await requirementsStore.fetchVersions(jobId)
    selectedRequirementVersion.value = requirementsStore.versions[0]?.version ?? null
  } catch (reason) {
    error.value = userMessage(reason)
  }
}

watch(selectedJobId, (jobId) => void loadRequirements(jobId))

async function load(): Promise<void> {
  error.value = ""
  loadingInputs.value = true
  try {
    await Promise.all([
      jobsStore.fetchJobs(1, 100),
      profileStore.fetchProfile(),
      resumesStore.fetchResumes(1, 100),
    ])
    const queryJobId = typeof route.query.jobId === "string" ? route.query.jobId : ""
    selectedJobId.value = jobsStore.jobs.some((item) => item.id === queryJobId)
      ? queryJobId
      : (jobsStore.jobs[0]?.id ?? "")
    selectedResumeId.value = compatibleResumes.value[0]?.id ?? ""
  } catch (reason) {
    error.value = userMessage(reason)
  } finally {
    loadingInputs.value = false
  }
}

async function submit(): Promise<void> {
  const job = selectedJob.value
  const requirement = selectedRequirement.value
  const profile = profileStore.current
  const resume = compatibleResumes.value.find((item) => item.id === selectedResumeId.value)
  if (!job || !requirement || !profile || !resume) return
  error.value = ""
  try {
    const created = await analysisStore.createCase({
      job_posting_id: job.id,
      job_posting_version: requirement.job_posting_version,
      job_requirement_snapshot_id: requirement.id,
      job_requirement_snapshot_version: requirement.version,
      candidate_profile_id: profile.id,
      candidate_profile_version: profile.version,
      resume_version_id: resume.id,
      resume_version: resume.version,
    })
    await router.push({ name: "analysis-detail", params: { id: created.id } })
  } catch (reason) {
    error.value = userMessage(reason)
  }
}

onMounted(load)
</script>

<template>
  <AppShell>
    <RouterLink
      class="back-link"
      to="/reports"
    >
      <ArrowLeft :size="16" /> 返回报告历史
    </RouterLink>
    <section class="section-toolbar page-toolbar">
      <div>
        <p class="eyebrow">
          固定版本输入
        </p>
        <h2>发起适配分析</h2>
        <p>选择一组已经保存的岗位、要求、主档与简历版本，执行同步确定性规则。</p>
      </div>
      <span class="analysis-mode-badge"><ShieldCheck :size="16" /> 确定性规则</span>
    </section>

    <StatePanel
      v-if="loadingInputs"
      mode="loading"
      title="正在读取分析输入"
    />
    <StatePanel
      v-else-if="error && jobsStore.jobs.length === 0"
      mode="error"
      title="无法准备分析"
      :message="error"
      @retry="load"
    />
    <form
      v-else
      class="analysis-form"
      @submit.prevent="submit"
    >
      <p
        v-if="error"
        class="form-error"
      >
        {{ error }}
      </p>
      <section class="analysis-step">
        <span class="analysis-step-number">1</span>
        <div class="analysis-step-content">
          <div class="analysis-step-heading">
            <div><h3>岗位与要求版本</h3><p>报告只读取选择的不可变岗位要求快照。</p></div>
            <RouterLink
              class="inline-link"
              to="/jobs"
            >
              管理岗位
            </RouterLink>
          </div>
          <div class="form-grid two-columns">
            <label>岗位
              <select v-model="selectedJobId">
                <option
                  value=""
                  disabled
                >选择岗位</option>
                <option
                  v-for="job in jobsStore.jobs"
                  :key="job.id"
                  :value="job.id"
                >
                  {{ job.job_title }} · {{ job.company_name }}
                </option>
              </select>
            </label>
            <label>岗位要求版本
              <select
                v-model="selectedRequirementVersion"
                :disabled="requirementsStore.versions.length === 0"
              >
                <option
                  :value="null"
                  disabled
                >选择要求版本</option>
                <option
                  v-for="snapshot in requirementsStore.versions"
                  :key="snapshot.version"
                  :value="snapshot.version"
                >
                  v{{ snapshot.version }} · 已确认 {{ confirmedCount(snapshot) }}/5 项
                </option>
              </select>
            </label>
          </div>
          <p
            v-if="selectedJobId && requirementsStore.versions.length === 0"
            class="form-warning"
          >
            该岗位还没有要求快照，请先进入岗位详情确认要求。
          </p>
        </div>
      </section>

      <section class="analysis-step">
        <span class="analysis-step-number">2</span>
        <div class="analysis-step-content">
          <div class="analysis-step-heading">
            <div><h3>主档版本</h3><p>使用当前已保存主档，后续编辑不会改写本次分析。</p></div>
            <RouterLink
              class="inline-link"
              to="/profile"
            >
              管理主档
            </RouterLink>
          </div>
          <div
            v-if="profileStore.current"
            class="input-snapshot-row"
          >
            <div><strong>{{ profileStore.current.content.basic_information.display_name.value || '未命名主档' }}</strong><small>主档 v{{ profileStore.current.version }}</small></div>
            <span class="ready-badge ready">已保存</span>
          </div>
          <p
            v-else
            class="form-warning"
          >
            还没有主档，请先建立并保存主档事实。
          </p>
        </div>
      </section>

      <section class="analysis-step">
        <span class="analysis-step-number">3</span>
        <div class="analysis-step-content">
          <div class="analysis-step-heading">
            <div><h3>简历版本</h3><p>仅显示与当前主档版本一致的不可变简历。</p></div>
            <RouterLink
              class="inline-link"
              to="/resumes"
            >
              管理简历
            </RouterLink>
          </div>
          <label>简历
            <select
              v-model="selectedResumeId"
              :disabled="compatibleResumes.length === 0"
            >
              <option
                value=""
                disabled
              >选择简历版本</option>
              <option
                v-for="resume in compatibleResumes"
                :key="resume.id"
                :value="resume.id"
              >
                {{ resume.title }} · v{{ resume.version }}
              </option>
            </select>
          </label>
          <p
            v-if="compatibleResumes.length === 0"
            class="form-warning"
          >
            当前主档版本还没有已发布简历，请先发布一个简历版本。
          </p>
        </div>
      </section>

      <div class="analysis-submit">
        <p>提交后同步计算，不会显示虚假的排队位置或进度百分比。</p>
        <button
          class="button button-primary"
          type="submit"
          :disabled="!canSubmit || analysisStore.creating"
        >
          <Play :size="17" />{{ analysisStore.creating ? '正在创建分析' : '开始分析' }}
        </button>
      </div>
    </form>
  </AppShell>
</template>
