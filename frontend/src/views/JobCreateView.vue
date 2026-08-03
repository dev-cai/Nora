<script setup lang="ts">
import { reactive, ref } from "vue"
import { FileText, Image, Link2, Save } from "lucide-vue-next"
import { useRouter } from "vue-router"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import { useJobsStore } from "@/stores/jobs"

const router = useRouter()
const jobs = useJobsStore()
const loading = ref(false)
const error = ref("")
const form = reactive({ job_title: "", company_name: "", location: "", jd_text: "" })

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
        class="mode-tab active"
        type="button"
      >
        <FileText :size="17" /> 文本
      </button>
      <button
        class="mode-tab"
        type="button"
        disabled
        title="M3.7 开放"
      >
        <Image :size="17" /> 截图 <span>稍后</span>
      </button>
      <button
        class="mode-tab"
        type="button"
        disabled
        title="M3.7 开放"
      >
        <Link2 :size="17" /> 链接 <span>稍后</span>
      </button>
    </div>
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
