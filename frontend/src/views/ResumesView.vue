<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ArrowRight, FilePlus2, FileText } from "lucide-vue-next"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useResumesStore } from "@/stores/resumes"

const store = useResumesStore()
const error = ref("")
async function load(): Promise<void> {
  error.value = ""
  try { await store.fetchResumes() } catch (reason) { error.value = userMessage(reason) }
}
onMounted(load)
</script>

<template>
  <AppShell>
    <section class="section-toolbar page-toolbar">
      <div>
        <p class="eyebrow">
          不可变发布记录
        </p><h2>简历版本</h2><p>每次发布都固定引用一个主档版本，历史内容不会被后续编辑覆盖。</p>
      </div>
      <RouterLink
        class="button button-primary"
        to="/resumes/new"
      >
        <FilePlus2 :size="17" />发布新版本
      </RouterLink>
    </section>
    <StatePanel
      v-if="error"
      mode="error"
      title="无法加载简历"
      :message="error"
      @retry="load"
    />
    <StatePanel
      v-else-if="store.isLoading"
      mode="loading"
      title="正在加载简历"
    />
    <StatePanel
      v-else-if="store.resumes.length === 0"
      mode="empty"
      title="还没有简历版本"
      message="先确认主档事实，再发布第一份不可变简历。"
    />
    <section
      v-else
      class="resume-list"
      aria-label="简历版本列表"
    >
      <RouterLink
        v-for="resume in store.resumes"
        :key="resume.id"
        class="resume-row"
        :to="`/resumes/${resume.id}`"
      >
        <span class="metric-icon blue"><FileText :size="18" /></span>
        <span class="resume-row-main"><strong>{{ resume.title }}</strong><small>简历 v{{ resume.version }} · 主档 v{{ resume.profile_version }}</small></span>
        <time>{{ new Date(resume.published_at).toLocaleString('zh-CN') }}</time>
        <ArrowRight :size="17" />
      </RouterLink>
    </section>
  </AppShell>
</template>
