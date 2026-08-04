<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { ArrowLeft, Send } from "lucide-vue-next"
import { useRouter } from "vue-router"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import SnapshotContent from "@/components/SnapshotContent.vue"
import StatePanel from "@/components/StatePanel.vue"
import { confirmedSnapshot, hasSnapshotFacts } from "@/features/profile-snapshot"
import { useProfileStore } from "@/stores/profile"
import { useResumesStore } from "@/stores/resumes"

const router = useRouter()
const profiles = useProfileStore()
const resumes = useResumesStore()
const title = ref("")
const error = ref("")
const publishing = ref(false)

const preview = computed(() => confirmedSnapshot(profiles.current?.content || {}))
const hasConfirmedFacts = computed(() => hasSnapshotFacts(preview.value))

async function load(): Promise<void> {
  error.value = ""
  try { await profiles.fetchProfile() } catch (reason) { error.value = userMessage(reason) }
}
async function publish(): Promise<void> {
  error.value = ""
  if (!title.value.trim()) { error.value = "请填写简历标题"; return }
  if (!profiles.current || !hasConfirmedFacts.value) { error.value = "请先在主档中确认至少一个可发布事实"; return }
  publishing.value = true
  try {
    const resume = await resumes.publishResume(title.value.trim(), profiles.current.version)
    await router.push({ name: "resume-detail", params: { id: resume.id } })
  } catch (reason) { error.value = userMessage(reason) }
  finally { publishing.value = false }
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
    <section class="section-toolbar page-toolbar">
      <div>
        <p class="eyebrow">
          确认后发布
        </p><h2>发布新简历</h2><p>预览仅包含主档中标记为“已确认”的事实。</p>
      </div>
      <span
        v-if="profiles.current"
        class="version-badge"
      >来源：主档 v{{ profiles.current.version }}</span>
    </section>
    <StatePanel
      v-if="profiles.isLoading"
      mode="loading"
      title="正在加载主档"
    />
    <StatePanel
      v-else-if="error && !profiles.current"
      mode="error"
      title="无法加载主档"
      :message="error"
      @retry="load"
    />
    <StatePanel
      v-else-if="!profiles.current"
      mode="empty"
      title="请先建立主档"
      message="发布简历需要一个包含已确认事实的主档版本。"
    />
    <form
      v-else
      class="publish-layout"
      @submit.prevent="publish"
    >
      <aside class="publish-settings">
        <h3>发布设置</h3>
        <label>简历标题<input
          v-model="title"
          maxlength="200"
          placeholder="例如 后端工程师简历"
        ></label>
        <p>发布后内容不可修改；继续编辑主档不会影响此版本。</p>
        <p
          v-if="error"
          class="form-error"
          role="alert"
        >
          {{ error }}
        </p>
        <button
          class="button button-primary button-wide"
          type="submit"
          :disabled="publishing || !hasConfirmedFacts"
        >
          <Send :size="17" />{{ publishing ? "正在发布…" : "发布不可变版本" }}
        </button>
      </aside>
      <section class="resume-preview">
        <div class="preview-heading">
          <span>发布预览</span><small>confirmed-only</small>
        </div><SnapshotContent
          v-if="hasConfirmedFacts"
          :content="preview"
        /><StatePanel
          v-else
          mode="empty"
          title="没有可发布事实"
          message="返回主档，将需要发布的字段标记为已确认。"
        />
      </section>
    </form>
  </AppShell>
</template>
