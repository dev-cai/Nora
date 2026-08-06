<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { ArrowLeft, CheckCircle2, CircleDashed, Plus, Save, Trash2 } from "lucide-vue-next"
import { useRoute } from "vue-router"

import { userMessage } from "@/api/client"
import type {
  JobRequirementSaveInput,
  RequirementConfirmationStatus,
  RequirementSourceType,
  WorkMode,
} from "@/api/types"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useJobRequirementsStore } from "@/stores/jobRequirements"
import { useJobsStore } from "@/stores/jobs"

const route = useRoute()
const jobsStore = useJobsStore()
const reqStore = useJobRequirementsStore()
const error = ref("")
const notice = ref("")
const jobId = String(route.params.id)

const statusLabels: Record<RequirementConfirmationStatus, string> = {
  unknown: "未知",
  unconfirmed: "待确认",
  confirmed: "已确认",
}
const sourceLabels: Record<RequirementSourceType, string> = {
  manual: "人工输入",
  text_range: "原文区间",
  ocr_preview: "OCR 预览",
}
const workModeLabels: Record<WorkMode, string> = {
  onsite: "现场办公",
  hybrid: "混合办公",
  remote: "远程",
}

const draft = reactive({
  required_skills: { value: null as string[] | null, confirmation_status: "unknown" as RequirementConfirmationStatus },
  minimum_experience_years: { value: null as number | null, confirmation_status: "unknown" as RequirementConfirmationStatus },
  degree_requirement: { value: null as string | null, confirmation_status: "unknown" as RequirementConfirmationStatus },
  location_requirement: { value: null as string | null, confirmation_status: "unknown" as RequirementConfirmationStatus },
  work_mode: { value: null as WorkMode | null, confirmation_status: "unknown" as RequirementConfirmationStatus },
})

function skillList(): string[] {
  if (draft.required_skills.value === null) {
    draft.required_skills.value = []
  }
  return draft.required_skills.value
}

function addSkill(): void {
  skillList().push("")
}
function removeSkill(index: number): void {
  skillList().splice(index, 1)
}
function updateSkill(index: number, value: string): void {
  skillList()[index] = value
}

async function load(): Promise<void> {
  error.value = ""
  try {
    await jobsStore.fetchJob(jobId)
    const latest = await reqStore.fetchLatest(jobId)
    if (latest) {
      draft.required_skills = {
        value: latest.content.required_skills.value ?? [],
        confirmation_status: latest.content.required_skills.confirmation_status,
      }
      draft.minimum_experience_years = {
        value: latest.content.minimum_experience_years.value,
        confirmation_status: latest.content.minimum_experience_years.confirmation_status,
      }
      draft.degree_requirement = {
        value: latest.content.degree_requirement.value,
        confirmation_status: latest.content.degree_requirement.confirmation_status,
      }
      draft.location_requirement = {
        value: latest.content.location_requirement.value,
        confirmation_status: latest.content.location_requirement.confirmation_status,
      }
      draft.work_mode = {
        value: latest.content.work_mode.value,
        confirmation_status: latest.content.work_mode.confirmation_status,
      }
    }
    await reqStore.fetchVersions(jobId)
  } catch (reason) {
    error.value = userMessage(reason)
  }
}

const saving = ref(false)
async function save(): Promise<void> {
  error.value = ""
  notice.value = ""
  const payload = buildPayload()
  if (!payload) return
  saving.value = true
  try {
    const saved = await reqStore.save(jobId, payload)
    notice.value = saved.version === 1 ? "已创建岗位要求快照" : `已创建新版本 v${saved.version}`
  } catch (reason) {
    error.value = userMessage(reason)
  } finally {
    saving.value = false
  }
}

function buildPayload(): JobRequirementSaveInput | null {
  if (jobsStore.current === null) return null
  const valueChecks: Array<[string, RequirementConfirmationStatus, unknown]> = [
    ["最低经验年限", draft.minimum_experience_years.confirmation_status, draft.minimum_experience_years.value],
    ["学历要求", draft.degree_requirement.confirmation_status, draft.degree_requirement.value],
    ["地点要求", draft.location_requirement.confirmation_status, draft.location_requirement.value],
    ["工作方式", draft.work_mode.confirmation_status, draft.work_mode.value],
  ]
  for (const [label, status, value] of valueChecks) {
    if (status !== "unknown" && (value === null || (typeof value === "string" && value.trim() === ""))) {
      error.value = `${label}需要填写内容，或把确认状态改为「未知」`
      return null
    }
  }
  const skills = skillList().map((item) => item.trim()).filter((item) => item !== "")
  const content = {
    required_skills: {
      value: draft.required_skills.confirmation_status === "unknown" ? null : skills,
      confirmation_status: draft.required_skills.confirmation_status,
      source_type: "manual" as const,
      source_range: null,
    },
    minimum_experience_years: {
      value:
        draft.minimum_experience_years.confirmation_status === "unknown"
          ? null
          : draft.minimum_experience_years.value,
      confirmation_status: draft.minimum_experience_years.confirmation_status,
      source_type: "manual" as const,
      source_range: null,
    },
    degree_requirement: {
      value:
        draft.degree_requirement.confirmation_status === "unknown"
          ? null
          : draft.degree_requirement.value,
      confirmation_status: draft.degree_requirement.confirmation_status,
      source_type: "manual" as const,
      source_range: null,
    },
    location_requirement: {
      value:
        draft.location_requirement.confirmation_status === "unknown"
          ? null
          : draft.location_requirement.value,
      confirmation_status: draft.location_requirement.confirmation_status,
      source_type: "manual" as const,
      source_range: null,
    },
    work_mode: {
      value:
        draft.work_mode.confirmation_status === "unknown" ? null : draft.work_mode.value,
      confirmation_status: draft.work_mode.confirmation_status,
      source_type: "manual" as const,
      source_range: null,
    },
  }
  return { content, job_posting_version: jobsStore.current.version }
}

const confirmedCount = computed(() => {
  const content = reqStore.latest?.content
  if (!content) return 0
  return Object.values(content).filter((fact) => fact.confirmation_status === "confirmed").length
})
const analysisReady = computed(() => reqStore.latest !== null && confirmedCount.value === 5)

onMounted(load)
</script>

<template>
  <AppShell>
    <RouterLink
      class="back-link"
      :to="{ name: 'job-detail', params: { id: jobId } }"
    >
      <ArrowLeft :size="16" /> 返回岗位详情
    </RouterLink>
    <StatePanel
      v-if="error"
      mode="error"
      title="无法加载岗位要求"
      :message="error"
      @retry="load"
    />
    <StatePanel
      v-else-if="jobsStore.isLoading || reqStore.latestLoading"
      mode="loading"
      title="正在加载岗位要求"
    />
    <template v-else-if="jobsStore.current">
      <section class="section-toolbar page-toolbar">
        <div>
          <p class="eyebrow">
            分析就绪输入
          </p>
          <h2>确认岗位要求</h2>
          <p>{{ jobsStore.current.job_title }} · {{ jobsStore.current.company_name }}</p>
        </div>
        <div
          v-if="analysisReady"
          class="ready-badge ready"
        >
          <CheckCircle2 :size="16" /> 岗位要求已确认（5/5）
        </div>
        <div
          v-else
          class="ready-badge pending"
          title="分析就绪还需主档与简历"
        >
          <CircleDashed :size="16" /> 岗位要求待确认（{{ confirmedCount }}/5）
        </div>
      </section>

      <section class="content-section detail-content">
        <div class="section-toolbar">
          <div>
            <p class="eyebrow">
              原始事实
            </p>
            <h2>岗位描述</h2>
          </div>
        </div>
        <pre>{{ jobsStore.current.jd_text }}</pre>
      </section>

      <form
        class="job-form"
        @submit.prevent="save"
      >
        <section class="form-section">
          <div class="form-section-title">
            <span>01</span>
            <div>
              <h3>技能要求</h3>
              <p>从 JD 原文或 OCR 结果确认所需技能。</p>
            </div>
          </div>
          <div class="fact-field">
            <div
              v-for="(skill, index) in skillList()"
              :key="index"
              class="skill-row"
            >
              <input
                :value="skill"
                maxlength="100"
                placeholder="例如 Python"
                @input="updateSkill(index, ($event.target as HTMLInputElement).value)"
              >
              <button
                class="icon-button"
                type="button"
                :aria-label="`移除技能 ${index + 1}`"
                @click="removeSkill(index)"
              >
                <Trash2 :size="16" />
              </button>
            </div>
            <button
              class="button button-secondary button-small"
              type="button"
              @click="addSkill"
            >
              <Plus :size="16" /> 添加技能
            </button>
          </div>
          <div class="field-meta">
            <select v-model="draft.required_skills.confirmation_status">
              <option
                v-for="(label, value) in statusLabels"
                :key="value"
                :value="value"
              >
                {{ label }}
              </option>
            </select>
            <span>来源：{{ reqStore.latest ? sourceLabels[reqStore.latest.content.required_skills.source_type] : "尚未创建" }}</span>
          </div>
        </section>

        <section class="form-section">
          <div class="form-section-title">
            <span>02</span>
            <div>
              <h3>最低经验年限</h3>
              <p>岗位要求的最少年限，缺失保持未知。</p>
            </div>
          </div>
          <div class="fact-field">
            <input
              v-model.number="draft.minimum_experience_years.value"
              type="number"
              min="0"
              max="50"
              :disabled="draft.minimum_experience_years.confirmation_status === 'unknown'"
              placeholder="例如 3"
            >
          </div>
          <div class="field-meta">
            <select v-model="draft.minimum_experience_years.confirmation_status">
              <option
                v-for="(label, value) in statusLabels"
                :key="value"
                :value="value"
              >
                {{ label }}
              </option>
            </select>
            <span>来源：{{ reqStore.latest ? sourceLabels[reqStore.latest.content.minimum_experience_years.source_type] : "尚未创建" }}</span>
          </div>
        </section>

        <section class="form-section">
          <div class="form-section-title">
            <span>03</span>
            <div>
              <h3>学历要求</h3>
              <p>例如 本科 / 硕士，缺失保持未知。</p>
            </div>
          </div>
          <div class="fact-field">
            <input
              v-model="draft.degree_requirement.value"
              maxlength="200"
              :disabled="draft.degree_requirement.confirmation_status === 'unknown'"
              placeholder="例如 本科"
            >
          </div>
          <div class="field-meta">
            <select v-model="draft.degree_requirement.confirmation_status">
              <option
                v-for="(label, value) in statusLabels"
                :key="value"
                :value="value"
              >
                {{ label }}
              </option>
            </select>
            <span>来源：{{ reqStore.latest ? sourceLabels[reqStore.latest.content.degree_requirement.source_type] : "尚未创建" }}</span>
          </div>
        </section>

        <section class="form-section">
          <div class="form-section-title">
            <span>04</span>
            <div>
              <h3>地点要求</h3>
              <p>例如 北京，缺失保持未知。</p>
            </div>
          </div>
          <div class="fact-field">
            <input
              v-model="draft.location_requirement.value"
              maxlength="200"
              :disabled="draft.location_requirement.confirmation_status === 'unknown'"
              placeholder="例如 北京"
            >
          </div>
          <div class="field-meta">
            <select v-model="draft.location_requirement.confirmation_status">
              <option
                v-for="(label, value) in statusLabels"
                :key="value"
                :value="value"
              >
                {{ label }}
              </option>
            </select>
            <span>来源：{{ reqStore.latest ? sourceLabels[reqStore.latest.content.location_requirement.source_type] : "尚未创建" }}</span>
          </div>
        </section>

        <section class="form-section">
          <div class="form-section-title">
            <span>05</span>
            <div>
              <h3>工作方式</h3>
              <p>现场 / 混合 / 远程，缺失保持未知。</p>
            </div>
          </div>
          <div class="fact-field">
            <select
              v-model="draft.work_mode.value"
              :disabled="draft.work_mode.confirmation_status === 'unknown'"
            >
              <option
                v-for="(label, value) in workModeLabels"
                :key="value"
                :value="value"
              >
                {{ label }}
              </option>
            </select>
          </div>
          <div class="field-meta">
            <select v-model="draft.work_mode.confirmation_status">
              <option
                v-for="(label, value) in statusLabels"
                :key="value"
                :value="value"
              >
                {{ label }}
              </option>
            </select>
            <span>来源：{{ reqStore.latest ? sourceLabels[reqStore.latest.content.work_mode.source_type] : "尚未创建" }}</span>
          </div>
        </section>

        <p
          v-if="error"
          class="form-error"
          role="alert"
        >
          {{ error }}
        </p>
        <p
          v-if="notice"
          class="form-notice"
          role="status"
        >
          {{ notice }}
        </p>
        <div class="form-actions">
          <button
            class="button button-primary"
            type="submit"
            :disabled="saving"
          >
            <Save :size="17" /> {{ saving ? "正在保存…" : "保存为新版本" }}
          </button>
        </div>
      </form>

      <section class="content-section version-history">
        <div class="section-toolbar">
          <div>
            <p class="eyebrow">
              版本历史
            </p>
            <h2>岗位要求版本</h2>
          </div>
        </div>
        <p
          v-if="reqStore.versions.length === 0"
          class="empty-hint"
        >
          尚无岗位要求快照，填写并保存后创建首个版本。
        </p>
        <ul
          v-else
          class="version-list"
        >
          <li
            v-for="item in reqStore.versions"
            :key="item.version"
          >
            <span class="version-badge">v{{ item.version }}</span>
            <span>{{ new Date(item.updated_at).toLocaleString("zh-CN") }}</span>
            <span class="version-status">{{ statusLabels[item.content.required_skills.confirmation_status] }}</span>
          </li>
        </ul>
      </section>
    </template>
  </AppShell>
</template>
