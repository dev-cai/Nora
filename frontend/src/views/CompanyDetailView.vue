<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowLeft, History, Plus, RefreshCw } from "lucide-vue-next"
import { useRoute, useRouter } from "vue-router"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import CompanySnapshotCard from "@/components/CompanySnapshotCard.vue"
import CompanySnapshotForm from "@/components/CompanySnapshotForm.vue"
import StatePanel from "@/components/StatePanel.vue"
import type { CompanySnapshotSubmission } from "@/stores/companies"
import { useCompaniesStore } from "@/stores/companies"

const route = useRoute()
const router = useRouter()
const store = useCompaniesStore()
const loadError = ref("")
const saveError = ref("")
const saved = ref("")
const editing = ref(false)
const snapshotId = computed(() => String(route.params.id))
const selectedVersion = computed(() => {
  const value = Number(route.query.version)
  return Number.isInteger(value) && value > 0 ? value : undefined
})

async function load(): Promise<void> {
  loadError.value = ""
  try {
    await store.fetch(snapshotId.value, selectedVersion.value)
  } catch (reason) {
    loadError.value = userMessage(reason)
  }
}

async function append(input: CompanySnapshotSubmission): Promise<void> {
  if (!store.latest) return
  saveError.value = ""
  saved.value = ""
  try {
    const created = await store.append(snapshotId.value, store.latest.version, input)
    saved.value = `已创建公司情报 v${created.version}`
    editing.value = false
    await router.replace({ name: "company-detail", params: { id: created.id } })
  } catch (reason) {
    saveError.value = userMessage(reason)
  }
}

watch([snapshotId, selectedVersion], () => void load(), { immediate: true })
</script>

<template>
  <AppShell>
    <RouterLink
      class="back-link"
      to="/reports"
    >
      <ArrowLeft :size="16" /> 返回分析报告
    </RouterLink>
    <StatePanel
      v-if="store.loading && !store.current"
      mode="loading"
      title="正在读取公司情报"
    />
    <StatePanel
      v-else-if="loadError"
      mode="error"
      title="无法读取公司情报"
      :message="loadError"
      @retry="load"
    />
    <template v-else-if="store.current && store.latest">
      <header class="report-detail-header">
        <div>
          <p class="eyebrow">
            版本化公司情报
          </p><h2>{{ store.current.company_name }}</h2><p>当前查看 v{{ store.current.version }} · 最新 v{{ store.latest.version }}</p>
        </div>
        <div class="detail-actions">
          <button
            class="button button-secondary button-small"
            type="button"
            aria-label="刷新"
            @click="load"
          >
            <RefreshCw :size="16" /> 刷新
          </button>
          <button
            class="button button-primary button-small"
            type="button"
            @click="editing = !editing"
          >
            <Plus :size="16" /> 新增版本
          </button>
        </div>
      </header>

      <CompanySnapshotCard :snapshot="store.current" />
      <p
        v-if="saved"
        class="form-success company-save-notice"
      >
        {{ saved }}
      </p>

      <section class="company-version-band">
        <div class="report-section-heading">
          <History :size="19" /><div><h3>版本历史</h3><p>选择精确版本，不会自动追随最新内容。</p></div>
        </div>
        <div class="revision-strip">
          <RouterLink
            v-for="version in store.versions"
            :key="version.version"
            class="revision-chip"
            :class="{ current: store.current.version === version.version }"
            :to="{ name: 'company-detail', params: { id: snapshotId }, query: version.version === store.latest.version ? {} : { version: version.version } }"
          >
            v{{ version.version }} · {{ new Date(version.created_at).toLocaleDateString('zh-CN') }}
          </RouterLink>
        </div>
      </section>

      <section
        v-if="editing"
        class="company-editor-band"
      >
        <div class="report-section-heading">
          <Plus :size="19" /><div><h3>追加 v{{ store.latest.version + 1 }}</h3><p>以最新版本为并发基线，并固定一份新的来源记录。</p></div>
        </div>
        <CompanySnapshotForm
          :initial="store.latest"
          company-name-readonly
          :saving="store.saving"
          submit-label="创建新版本"
          @submit="append"
        />
        <p
          v-if="saveError"
          class="form-error company-page-error"
        >
          {{ saveError }}
        </p>
      </section>
    </template>
  </AppShell>
</template>
