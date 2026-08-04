<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ArrowLeft, ShieldCheck } from "lucide-vue-next"
import { useRoute } from "vue-router"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import SnapshotContent from "@/components/SnapshotContent.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useResumesStore } from "@/stores/resumes"

const route = useRoute()
const store = useResumesStore()
const error = ref("")
async function load(): Promise<void> {
  error.value = ""
  try { await store.fetchResume(String(route.params.id)) } catch (reason) { error.value = userMessage(reason) }
}
onMounted(load)
</script>

<template>
  <AppShell>
    <RouterLink
      class="back-link"
      to="/resumes"
    >
      <ArrowLeft :size="16" />返回简历版本
    </RouterLink>
    <StatePanel
      v-if="error"
      mode="error"
      title="无法读取简历"
      :message="error"
      @retry="load"
    />
    <StatePanel
      v-else-if="store.isLoading || !store.current"
      mode="loading"
      title="正在读取简历"
    />
    <template v-else>
      <header class="resume-detail-header">
        <div>
          <p class="eyebrow">
            不可变快照
          </p><h2>{{ store.current.title }}</h2><p>发布于 {{ new Date(store.current.published_at).toLocaleString('zh-CN') }}</p>
        </div>
        <div class="immutable-badge">
          <ShieldCheck :size="18" /><span><strong>简历 v{{ store.current.version }}</strong><small>来源主档 v{{ store.current.profile_version }}</small></span>
        </div>
      </header>
      <section class="resume-document">
        <SnapshotContent :content="store.current.content" />
      </section>
    </template>
  </AppShell>
</template>
