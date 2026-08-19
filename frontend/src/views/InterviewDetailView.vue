<script setup lang="ts">
import { computed, ref, watch } from "vue"
import {
  ArrowLeft,
  CalendarClock,
  ExternalLink,
  History,
  RefreshCw,
  Save,
} from "lucide-vue-next"
import { useRoute } from "vue-router"

import { userMessage } from "@/api/client"
import type { InterviewCase, InterviewCaseStatus, InterviewMode } from "@/api/types"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useInterviewsStore } from "@/stores/interviews"

const route = useRoute()
const store = useInterviewsStore()
const interviewId = computed(() => String(route.params.id))
const startsAt = ref("")
const timezone = ref("")
const mode = ref<InterviewMode>("online")
const modeOptions: InterviewMode[] = ["online", "onsite", "phone"]
const location = ref("")
const meetingUrl = ref("")
const roundNumber = ref(1)
const note = ref("")
const status = ref<InterviewCaseStatus>("scheduled")
const error = ref("")
const saved = ref(false)
const editable = computed(
  () => Boolean(store.current && new Date(store.current.starts_at).getTime() > Date.now()),
)
const modeLabels: Record<InterviewMode, string> = {
  onsite: "线下",
  online: "线上",
  phone: "电话",
}

function toLocalInput(value: string): string {
  const date = new Date(value)
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return shifted.toISOString().slice(0, 16)
}

function fill(value: InterviewCase): void {
  startsAt.value = toLocalInput(value.starts_at)
  timezone.value = value.timezone
  mode.value = value.mode
  location.value = value.location || ""
  meetingUrl.value = value.meeting_url || ""
  roundNumber.value = value.round_number
  note.value = value.note || ""
  status.value = value.status
}

async function load(): Promise<void> {
  error.value = ""
  saved.value = false
  try {
  const value = await store.fetchInterview(interviewId.value)
    fill(value)
    await store.fetchVersions(value.id)
    await store.fetchPreparation(value.id)
  } catch (reason) { error.value = userMessage(reason) }
}

async function save(): Promise<void> {
  if (!store.current || !editable.value) return
  error.value = ""
  saved.value = false
  try {
    const value = await store.update({
      base_version: store.current.version,
      starts_at: new Date(startsAt.value).toISOString(),
      timezone: timezone.value.trim(),
      mode: mode.value,
      location: mode.value === "onsite" ? location.value.trim() || null : null,
      meeting_url: mode.value === "online" ? meetingUrl.value.trim() || null : null,
      round_number: roundNumber.value,
      note: note.value.trim() || null,
      status: status.value,
    })
    fill(value)
    saved.value = true
  } catch (reason) { error.value = userMessage(reason) }
}

watch(interviewId, () => void load(), { immediate: true })
</script>

<template>
  <AppShell>
    <RouterLink
      class="back-link"
      to="/interviews"
    >
      <ArrowLeft :size="16" /> 返回面试安排
    </RouterLink>
    <StatePanel
      v-if="store.loading && !store.current"
      mode="loading"
      title="正在读取面试安排"
    />
    <StatePanel
      v-else-if="error && !store.current"
      mode="error"
      title="无法读取面试安排"
      :message="error"
      @retry="load"
    />
    <template v-else-if="store.current">
      <header class="resume-detail-header">
        <div>
          <p class="eyebrow">
            第 {{ store.current.round_number }} 轮 · {{ modeLabels[store.current.mode] }}
          </p>
          <h2>{{ new Date(store.current.starts_at).toLocaleString('zh-CN') }}</h2>
          <p>{{ store.current.timezone }} · {{ store.current.status === 'scheduled' ? '已安排' : '已取消' }}</p>
        </div>
        <div class="detail-actions">
          <span class="immutable-badge">
            <CalendarClock :size="18" />
            <span><strong>安排 v{{ store.current.version }}</strong><small>只追加历史</small></span>
          </span>
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
        <div>
          <dt>投递记录</dt><dd>
            <RouterLink
              class="inline-link"
              :to="`/applications/${store.current.application_record_id}`"
            >
              {{ store.current.application_record_id }}
            </RouterLink>
          </dd>
        </div>
        <div><dt>来源</dt><dd>用户确认</dd></div>
        <div><dt>地点</dt><dd>{{ store.current.location || '—' }}</dd></div>
        <div>
          <dt>会议链接</dt>
          <dd>
            <a
              v-if="store.current.meeting_url"
              class="inline-link"
              :href="store.current.meeting_url"
              target="_blank"
              rel="noreferrer"
            >
              打开链接 <ExternalLink :size="13" />
            </a>
            <span v-else>—</span>
          </dd>
        </div>
        <div><dt>备注</dt><dd>{{ store.current.note || '—' }}</dd></div>
        <div><dt>更新于</dt><dd>{{ new Date(store.current.updated_at).toLocaleString('zh-CN') }}</dd></div>
      </dl>

      <section class="interview-editor-band">
        <div class="message-band-heading">
          <Save :size="19" />
          <h3>{{ editable ? '更新安排' : '历史安排' }}</h3>
        </div>
        <form
          class="interview-form interview-detail-form"
          @submit.prevent="save"
        >
          <div class="form-grid two-columns">
            <label>
              <span>开始时间</span>
              <input
                v-model="startsAt"
                type="datetime-local"
                required
                :disabled="!editable"
              >
            </label>
            <label>
              <span>时区</span>
              <input
                v-model="timezone"
                maxlength="100"
                required
                :disabled="!editable"
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
                :disabled="!editable"
              >
            </label>
            <fieldset
              class="interview-mode-field"
              :disabled="!editable"
            >
              <legend>方式</legend>
              <div class="application-status-control">
                <button
                  v-for="option in modeOptions"
                  :key="option"
                  type="button"
                  :class="{ active: mode === option }"
                  @click="mode = option"
                >
                  {{ modeLabels[option] }}
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
                maxlength="2000"
                required
                :disabled="!editable"
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
                :disabled="!editable"
              >
            </label>
            <label class="interview-wide-field">
              <span>备注（可选）</span>
              <textarea
                v-model="note"
                rows="4"
                maxlength="2000"
                :disabled="!editable"
              />
            </label>
          </div>
          <div
            v-if="editable"
            class="application-status-control interview-status-control"
            role="group"
            aria-label="安排状态"
          >
            <button
              type="button"
              :class="{ active: status === 'scheduled' }"
              @click="status = 'scheduled'"
            >
              已安排
            </button>
            <button
              type="button"
              :class="{ active: status === 'cancelled' }"
              @click="status = 'cancelled'"
            >
              已取消
            </button>
          </div>
          <p
            v-if="error"
            class="form-error"
            role="alert"
          >
            {{ error }}
          </p>
          <p
            v-if="saved"
            class="form-success"
          >
            已保存为 v{{ store.current.version }}
          </p>
          <div
            v-if="editable"
            class="form-actions"
          >
            <button
              class="button button-primary"
              type="submit"
              :disabled="store.saving"
            >
              <Save :size="17" /> {{ store.saving ? '正在保存…' : '保存新版本' }}
            </button>
          </div>
        </form>
      </section>

      <section class="interview-editor-band preparation-band">
        <div class="message-band-heading">
          <History :size="19" />
          <h3>面试准备</h3>
          <button
            class="icon-button"
            type="button"
            title="刷新生成准备计划"
            aria-label="刷新生成准备计划"
            :disabled="store.saving"
            @click="store.generatePreparation(interviewId)"
          >
            <RefreshCw :size="17" />
          </button>
        </div>
        <p
          v-if="!store.preparation"
          class="empty-copy"
        >
          还没有准备计划，点击刷新生成。
        </p>
        <template v-else>
          <p class="eyebrow">
            准备计划 v{{ store.preparation.version }} · {{ new Date(store.preparation.created_at).toLocaleString('zh-CN') }}
          </p>
          <div class="preparation-topics">
            <article
              v-for="topic in store.preparation.topics"
              :key="topic.topic_id"
              class="preparation-topic"
            >
              <div class="topic-heading">
                <strong>{{ topic.title }}</strong><span>{{ topic.priority }} · {{ topic.estimated_effort_minutes }} 分钟</span>
              </div>
              <p>{{ topic.reason }}</p>
              <small>{{ topic.suggestion }}</small>
              <div
                v-if="topic.citation_ids.length"
                class="topic-citations"
              >
                <details
                  v-for="citationId in topic.citation_ids"
                  :key="citationId"
                  class="preparation-citation"
                >
                  <summary>打开证据</summary>
                  <template v-if="store.preparation.citations.find((item) => item.citation_id === citationId)">
                    <p>{{ store.preparation.citations.find((item) => item.citation_id === citationId)!.excerpt }}</p>
                    <small>{{ store.preparation.citations.find((item) => item.citation_id === citationId)!.locator }}</small>
                  </template>
                </details>
              </div>
            </article>
          </div>
          <details
            v-if="store.preparationVersions.length > 1"
            class="preparation-history"
          >
            <summary>历史版本（{{ store.preparationVersions.length }}）</summary>
            <p
              v-for="item in store.preparationVersions"
              :key="item.id"
            >
              v{{ item.version }} · {{ new Date(item.created_at).toLocaleString('zh-CN') }}
            </p>
          </details>
        </template>
      </section>

      <section class="interview-history-band">
        <div class="message-band-heading">
          <History :size="19" />
          <h3>版本历史</h3>
        </div>
        <ol class="application-timeline">
          <li
            v-for="item in store.versions"
            :key="item.version"
          >
            <span class="timeline-marker" />
            <div>
              <strong>v{{ item.version }} · 第 {{ item.round_number }} 轮 · {{ modeLabels[item.mode] }}</strong>
              <p>{{ new Date(item.starts_at).toLocaleString('zh-CN') }} · {{ item.timezone }}</p>
              <small>{{ item.status === 'scheduled' ? '已安排' : '已取消' }} · {{ new Date(item.updated_at).toLocaleString('zh-CN') }}</small>
            </div>
          </li>
        </ol>
      </section>
    </template>
  </AppShell>
</template>
