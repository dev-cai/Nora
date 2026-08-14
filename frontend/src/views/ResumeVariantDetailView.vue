<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowLeft, FileStack, RefreshCw, ShieldCheck } from "lucide-vue-next"
import { useRoute } from "vue-router"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useVariantsStore } from "@/stores/variants"

const route = useRoute()
const store = useVariantsStore()
const error = ref("")
const variantId = computed(() => String(route.params.id))

async function load(): Promise<void> {
  error.value = ""
  try {
    const variant = await store.fetchVariant(variantId.value)
    await store.fetchTemplate(variant.template_id, variant.template_version)
  } catch (reason) { error.value = userMessage(reason) }
}

watch(variantId, () => void load(), { immediate: true })
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
      <section class="locked-band">
        <ShieldCheck :size="18" /><div><strong>版本已固定</strong><p>刷新只读取同一变体；来源简历或模板升级不会改写这份内容。</p></div>
      </section>
    </template>
  </AppShell>
</template>
