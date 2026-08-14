<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ArrowRight, FileStack, LayoutTemplate, ShieldCheck } from "lucide-vue-next"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useVariantsStore } from "@/stores/variants"

const store = useVariantsStore()
const error = ref("")

async function load(): Promise<void> {
  error.value = ""
  try { await Promise.all([store.fetchTemplates(), store.fetchVariants()]) }
  catch (reason) { error.value = userMessage(reason) }
}

onMounted(load)
</script>

<template>
  <AppShell>
    <section class="section-toolbar page-toolbar">
      <div>
        <p class="eyebrow">
          声明式模板
        </p>
        <h2>定制简历</h2>
        <p>模板只定义受控字段和版式；已创建的变体始终固定来源与模板版本。</p>
      </div>
      <span class="analysis-mode-badge"><ShieldCheck :size="16" /> 不执行模板代码</span>
    </section>
    <StatePanel
      v-if="error"
      mode="error"
      title="无法加载定制简历"
      :message="error"
      @retry="load"
    />
    <StatePanel
      v-else-if="store.isLoading"
      mode="loading"
      title="正在加载定制简历"
    />
    <template v-else>
      <section aria-labelledby="template-heading">
        <div class="section-heading-row">
          <div>
            <p class="eyebrow">
              可用版式
            </p><h3 id="template-heading">
              模板版本
            </h3>
          </div>
          <span>{{ store.templates.length }} 个</span>
        </div>
        <div class="template-grid">
          <article
            v-for="template in store.templates"
            :key="`${template.id}-${template.version}`"
            class="template-card"
          >
            <span class="metric-icon blue"><LayoutTemplate :size="18" /></span>
            <div><strong>{{ template.name }}</strong><small>v{{ template.version }} · {{ template.page_size.toUpperCase() }} · {{ template.density === 'compact' ? '紧凑' : '标准' }}</small></div>
            <span class="version-badge">{{ template.accent === 'blue' ? '蓝色强调' : '中性色' }}</span>
          </article>
        </div>
      </section>
      <section
        class="content-section"
        aria-labelledby="variant-heading"
      >
        <div class="section-heading-row">
          <div>
            <p class="eyebrow">
              不可变记录
            </p><h3 id="variant-heading">
              已创建变体
            </h3>
          </div>
          <span>{{ store.total }} 份</span>
        </div>
        <StatePanel
          v-if="store.variants.length === 0"
          mode="empty"
          title="还没有定制简历"
          message="在报告中确认投递后，即可创建第一份岗位定制简历。"
        />
        <div
          v-else
          class="variant-list"
        >
          <RouterLink
            v-for="variant in store.variants"
            :key="variant.id"
            class="variant-row"
            :to="{ name: 'resume-variant-detail', params: { id: variant.id } }"
          >
            <span class="metric-icon green"><FileStack :size="18" /></span>
            <span><strong>{{ variant.title }}</strong><small>变体 v{{ variant.version }} · 简历 v{{ variant.resume_version }} · 模板 v{{ variant.template_version }}</small></span>
            <time>{{ new Date(variant.created_at).toLocaleString('zh-CN') }}</time>
            <ArrowRight :size="17" />
          </RouterLink>
        </div>
      </section>
    </template>
  </AppShell>
</template>
