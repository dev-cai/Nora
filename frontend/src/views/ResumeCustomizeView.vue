<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowDown, ArrowLeft, ArrowUp, FilePenLine, GripVertical, ShieldCheck } from "lucide-vue-next"
import { useRoute, useRouter } from "vue-router"

import { userMessage } from "@/api/client"
import type { TemplateDefinition, VariantBlock } from "@/api/types"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { resumeBlocks, templateAllows, templateRequires } from "@/features/resume-variant"
import { useResumesStore } from "@/stores/resumes"
import { useVariantsStore } from "@/stores/variants"

type EditableBlock = VariantBlock & { selected: boolean; required: boolean }

const route = useRoute()
const router = useRouter()
const resumes = useResumesStore()
const variants = useVariantsStore()
const error = ref("")
const title = ref("")
const selectedTemplateKey = ref("")
const blocks = ref<EditableBlock[]>([])
const resumeId = computed(() => String(route.params.id))
const decisionId = computed(() => typeof route.query.decision === "string" ? route.query.decision : "")
const selectedTemplate = computed(() => variants.templates.find((item) => templateKey(item) === selectedTemplateKey.value) || null)
const selectedCount = computed(() => blocks.value.filter((block) => block.selected).length)

function templateKey(template: TemplateDefinition): string { return `${template.id}:${template.version}` }

function applyTemplate(template: TemplateDefinition): void {
  if (!resumes.current) return
  const sectionIndex = new Map(template.section_order.map((section, index) => [section, index]))
  blocks.value = resumeBlocks(resumes.current)
    .filter((block) => templateAllows(template, block.source_path))
    .map((block) => ({ ...block, selected: true, required: templateRequires(template, block.source_path) }))
    .sort((left, right) => (sectionIndex.get(left.source_path.split(".")[0] || "") ?? 99) - (sectionIndex.get(right.source_path.split(".")[0] || "") ?? 99))
}

async function load(): Promise<void> {
  error.value = ""
  if (!decisionId.value) { error.value = "缺少已确认的投递决定，请从报告详情重新进入"; return }
  try {
    await Promise.all([resumes.fetchResume(resumeId.value), variants.fetchTemplates()])
    if (!resumes.current || variants.templates.length === 0) { error.value = "当前没有可用的简历或模板"; return }
    title.value = `${resumes.current.title} · 定制版`
    selectedTemplateKey.value = templateKey(variants.templates[0]!)
    applyTemplate(variants.templates[0]!)
  } catch (reason) { error.value = userMessage(reason) }
}

function selectTemplate(template: TemplateDefinition): void {
  selectedTemplateKey.value = templateKey(template)
  applyTemplate(template)
}

function move(index: number, offset: number): void {
  const target = index + offset
  if (target < 0 || target >= blocks.value.length) return
  const copy = [...blocks.value]
  const [block] = copy.splice(index, 1)
  if (!block) return
  copy.splice(target, 0, block)
  blocks.value = copy
}

async function create(): Promise<void> {
  error.value = ""
  const template = selectedTemplate.value
  const chosen = blocks.value.filter((block) => block.selected).map(({ source_path, label, value }) => ({ source_path, label: label.trim(), value: value.trim() }))
  if (!template || !decisionId.value) { error.value = "请选择可用模板"; return }
  if (!title.value.trim()) { error.value = "请填写定制简历标题"; return }
  if (chosen.length === 0 || chosen.some((block) => !block.label || !block.value)) { error.value = "请至少保留一个内容完整的字段"; return }
  try {
    const created = await variants.createVariant({
      application_decision_id: decisionId.value,
      template_id: template.id,
      template_version: template.version,
      title: title.value.trim(),
      blocks: chosen,
    })
    await router.push({ name: "resume-variant-detail", params: { id: created.id } })
  } catch (reason) { error.value = userMessage(reason) }
}

watch([resumeId, decisionId], () => void load(), { immediate: true })
</script>

<template>
  <AppShell>
    <button
      class="back-link link-button"
      type="button"
      @click="router.back()"
    >
      <ArrowLeft :size="16" /> 返回报告
    </button>
    <StatePanel
      v-if="resumes.isLoading || variants.loading"
      mode="loading"
      title="正在准备定制内容"
    />
    <StatePanel
      v-else-if="error && (!resumes.current || !decisionId)"
      mode="error"
      title="无法开始定制"
      :message="error"
      @retry="load"
    />
    <form
      v-else-if="resumes.current"
      class="customize-layout"
      @submit.prevent="create"
    >
      <aside class="customize-settings">
        <p class="eyebrow">
          固定来源
        </p>
        <h2>{{ resumes.current.title }}</h2>
        <p>简历 v{{ resumes.current.version }} · 主档 v{{ resumes.current.profile_version }}</p>
        <label>定制简历标题<input
          v-model="title"
          maxlength="200"
        ></label>
        <fieldset class="template-options">
          <legend>选择模板版本</legend>
          <label
            v-for="template in variants.templates"
            :key="templateKey(template)"
            :class="{ active: selectedTemplateKey === templateKey(template) }"
          >
            <input
              type="radio"
              name="template"
              :value="templateKey(template)"
              :checked="selectedTemplateKey === templateKey(template)"
              @change="selectTemplate(template)"
            >
            <span><strong>{{ template.name }}</strong><small>v{{ template.version }} · {{ template.density === 'compact' ? '紧凑' : '标准' }}</small></span>
          </label>
        </fieldset>
        <div class="template-safety">
          <ShieldCheck :size="17" /><span>仅使用声明式字段与样式枚举，不执行脚本或外部资源。</span>
        </div>
      </aside>
      <section class="block-editor">
        <header>
          <div>
            <p class="eyebrow">
              内容编排
            </p><h3>选择、编辑与排序</h3>
          </div>
          <span>{{ selectedCount }} / {{ blocks.length }} 个字段</span>
        </header>
        <StatePanel
          v-if="blocks.length === 0"
          mode="empty"
          title="模板没有可用字段"
          message="请选择其他模板或检查来源简历内容。"
        />
        <div
          v-else
          class="block-list"
        >
          <article
            v-for="(block, index) in blocks"
            :key="block.source_path"
            class="block-row"
            :class="{ muted: !block.selected }"
          >
            <GripVertical
              class="drag-mark"
              :size="18"
            />
            <label class="block-check"><input
              v-model="block.selected"
              type="checkbox"
              :disabled="block.required"
            ><span class="sr-only">保留 {{ block.label }}</span></label>
            <div class="block-fields">
              <div>
                <input
                  v-model="block.label"
                  aria-label="字段标签"
                  maxlength="100"
                ><code>{{ block.source_path }}</code>
              </div>
              <textarea
                v-model="block.value"
                aria-label="字段内容"
                maxlength="4000"
                :disabled="!block.selected"
              />
            </div>
            <div class="reorder-actions">
              <button
                class="icon-button"
                type="button"
                :disabled="index === 0"
                title="上移"
                aria-label="上移"
                @click="move(index, -1)"
              >
                <ArrowUp :size="16" />
              </button>
              <button
                class="icon-button"
                type="button"
                :disabled="index === blocks.length - 1"
                title="下移"
                aria-label="下移"
                @click="move(index, 1)"
              >
                <ArrowDown :size="16" />
              </button>
            </div>
          </article>
        </div>
        <p
          v-if="error"
          class="form-error"
          role="alert"
        >
          {{ error }}
        </p>
        <footer class="variant-submit">
          <span>创建后将固定当前顺序、编辑内容和全部来源版本。</span>
          <button
            class="button button-primary"
            type="submit"
            :disabled="variants.saving || selectedCount === 0"
          >
            <FilePenLine :size="17" /> {{ variants.saving ? '正在创建…' : '创建不可变变体' }}
          </button>
        </footer>
      </section>
    </form>
  </AppShell>
</template>
