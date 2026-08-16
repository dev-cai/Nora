<script setup lang="ts">
import { reactive, ref, watch } from "vue"
import { Globe2, NotebookPen, Save } from "lucide-vue-next"

import type { CompanyFieldStatus, CompanySnapshot, CompanySourceTier } from "@/api/types"
import type { CompanySnapshotSubmission } from "@/stores/companies"

const props = withDefaults(defineProps<{
  initial?: CompanySnapshot | null
  saving?: boolean
  companyNameReadonly?: boolean
  submitLabel?: string
}>(), {
  initial: null,
  saving: false,
  companyNameReadonly: false,
  submitLabel: "保存公司情报",
})
const emit = defineEmits<{ submit: [value: CompanySnapshotSubmission] }>()

const statusOptions: Array<{ value: CompanyFieldStatus; label: string }> = [
  { value: "confirmed", label: "已确认" },
  { value: "unconfirmed", label: "待确认" },
  { value: "unknown", label: "未知" },
  { value: "conflicted", label: "存在冲突" },
  { value: "superseded", label: "已被替代" },
]
const tierOptions: Array<{ value: CompanySourceTier; label: string }> = [
  { value: "official/company", label: "公司官方" },
  { value: "reputable_media", label: "可信媒体" },
  { value: "verified_platform", label: "已验证平台" },
  { value: "anonymous_platform", label: "匿名平台" },
]

function localDateTime(value: Date): string {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

const form = reactive({
  companyName: "",
  size: "",
  sizeStatus: "unknown" as CompanyFieldStatus,
  industry: "",
  industryStatus: "unknown" as CompanyFieldStatus,
  reviewSummary: "",
  reviewStatus: "unknown" as CompanyFieldStatus,
  sourceKind: "manual" as "manual" | "web",
  sourceLocator: "",
  sourceContent: "",
  sourceTier: "official/company" as CompanySourceTier,
  acquisitionMethod: "user_entry",
  licenseNote: "用户提供，仅用于个人求职决策",
  acquiredAt: localDateTime(new Date()),
  publishedAt: "",
})
const error = ref("")

function restore(snapshot: CompanySnapshot | null): void {
  if (!snapshot) return
  form.companyName = snapshot.company_name
  form.size = snapshot.size ?? ""
  form.sizeStatus = snapshot.size_status
  form.industry = snapshot.industry ?? ""
  form.industryStatus = snapshot.industry_status
  form.reviewSummary = snapshot.review_summary ?? ""
  form.reviewStatus = snapshot.review_status
  form.sourceTier = snapshot.source.tier
  form.sourceKind = snapshot.source.kind === "web" ? "web" : "manual"
  form.acquisitionMethod = snapshot.source.acquisition_method
  form.licenseNote = snapshot.source.license_note
  form.acquiredAt = localDateTime(new Date())
  form.publishedAt = snapshot.source.published_at
    ? localDateTime(new Date(snapshot.source.published_at))
    : ""
  form.sourceLocator = ""
  form.sourceContent = ""
}

function normalizedValue(value: string, status: CompanyFieldStatus): string | null {
  return status === "unknown" ? null : value.trim() || null
}

function submit(): void {
  error.value = ""
  const companyName = form.companyName.trim()
  const size = normalizedValue(form.size, form.sizeStatus)
  const industry = normalizedValue(form.industry, form.industryStatus)
  const reviewSummary = normalizedValue(form.reviewSummary, form.reviewStatus)
  if (!companyName) {
    error.value = "请填写公司名称"
    return
  }
  if (!form.sourceContent.trim()) {
    error.value = "请填写来源原文或人工记录"
    return
  }
  if (!size && form.sizeStatus !== "unknown") {
    error.value = "公司规模状态不是未知时必须填写内容"
    return
  }
  if (!industry && form.industryStatus !== "unknown") {
    error.value = "行业状态不是未知时必须填写内容"
    return
  }
  if (!reviewSummary && form.reviewStatus !== "unknown") {
    error.value = "摘要状态不是未知时必须填写内容"
    return
  }
  if (form.sourceKind === "web") {
    try {
      const url = new URL(form.sourceLocator)
      if (!['http:', 'https:'].includes(url.protocol)) throw new Error("invalid protocol")
    } catch {
      error.value = "网页来源必须填写有效的 HTTP 或 HTTPS 地址"
      return
    }
  }
  const acquired = new Date(form.acquiredAt)
  const published = form.publishedAt ? new Date(form.publishedAt) : null
  if (Number.isNaN(acquired.getTime()) || (published && Number.isNaN(published.getTime()))) {
    error.value = "来源时间无效"
    return
  }
  if (published && published > acquired) {
    error.value = "发布时间不能晚于获取时间"
    return
  }
  const statuses = [form.sizeStatus, form.industryStatus, form.reviewStatus]
  if (form.sourceTier === "anonymous_platform" && statuses.includes("confirmed")) {
    error.value = "匿名来源不能将字段标记为已确认"
    return
  }
  if (published && (acquired.getTime() - published.getTime()) / 86_400_000 > 730 && statuses.includes("confirmed")) {
    error.value = "过期来源不能将字段标记为当前已确认事实"
    return
  }
  emit("submit", {
    company_name: companyName,
    size,
    size_status: form.sizeStatus,
    industry,
    industry_status: form.industryStatus,
    review_summary: reviewSummary,
    review_status: form.reviewStatus,
    source: {
      content: form.sourceContent.trim(),
      kind: form.sourceKind,
      locator: form.sourceKind === "web" ? form.sourceLocator.trim() : null,
      acquisition_method: form.acquisitionMethod.trim(),
      license_note: form.licenseNote.trim(),
      acquired_at: acquired.toISOString(),
      published_at: published?.toISOString() ?? null,
      tier: form.sourceTier,
    },
  })
}

watch(() => props.initial, restore, { immediate: true })
</script>

<template>
  <form
    class="company-form"
    @submit.prevent="submit"
  >
    <section class="form-section">
      <div class="form-section-heading">
        <div><span>01</span><h3>公司字段</h3></div>
        <p>每个字段保留独立确认状态。</p>
      </div>
      <div class="form-grid two-columns">
        <label>公司名称<input
          v-model="form.companyName"
          :readonly="companyNameReadonly"
          maxlength="200"
        ></label>
        <div class="company-field">
          <label for="company-size">公司规模</label>
          <div class="company-value-status">
            <input
              id="company-size"
              v-model="form.size"
              :disabled="form.sizeStatus === 'unknown'"
              maxlength="200"
            >
            <select
              v-model="form.sizeStatus"
              aria-label="公司规模状态"
            >
              <option
                v-for="option in statusOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
          </div>
        </div>
        <div class="company-field">
          <label for="company-industry">行业</label>
          <div class="company-value-status">
            <input
              id="company-industry"
              v-model="form.industry"
              :disabled="form.industryStatus === 'unknown'"
              maxlength="200"
            >
            <select
              v-model="form.industryStatus"
              aria-label="行业状态"
            >
              <option
                v-for="option in statusOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
          </div>
        </div>
        <div class="company-field company-summary-input">
          <label for="company-summary">来源摘要</label>
          <div class="company-value-status">
            <textarea
              id="company-summary"
              v-model="form.reviewSummary"
              :disabled="form.reviewStatus === 'unknown'"
              maxlength="2000"
            />
            <select
              v-model="form.reviewStatus"
              aria-label="来源摘要状态"
            >
              <option
                v-for="option in statusOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
          </div>
        </div>
      </div>
    </section>

    <section class="form-section">
      <div class="form-section-heading">
        <div><span>02</span><h3>来源记录</h3></div>
        <p>原文作为私有 Artifact 保存，页面仅展示安全元数据。</p>
      </div>
      <div
        class="company-source-mode"
        role="group"
        aria-label="来源类型"
      >
        <button
          type="button"
          :class="{ active: form.sourceKind === 'manual' }"
          @click="form.sourceKind = 'manual'"
        >
          <NotebookPen :size="16" /> 人工记录
        </button>
        <button
          type="button"
          :class="{ active: form.sourceKind === 'web' }"
          @click="form.sourceKind = 'web'"
        >
          <Globe2 :size="16" /> 网页来源
        </button>
      </div>
      <div class="form-grid two-columns company-source-grid">
        <label
          v-if="form.sourceKind === 'web'"
          class="company-full-field"
        >来源 URL<input
          v-model="form.sourceLocator"
          type="url"
          maxlength="2000"
          placeholder="https://"
        ></label>
        <label class="company-full-field">来源原文或人工记录<textarea
          v-model="form.sourceContent"
          maxlength="10000"
        /></label>
        <label>来源层级<select v-model="form.sourceTier"><option
          v-for="option in tierOptions"
          :key="option.value"
          :value="option.value"
        >{{ option.label }}</option></select></label>
        <label>录入方式<input
          v-model="form.acquisitionMethod"
          maxlength="100"
        ></label>
        <label>获取时间<input
          v-model="form.acquiredAt"
          type="datetime-local"
        ></label>
        <label>发布时间<input
          v-model="form.publishedAt"
          type="datetime-local"
        ></label>
        <label class="company-full-field">许可或使用说明<input
          v-model="form.licenseNote"
          maxlength="500"
        ></label>
      </div>
    </section>

    <p
      v-if="error"
      class="form-error"
    >
      {{ error }}
    </p>
    <div class="form-actions company-form-actions">
      <button
        class="button button-primary"
        type="submit"
        :disabled="saving"
      >
        <Save :size="17" /> {{ saving ? '保存中…' : submitLabel }}
      </button>
    </div>
  </form>
</template>
