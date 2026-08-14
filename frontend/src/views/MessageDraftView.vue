<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowLeft, Check, Clipboard, History, RefreshCw, Save, ShieldCheck } from "lucide-vue-next"
import { useRoute } from "vue-router"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useMessagesStore } from "@/stores/messages"

const route = useRoute()
const store = useMessagesStore()
const draftId = computed(() => String(route.params.id))
const editableText = ref("")
const error = ref("")
const copied = ref(false)

const hasChanges = computed(() => (
  store.current !== null && editableText.value !== store.current.text
))

async function load(): Promise<void> {
  error.value = ""
  copied.value = false
  try {
    const draft = await store.fetchDraft(draftId.value)
    editableText.value = draft.text
    await store.fetchVersions(draft.id)
  } catch (reason) {
    error.value = userMessage(reason)
  }
}

async function save(): Promise<void> {
  error.value = ""
  try {
    const draft = await store.save(editableText.value)
    editableText.value = draft.text
  } catch (reason) {
    error.value = userMessage(reason)
  }
}

async function copy(): Promise<void> {
  error.value = ""
  try {
    await navigator.clipboard.writeText(editableText.value)
    copied.value = true
  } catch {
    error.value = "无法写入剪贴板"
  }
}

watch(draftId, () => void load(), { immediate: true })
watch(editableText, () => { copied.value = false })
</script>

<template>
  <AppShell>
    <RouterLink
      v-if="store.current"
      class="back-link"
      :to="`/resume-variants/${store.current.resume_variant_id}`"
    >
      <ArrowLeft :size="16" /> 返回定制简历
    </RouterLink>
    <StatePanel
      v-if="store.loading && !store.current"
      mode="loading"
      title="正在读取消息草稿"
    />
    <StatePanel
      v-else-if="error && !store.current"
      mode="error"
      title="无法读取消息草稿"
      :message="error"
      @retry="load"
    />
    <template v-else-if="store.current">
      <header class="message-draft-header">
        <div>
          <p class="eyebrow">
            纯文本草稿
          </p>
          <h2>{{ store.current.style === 'professional' ? '专业风格' : store.current.style === 'concise' ? '简洁风格' : '内推上下文风格' }}</h2>
          <p>版本 {{ store.current.version }} · {{ new Date(store.current.created_at).toLocaleString('zh-CN') }}</p>
        </div>
        <div class="detail-actions">
          <span class="immutable-badge"><ShieldCheck :size="18" /><span><strong>修订 v{{ store.current.version }}</strong><small>{{ store.current.revision_type === 'generated' ? '确定性生成' : '用户编辑' }}</small></span></span>
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

      <section class="message-editor-band">
        <textarea
          v-model="editableText"
          aria-label="消息草稿内容"
          maxlength="4000"
          rows="12"
        />
        <p
          v-if="error"
          class="form-error"
          role="alert"
        >
          {{ error }}
        </p>
        <div class="message-editor-actions">
          <span class="text-counter">{{ editableText.length }} / 4000</span>
          <button
            class="button button-secondary"
            type="button"
            :disabled="!editableText || store.saving"
            @click="copy"
          >
            <Check
              v-if="copied"
              :size="17"
            />
            <Clipboard
              v-else
              :size="17"
            />
            {{ copied ? '已复制' : '复制' }}
          </button>
          <button
            class="button button-primary"
            type="button"
            :disabled="!hasChanges || store.saving"
            @click="save"
          >
            <Save :size="17" /> {{ store.saving ? '正在保存…' : '保存新版本' }}
          </button>
        </div>
      </section>

      <section class="message-provenance-band">
        <div class="message-band-heading">
          <History :size="19" />
          <h3>版本与来源</h3>
        </div>
        <dl class="variant-provenance">
          <div><dt>投递决定</dt><dd>{{ store.current.application_decision_id }}</dd></div>
          <div><dt>决策案例</dt><dd>{{ store.current.decision_case_id }}</dd></div>
          <div><dt>岗位版本</dt><dd>{{ store.current.job_posting_id }} · v{{ store.current.job_posting_version }}</dd></div>
          <div><dt>来源简历</dt><dd>{{ store.current.resume_version_id }} · v{{ store.current.resume_version }}</dd></div>
          <div><dt>定制简历</dt><dd>{{ store.current.resume_variant_id }} · v{{ store.current.resume_variant_version }}</dd></div>
          <div><dt>公司情报</dt><dd>{{ store.current.company_snapshot_id ? `${store.current.company_snapshot_id} · v${store.current.company_snapshot_version}` : '未引用' }}</dd></div>
          <div><dt>生成器</dt><dd>{{ store.current.generator_version }} · {{ store.current.template_version }}</dd></div>
          <div><dt>内容指纹</dt><dd><code>{{ store.current.content_fingerprint }}</code></dd></div>
        </dl>
        <div
          class="revision-strip"
          aria-label="草稿版本历史"
        >
          <span
            v-for="version in store.versions"
            :key="version.version"
            class="revision-chip"
            :class="{ current: version.version === store.current.version }"
          >v{{ version.version }} · {{ version.revision_type === 'generated' ? '生成' : '编辑' }}</span>
        </div>
      </section>
    </template>
  </AppShell>
</template>
