<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { ArrowLeft, ClipboardCheck, Download, Eye, FileStack, FileText, MessageSquareText, RefreshCw, ShieldCheck } from "lucide-vue-next"
import { useRoute, useRouter } from "vue-router"

import { api, userMessage } from "@/api/client"
import type { MessageDraftStyle } from "@/api/types"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useMessagesStore } from "@/stores/messages"
import { useVariantsStore } from "@/stores/variants"

const messageStyles: ReadonlyArray<readonly [MessageDraftStyle, string]> = [
  ["professional", "专业"],
  ["concise", "简洁"],
  ["referral", "内推上下文"],
]

const route = useRoute()
const router = useRouter()
const store = useVariantsStore()
const messages = useMessagesStore()
const error = ref("")
const pdfError = ref("")
const previewUrl = ref("")
const transferring = ref(false)
const messageError = ref("")
const messageStyle = ref<MessageDraftStyle>("professional")
const userNote = ref("")
const referralContext = ref("")
const variantId = computed(() => String(route.params.id))

async function load(): Promise<void> {
  error.value = ""
  messages.latestForVariant = null
  try {
    const variant = await store.fetchVariant(variantId.value)
    await Promise.all([
      store.fetchTemplate(variant.template_id, variant.template_version),
      store.fetchLatestPdf(variant.id),
      messages.fetchLatestForVariant(variant.id),
    ])
  } catch (reason) { error.value = userMessage(reason) }
}

async function generateMessageDraft(): Promise<void> {
  messageError.value = ""
  if (messageStyle.value === "referral" && !referralContext.value.trim()) {
    messageError.value = "内推风格需要填写上下文"
    return
  }
  try {
    const value = await messages.generate(variantId.value, {
      style: messageStyle.value,
      user_note: userNote.value.trim() || null,
      referral_context: messageStyle.value === "referral" ? referralContext.value.trim() : null,
    })
    await router.push(`/messages/${value.id}`)
  } catch (reason) {
    messageError.value = userMessage(reason)
  }
}

async function generatePdf(): Promise<void> {
  pdfError.value = ""
  try { await store.generatePdf(variantId.value) }
  catch (reason) { pdfError.value = userMessage(reason) }
}

async function previewPdf(): Promise<void> {
  if (!store.currentPdf) return
  pdfError.value = ""
  transferring.value = true
  try {
    const blob = await api.getResumePdfContent(store.currentPdf.id, false)
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = URL.createObjectURL(blob)
  } catch (reason) { pdfError.value = userMessage(reason) }
  finally { transferring.value = false }
}

async function downloadPdf(): Promise<void> {
  if (!store.currentPdf) return
  pdfError.value = ""
  transferring.value = true
  try {
    const blob = await api.getResumePdfContent(store.currentPdf.id, true)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = `nora-resume-${store.currentPdf.id}.pdf`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (reason) { pdfError.value = userMessage(reason) }
  finally { transferring.value = false }
}

watch(variantId, () => void load(), { immediate: true })
onBeforeUnmount(() => { if (previewUrl.value) URL.revokeObjectURL(previewUrl.value) })
</script>

<template>
  <AppShell>
    <RouterLink
      class="back-link"
      to="/templates"
    >
      <ArrowLeft :size="16" /> 返回定制简历
    </RouterLink>
    <StatePanel
      v-if="store.loading && !store.current"
      mode="loading"
      title="正在读取定制简历"
    />
    <StatePanel
      v-else-if="error"
      mode="error"
      title="无法读取定制简历"
      :message="error"
      @retry="load"
    />
    <template v-else-if="store.current">
      <header class="resume-detail-header">
        <div>
          <p class="eyebrow">
            不可变岗位变体
          </p><h2>{{ store.current.title }}</h2><p>创建于 {{ new Date(store.current.created_at).toLocaleString('zh-CN') }}</p>
        </div>
        <div class="detail-actions">
          <RouterLink
            class="button button-primary"
            :to="`/applications/new?variant=${store.current.id}`"
          >
            <ClipboardCheck :size="17" /> 创建投递记录
          </RouterLink>
          <span class="immutable-badge"><ShieldCheck :size="18" /><span><strong>变体 v{{ store.current.version }}</strong><small>{{ store.currentTemplate?.name || '模板' }} v{{ store.current.template_version }}</small></span></span>
          <button
            class="icon-button"
            type="button"
            title="刷新"
            aria-label="刷新"
            @click="load"
          >
            <RefreshCw :size="17" />
          </button>
        </div>
      </header>
      <dl class="variant-provenance">
        <div><dt>投递决定</dt><dd>{{ store.current.application_decision_id }}</dd></div>
        <div><dt>决策案例</dt><dd>{{ store.current.decision_case_id }}</dd></div>
        <div><dt>岗位版本</dt><dd>{{ store.current.job_posting_id }} · v{{ store.current.job_posting_version }}</dd></div>
        <div><dt>岗位要求</dt><dd>{{ store.current.job_requirement_snapshot_id }} · v{{ store.current.job_requirement_snapshot_version }}</dd></div>
        <div><dt>来源简历</dt><dd>{{ store.current.resume_version_id }} · v{{ store.current.resume_version }}</dd></div>
        <div><dt>生成器版本</dt><dd>{{ store.current.generator_version }}</dd></div>
        <div><dt>内容指纹</dt><dd><code>{{ store.current.content_fingerprint }}</code></dd></div>
      </dl>
      <section
        class="variant-document"
        :class="`accent-${store.currentTemplate?.accent || 'neutral'} density-${store.currentTemplate?.density || 'standard'}`"
      >
        <header><FileStack :size="20" /><span>{{ store.currentTemplate?.name }}</span></header>
        <article
          v-for="block in store.current.blocks"
          :key="block.source_path"
          class="variant-block"
        >
          <small>{{ block.label }}</small><p>{{ block.value }}</p>
        </article>
      </section>
      <section class="pdf-band">
        <div class="pdf-band-heading">
          <span class="metric-icon blue"><FileText :size="19" /></span>
          <div>
            <p class="eyebrow">
              确定性产物
            </p>
            <h3>PDF 简历</h3>
          </div>
          <span
            v-if="store.currentPdf"
            class="version-badge"
          >{{ store.currentPdf.status === 'available' ? '可用' : store.currentPdf.status === 'failed' ? '生成失败' : '生成中' }}</span>
        </div>
        <dl
          v-if="store.currentPdf?.status === 'available'"
          class="pdf-metadata"
        >
          <div><dt>Artifact</dt><dd>{{ store.currentPdf.artifact_id }} · v{{ store.currentPdf.artifact_version }}</dd></div>
          <div><dt>SHA-256</dt><dd><code>{{ store.currentPdf.artifact_sha256 }}</code></dd></div>
          <div><dt>渲染环境</dt><dd>{{ store.currentPdf.renderer_version }}</dd></div>
          <div><dt>字体集</dt><dd>{{ store.currentPdf.font_set_version }}</dd></div>
        </dl>
        <p
          v-if="pdfError"
          class="form-error"
          role="alert"
        >
          {{ pdfError }}
        </p>
        <div class="pdf-actions">
          <button
            v-if="!store.currentPdf || store.currentPdf.status !== 'available'"
            class="button button-primary"
            type="button"
            :disabled="store.generatingPdf"
            @click="generatePdf"
          >
            <RefreshCw :size="17" /> {{ store.generatingPdf ? '正在生成…' : store.currentPdf?.status === 'failed' ? '重试生成' : '生成 PDF' }}
          </button>
          <template v-else>
            <button
              class="button button-secondary"
              type="button"
              :disabled="transferring"
              @click="previewPdf"
            >
              <Eye :size="17" /> 预览
            </button>
            <button
              class="button button-primary"
              type="button"
              :disabled="transferring"
              @click="downloadPdf"
            >
              <Download :size="17" /> 下载
            </button>
          </template>
        </div>
        <iframe
          v-if="previewUrl"
          class="pdf-preview"
          :src="previewUrl"
          title="定制简历 PDF 预览"
        />
      </section>
      <section class="message-draft-band">
        <div class="pdf-band-heading">
          <span class="metric-icon green"><MessageSquareText :size="19" /></span>
          <div>
            <p class="eyebrow">
              确定性纯文本
            </p>
            <h3>消息草稿</h3>
          </div>
          <RouterLink
            v-if="messages.latestForVariant"
            class="button button-secondary"
            :to="`/messages/${messages.latestForVariant.id}`"
          >
            打开 v{{ messages.latestForVariant.version }}
          </RouterLink>
        </div>
        <div
          class="message-style-control"
          role="group"
          aria-label="消息草稿风格"
        >
          <button
            v-for="option in messageStyles"
            :key="option[0]"
            type="button"
            :class="{ active: messageStyle === option[0] }"
            @click="messageStyle = option[0]"
          >
            {{ option[1] }}
          </button>
        </div>
        <div class="message-inputs">
          <label>
            <span>用户备注</span>
            <textarea
              v-model="userNote"
              aria-label="用户备注"
              rows="3"
              maxlength="1000"
            />
          </label>
          <label v-if="messageStyle === 'referral'">
            <span>内推上下文</span>
            <textarea
              v-model="referralContext"
              aria-label="内推上下文"
              rows="3"
              maxlength="1000"
              required
            />
          </label>
        </div>
        <p
          v-if="messageError"
          class="form-error"
          role="alert"
        >
          {{ messageError }}
        </p>
        <div class="pdf-actions">
          <button
            class="button button-primary"
            type="button"
            :disabled="messages.generating"
            @click="generateMessageDraft"
          >
            <MessageSquareText :size="17" /> {{ messages.generating ? '正在生成…' : '生成草稿' }}
          </button>
        </div>
      </section>
      <section class="locked-band">
        <ShieldCheck :size="18" /><div><strong>版本已固定</strong><p>刷新只读取同一变体；来源简历或模板升级不会改写这份内容。</p></div>
      </section>
    </template>
  </AppShell>
</template>
