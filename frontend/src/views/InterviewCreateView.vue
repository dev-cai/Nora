<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowLeft, CalendarPlus } from "lucide-vue-next"
import { useRoute, useRouter } from "vue-router"

import { userMessage } from "@/api/client"
import type { InterviewMode } from "@/api/types"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useApplicationsStore } from "@/stores/applications"
import { useInterviewsStore } from "@/stores/interviews"

const route = useRoute()
const router = useRouter()
const applications = useApplicationsStore()
const interviews = useInterviewsStore()
const applicationId = computed(() => String(route.query.application || ""))
const startsAt = ref(toLocalInput(new Date(Date.now() + 24 * 60 * 60 * 1000)))
const timezone = ref(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC")
const mode = ref<InterviewMode>("online")
const modeOptions: InterviewMode[] = ["online", "onsite", "phone"]
const location = ref("")
const meetingUrl = ref("")
const roundNumber = ref(1)
const note = ref("")
const error = ref("")

function toLocalInput(value: Date): string {
  const shifted = new Date(value.getTime() - value.getTimezoneOffset() * 60_000)
  return shifted.toISOString().slice(0, 16)
}

async function load(): Promise<void> {
  error.value = ""
  if (!applicationId.value) {
    error.value = "缺少投递记录"
    return
  }
  try {
    const record = await applications.fetchRecord(applicationId.value)
    if (record.status !== "interviewing") error.value = "投递记录尚未确认进入面试中"
  } catch (reason) { error.value = userMessage(reason) }
}

async function create(): Promise<void> {
  if (!applications.current || applications.current.status !== "interviewing") return
  error.value = ""
  try {
    const value = await interviews.create(applications.current.id, {
      starts_at: new Date(startsAt.value).toISOString(),
      timezone: timezone.value.trim(),
      mode: mode.value,
      location: mode.value === "onsite" ? location.value.trim() || null : null,
      meeting_url: mode.value === "online" ? meetingUrl.value.trim() || null : null,
      round_number: roundNumber.value,
      note: note.value.trim() || null,
      status: "scheduled",
    })
    await router.push(`/interviews/${value.id}`)
  } catch (reason) { error.value = userMessage(reason) }
}

watch(applicationId, () => void load(), { immediate: true })
</script>

<template>
  <AppShell>
    <RouterLink
      class="back-link"
      :to="applicationId ? `/applications/${applicationId}` : '/applications'"
    >
      <ArrowLeft :size="16" /> 返回投递详情
    </RouterLink>
    <StatePanel
      v-if="applications.loading && !applications.current"
      mode="loading"
      title="正在读取投递记录"
    />
    <StatePanel
      v-else-if="error && !applications.current"
      mode="error"
      title="无法记录面试"
      :message="error"
      @retry="load"
    />
    <template v-else-if="applications.current">
      <header class="resume-detail-header">
        <div>
          <p class="eyebrow">
            用户确认通知
          </p>
          <h2>记录面试安排</h2>
          <p>投递记录 {{ applications.current.id }}</p>
        </div>
        <span class="version-badge">新安排 v1</span>
      </header>
      <form
        class="interview-form"
        @submit.prevent="create"
      >
        <div class="form-grid two-columns">
          <label>
            <span>开始时间</span>
            <input
              v-model="startsAt"
              type="datetime-local"
              required
            >
          </label>
          <label>
            <span>时区</span>
            <input
              v-model="timezone"
              maxlength="100"
              required
            >
          </label>
          <label>
            <span>轮次</span>
            <input
              v-model.number="roundNumber"
              type="number"
              min="1"
              max="20"
              required
            >
          </label>
          <fieldset class="interview-mode-field">
            <legend>方式</legend>
            <div class="application-status-control">
              <button
                v-for="option in modeOptions"
                :key="option"
                type="button"
                :class="{ active: mode === option }"
                @click="mode = option"
              >
                {{ option === 'online' ? '线上' : option === 'onsite' ? '线下' : '电话' }}
              </button>
            </div>
          </fieldset>
          <label
            v-if="mode === 'online'"
            class="interview-wide-field"
          >
            <span>会议链接</span>
            <input
              v-model="meetingUrl"
              type="url"
              inputmode="url"
              maxlength="2000"
              placeholder="https://"
              required
            >
          </label>
          <label
            v-if="mode === 'onsite'"
            class="interview-wide-field"
          >
            <span>地点</span>
            <input
              v-model="location"
              maxlength="500"
              required
            >
          </label>
          <label class="interview-wide-field">
            <span>备注（可选）</span>
            <textarea
              v-model="note"
              rows="4"
              maxlength="2000"
            />
          </label>
        </div>
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
            type="submit"
            :disabled="interviews.saving || applications.current.status !== 'interviewing'"
          >
            <CalendarPlus :size="17" />
            {{ interviews.saving ? '正在保存…' : '保存面试安排' }}
          </button>
        </div>
      </form>
    </template>
  </AppShell>
</template>
