<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowLeft, CheckCircle2, FileText, MessageSquareText } from "lucide-vue-next"
import { useRoute, useRouter } from "vue-router"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useApplicationsStore } from "@/stores/applications"
import { useMessagesStore } from "@/stores/messages"
import { useVariantsStore } from "@/stores/variants"

const route = useRoute()
const router = useRouter()
const applications = useApplicationsStore()
const variants = useVariantsStore()
const messages = useMessagesStore()
const variantId = computed(() => String(route.query.variant || ""))
const includePdf = ref(true)
const includeDraft = ref(true)
const error = ref("")

async function load(): Promise<void> {
  error.value = ""
  if (!variantId.value) {
    error.value = "缺少定制简历"
    return
  }
  try {
    const variant = await variants.fetchVariant(variantId.value)
    await Promise.all([
      variants.fetchLatestPdf(variant.id),
      messages.fetchLatestForVariant(variant.id),
    ])
    includePdf.value = variants.currentPdf?.status === "available"
    includeDraft.value = messages.latestForVariant !== null
  } catch (reason) { error.value = userMessage(reason) }
}

async function create(): Promise<void> {
  if (!variants.current) return
  error.value = ""
  try {
    const record = await applications.create({
      application_decision_id: variants.current.application_decision_id,
      resume_variant_id: variants.current.id,
      resume_pdf_id: includePdf.value ? variants.currentPdf?.id ?? null : null,
      message_draft_id: includeDraft.value ? messages.latestForVariant?.id ?? null : null,
      message_draft_version: includeDraft.value ? messages.latestForVariant?.version ?? null : null,
    })
    await router.push(`/applications/${record.id}`)
  } catch (reason) { error.value = userMessage(reason) }
}

watch(variantId, () => void load(), { immediate: true })
</script>

<template>
  <AppShell>
    <RouterLink
      class="back-link"
      :to="variantId ? `/resume-variants/${variantId}` : '/templates'"
    >
      <ArrowLeft :size="16" /> 返回定制简历
    </RouterLink>
    <StatePanel
      v-if="variants.loading && !variants.current"
      mode="loading"
      title="正在读取投递材料"
    />
    <StatePanel
      v-else-if="error && !variants.current"
      mode="error"
      title="无法读取投递材料"
      :message="error"
      @retry="load"
    />
    <template v-else-if="variants.current">
      <header class="resume-detail-header">
        <div>
          <p class="eyebrow">
            创建 planned 记录
          </p>
          <h2>确认投递材料</h2>
          <p>{{ variants.current.title }}</p>
        </div>
        <span class="version-badge">尚未标记已投递</span>
      </header>
      <section class="application-confirmation">
        <div class="application-source-row required">
          <CheckCircle2 :size="20" />
          <div>
            <strong>定制简历 v{{ variants.current.version }}</strong>
            <small>{{ variants.current.id }}</small>
          </div>
          <span>必选</span>
        </div>
        <label class="application-source-row">
          <input
            v-model="includePdf"
            type="checkbox"
            :disabled="variants.currentPdf?.status !== 'available'"
          >
          <FileText :size="20" />
          <span>
            <strong>PDF Artifact</strong>
            <small v-if="variants.currentPdf?.status === 'available'">
              {{ variants.currentPdf.artifact_id }} · v{{ variants.currentPdf.artifact_version }}
            </small>
            <small v-else>当前无可用 PDF</small>
          </span>
        </label>
        <label class="application-source-row">
          <input
            v-model="includeDraft"
            type="checkbox"
            :disabled="!messages.latestForVariant"
          >
          <MessageSquareText :size="20" />
          <span>
            <strong>消息草稿</strong>
            <small v-if="messages.latestForVariant">
              {{ messages.latestForVariant.id }} · v{{ messages.latestForVariant.version }}
            </small>
            <small v-else>当前无消息草稿</small>
          </span>
        </label>
        <p
          v-if="error"
          class="form-error"
          role="alert"
        >
          {{ error }}
        </p>
        <div class="form-actions">
          <button
            class="button button-primary"
            type="button"
            :disabled="applications.saving"
            @click="create"
          >
            <CheckCircle2 :size="17" />
            {{ applications.saving ? '正在创建…' : '创建待确认记录' }}
          </button>
        </div>
      </section>
    </template>
  </AppShell>
</template>
