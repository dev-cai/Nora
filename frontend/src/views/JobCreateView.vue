<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { FileText, Image, Link2, Save } from "lucide-vue-next"
import { useRouter } from "vue-router"

import { userMessage } from "@/api/client"
import type { JdImportDraftContent, JdImportRequirementFact, JdImportSourceType } from "@/api/types"
import AppShell from "@/components/AppShell.vue"
import { useJobsStore } from "@/stores/jobs"

type InputMode = "text" | "image" | "url"

const router = useRouter()
const jobs = useJobsStore()
const loading = ref(false)
const error = ref("")
const aiImportFailed = ref(false)
const mode = ref<InputMode>("text")
const previewError = ref("")
const previewUrl = ref("")
const imageInput = ref<HTMLInputElement | null>(null)
const form = reactive({ job_title: "", company_name: "", location: "", jd_text: "" })
const requirements = reactive({
  required_skills: "",
  minimum_experience_years: "",
  degree_requirement: "",
  location_requirement: "",
  work_mode: "",
})
const hasCompleteManualFields = computed(() =>
  [form.job_title, form.company_name, form.location, form.jd_text].every((value) => value.trim().length > 0),
)

function selectMode(next: InputMode): void {
  mode.value = next
  previewError.value = ""
  aiImportFailed.value = false
}

async function restoreDraft(): Promise<void> {
  try {
    const draft = await jobs.restoreJdImport()
    if (!draft) return
    mode.value = draft.source_type
    previewUrl.value = draft.source_url ?? ""
    applyDraft(draft.content)
  } catch (reason) {
    error.value = userMessage(reason)
  }
}

async function previewFromUrl(): Promise<void> {
  previewError.value = ""
  const url = previewUrl.value.trim()
  if (!url) {
    previewError.value = "请输入链接地址"
    return
  }
  try {
    const preview = await jobs.fetchPreviewFromUrl(url)
    await createDraft("url", url, preview.jd_text)
  } catch (reason) {
    previewError.value = userMessage(reason)
  }
}

function pickImage(): void {
  imageInput.value?.click()
}

async function previewFromImage(event: Event): Promise<void> {
  previewError.value = ""
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const preview = await jobs.fetchPreviewFromImage(file)
    await createDraft("image", null, preview.jd_text)
  } catch (reason) {
    previewError.value = userMessage(reason)
  } finally {
    if (imageInput.value) imageInput.value.value = ""
  }
}

function importSourceType(): JdImportSourceType {
  return mode.value === "image" ? "image" : mode.value === "url" ? "url" : "text"
}

function applyDraft(content: JdImportDraftContent): void {
  form.jd_text = content.jd_text
  form.job_title = content.job_title ?? ""
  form.company_name = content.company_name ?? ""
  form.location = content.location ?? ""
  requirements.required_skills = content.requirements.required_skills.value?.join(", ") ?? ""
  requirements.minimum_experience_years = content.requirements.minimum_experience_years.value?.toString() ?? ""
  requirements.degree_requirement = content.requirements.degree_requirement.value ?? ""
  requirements.location_requirement = content.requirements.location_requirement.value ?? ""
  requirements.work_mode = content.requirements.work_mode.value ?? ""
}

function draftContent(): JdImportDraftContent {
  const fact = <T>(value: T | null, sourceType: "manual" | "text_range" = "manual"): JdImportRequirementFact<T> => ({
    value,
    confirmation_status: value === null || value === "" || (Array.isArray(value) && value.length === 0) ? "unknown" as const : "unconfirmed" as const,
    source_type: sourceType,
    source_range: null,
  })
  const years = String(requirements.minimum_experience_years).trim()
  if (years && !/^\d+$/.test(years)) {
    throw new Error("最低经验年限必须是非负整数")
  }
  return {
    jd_text: form.jd_text,
    job_title: form.job_title.trim() || null,
    company_name: form.company_name.trim() || null,
    location: form.location.trim() || null,
    requirements: {
      required_skills: fact(requirements.required_skills.split(",").map((item) => item.trim()).filter(Boolean)),
      minimum_experience_years: fact(years ? Number(years) : null),
      degree_requirement: fact(requirements.degree_requirement.trim() || null),
      location_requirement: fact(requirements.location_requirement.trim() || null),
      work_mode: fact(
        (["onsite", "hybrid", "remote"] as const).includes(requirements.work_mode.trim() as "onsite" | "hybrid" | "remote")
          ? requirements.work_mode.trim() as "onsite" | "hybrid" | "remote"
          : null,
      ),
    },
  }
}

onMounted(() => { void restoreDraft() })

async function createDraft(
  sourceType: JdImportSourceType = importSourceType(),
  sourceUrl: string | null = null,
  jdText = form.jd_text,
): Promise<void> {
  aiImportFailed.value = false
  try {
    const draft = await jobs.createJdImport(sourceType, jdText, sourceUrl)
    applyDraft(draft.content)
  } catch (reason) {
    aiImportFailed.value = true
    throw reason
  }
}

async function saveManualFallback(): Promise<void> {
  error.value = ""
  if (!aiImportFailed.value) {
    error.value = "请先尝试 AI 自动识别"
    return
  }
  if (!hasCompleteManualFields.value) {
    error.value = "AI 自动识别不可用时，请完整填写职位、公司、地点和 JD 正文后再使用手动兜底"
    return
  }
  loading.value = true
  try {
    const job = await jobs.createJob({ ...form, source_type: "manual" })
    await router.push({ name: "job-detail", params: { id: job.id } })
  } catch (reason) {
    error.value = userMessage(reason)
  } finally {
    loading.value = false
  }
}

async function submit(): Promise<void> {
  error.value = ""
  if (!form.jd_text.trim()) {
    error.value = "请先填写 JD 正文"
    return
  }
  loading.value = true
  try {
    if (!jobs.importDraft) {
      await createDraft()
      return
    }
    await jobs.updateJdImport(draftContent())
    const job = await jobs.confirmJdImport()
    await router.push({ name: "job-detail", params: { id: job.id } })
  } catch (reason) {
    error.value = userMessage(reason)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AppShell>
    <section class="section-toolbar page-toolbar">
      <div>
        <p class="eyebrow">
          新建快照
        </p><h2>录入岗位</h2><p>保存你实际看到的职位信息与原始 JD。</p>
      </div>
    </section>
    <div
      class="mode-tabs"
      role="tablist"
      aria-label="岗位输入方式"
    >
      <button
        class="mode-tab"
        :class="{ active: mode === 'text' }"
        type="button"
        @click="selectMode('text')"
      >
        <FileText :size="17" /> 文本
      </button>
      <button
        class="mode-tab"
        :class="{ active: mode === 'image' }"
        type="button"
        @click="selectMode('image')"
      >
        <Image :size="17" /> 截图
      </button>
      <button
        class="mode-tab"
        :class="{ active: mode === 'url' }"
        type="button"
        @click="selectMode('url')"
      >
        <Link2 :size="17" /> 链接
      </button>
    </div>
    <section
      v-if="mode === 'image'"
      class="form-section"
    >
      <div class="form-section-title">
        <span>提取</span><div><h3>从截图提取并自动识别</h3><p>支持 PNG / JPEG，单张不超过 10 MiB。</p></div>
      </div>
      <input
        ref="imageInput"
        type="file"
        accept="image/png,image/jpeg"
        class="sr-only"
        @change="previewFromImage"
      >
      <button
        class="button button-secondary"
        type="button"
        :disabled="jobs.previewLoading || jobs.importLoading"
        @click="pickImage"
      >
        <Image :size="17" /> {{ jobs.previewLoading ? "正在提取…" : jobs.importLoading ? "正在 AI 识别…" : "选择截图" }}
      </button>
      <p
        v-if="previewError"
        class="form-error"
        role="alert"
      >
        {{ previewError }}
      </p>
    </section>
    <section
      v-else-if="mode === 'url'"
      class="form-section"
    >
      <div class="form-section-title">
        <span>提取</span><div><h3>从链接提取并自动识别</h3><p>仅支持公网 http/https 地址。</p></div>
      </div>
      <div class="form-grid">
        <label>岗位链接<input
          v-model="previewUrl"
          type="url"
          maxlength="2048"
          placeholder="https://example.com/jobs/123"
        ></label>
      </div>
      <button
        class="button button-secondary"
        type="button"
        :disabled="jobs.previewLoading || jobs.importLoading"
        @click="previewFromUrl"
      >
        <Link2 :size="17" /> {{ jobs.previewLoading ? "正在提取…" : jobs.importLoading ? "正在 AI 识别…" : "提取并识别" }}
      </button>
      <p
        v-if="previewError"
        class="form-error"
        role="alert"
      >
        {{ previewError }}
      </p>
    </section>
    <form
      class="job-form"
      @submit.prevent="submit"
    >
      <section class="form-section">
        <div class="form-section-title">
          <span>01</span><div><h3>岗位信息</h3><p>用于列表检索和快速识别。</p></div>
        </div>
        <div class="form-grid three-columns">
          <label>职位名称<input
            v-model="form.job_title"
            maxlength="200"
            placeholder="例如 后端开发工程师"
          ></label>
          <label>公司名称<input
            v-model="form.company_name"
            maxlength="200"
            placeholder="例如 Example Corp"
          ></label>
          <label>工作地点<input
            v-model="form.location"
            maxlength="200"
            placeholder="例如 上海 / 远程"
          ></label>
        </div>
      </section>
      <section class="form-section">
        <div class="form-section-title">
          <span>02</span><div><h3>JD 正文</h3><p>保留原始职责、要求与补充信息。</p></div>
        </div>
        <label>岗位描述<textarea
          v-model="form.jd_text"
          rows="16"
          maxlength="100000"
          placeholder="粘贴完整 JD…"
        /></label>
        <div class="character-count">
          {{ form.jd_text.length.toLocaleString() }} / 100,000
        </div>
      </section>
      <section
        v-if="jobs.importDraft"
        class="form-section"
      >
        <div class="form-section-title">
          <span>03</span><div><h3>结构化岗位要求</h3><p>AI 生成候选，你可以修改任意字段后一次确认导入。</p></div>
        </div>
        <div class="form-grid three-columns">
          <label>必备技能（逗号分隔）<input
            v-model="requirements.required_skills"
            placeholder="Python, FastAPI"
          ></label>
          <label>最低经验年限<input
            v-model="requirements.minimum_experience_years"
            type="number"
            min="0"
          ></label>
          <label>学历要求<input
            v-model="requirements.degree_requirement"
            placeholder="本科"
          ></label>
          <label>地点要求<input
            v-model="requirements.location_requirement"
            placeholder="上海 / 远程"
          ></label>
          <label>工作方式<select v-model="requirements.work_mode">
            <option value="">未知</option>
            <option value="onsite">现场办公</option>
            <option value="hybrid">混合办公</option>
            <option value="remote">远程</option>
          </select></label>
        </div>
      </section>
      <p
        v-if="error"
        class="form-error"
        role="alert"
      >
        {{ error }}
      </p>
      <div class="form-actions">
        <RouterLink
          class="button button-secondary"
          to="/jobs"
          @click="jobs.discardJdImport()"
        >
          取消
        </RouterLink><button
          v-if="!jobs.importDraft && aiImportFailed && hasCompleteManualFields"
          class="button button-secondary"
          type="button"
          :disabled="loading"
          @click="saveManualFallback"
        >
          手动填写兜底
        </button><button
          class="button button-primary"
          type="submit"
          :disabled="loading"
        >
          <Save :size="17" /> {{ loading ? "正在确认…" : jobs.importDraft ? "确认导入岗位" : "AI 自动识别" }}
        </button>
      </div>
    </form>
  </AppShell>
</template>
