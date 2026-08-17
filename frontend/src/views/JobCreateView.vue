<script setup lang="ts">
import { reactive, ref } from "vue"
import { FileText, Image, Link2, Save } from "lucide-vue-next"
import { useRouter } from "vue-router"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import { useJobsStore } from "@/stores/jobs"

type InputMode = "text" | "image" | "url"

const router = useRouter()
const jobs = useJobsStore()
const loading = ref(false)
const error = ref("")
const mode = ref<InputMode>("text")
const previewError = ref("")
const previewUrl = ref("")
const imageInput = ref<HTMLInputElement | null>(null)
const form = reactive({ job_title: "", company_name: "", location: "", jd_text: "" })

function selectMode(next: InputMode): void {
  mode.value = next
  previewError.value = ""
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
    form.jd_text = preview.jd_text
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
    form.jd_text = preview.jd_text
  } catch (reason) {
    previewError.value = userMessage(reason)
  } finally {
    if (imageInput.value) imageInput.value.value = ""
  }
}

async function submit(): Promise<void> {
  error.value = ""
  if (!form.job_title.trim() || !form.company_name.trim() || !form.location.trim() || !form.jd_text.trim()) {
    error.value = "请完整填写职位、公司、地点和 JD 正文"
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
        <span>提取</span><div><h3>从截图提取 JD 正文</h3><p>支持 PNG / JPEG，单张不超过 10 MiB。</p></div>
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
        :disabled="jobs.previewLoading"
        @click="pickImage"
      >
        <Image :size="17" /> {{ jobs.previewLoading ? "正在识别…" : "选择截图" }}
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
        <span>提取</span><div><h3>从链接提取 JD 正文</h3><p>仅支持公网 http/https 地址。</p></div>
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
        :disabled="jobs.previewLoading"
        @click="previewFromUrl"
      >
        <Link2 :size="17" /> {{ jobs.previewLoading ? "正在抓取…" : "提取正文" }}
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
        >
          取消
        </RouterLink><button
          class="button button-primary"
          type="submit"
          :disabled="loading"
        >
          <Save :size="17" /> {{ loading ? "正在保存…" : "保存岗位快照" }}
        </button>
      </div>
    </form>
  </AppShell>
</template>
