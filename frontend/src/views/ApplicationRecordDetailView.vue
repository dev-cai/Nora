<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ArrowLeft, Clock3, RefreshCw, Send, ShieldCheck } from "lucide-vue-next"
import { useRoute } from "vue-router"

import { userMessage } from "@/api/client"
import type { ApplicationRecordStatus } from "@/api/types"
import AppShell from "@/components/AppShell.vue"
import StatePanel from "@/components/StatePanel.vue"
import { useApplicationsStore } from "@/stores/applications"

const statusLabels: Record<ApplicationRecordStatus, string> = {
  planned: "待确认",
  applied: "已投递",
  interviewing: "面试中",
  offer_received: "已获 Offer",
  rejected: "未通过",
  withdrawn: "已撤回",
}
const nextStatuses: Record<ApplicationRecordStatus, ApplicationRecordStatus[]> = {
  planned: ["applied", "withdrawn"],
  applied: ["interviewing", "rejected", "withdrawn"],
  interviewing: ["offer_received", "rejected", "withdrawn"],
  offer_received: [],
  rejected: [],
  withdrawn: [],
}
const channelOptions = ["公司官网", "招聘平台", "邮件", "内推", "其他"]

const route = useRoute()
const store = useApplicationsStore()
const recordId = computed(() => String(route.params.id))
const target = ref<ApplicationRecordStatus | null>(null)
const occurredAt = ref(toLocalInput(new Date()))
const channel = ref("")
const note = ref("")
const error = ref("")
const availableTargets = computed(() => store.current ? nextStatuses[store.current.status] : [])

function toLocalInput(value: Date): string {
  const shifted = new Date(value.getTime() - value.getTimezoneOffset() * 60_000)
  return shifted.toISOString().slice(0, 16)
}

async function load(): Promise<void> {
  error.value = ""
  target.value = null
  try {
    const record = await store.fetchRecord(recordId.value)
    await store.fetchTransitions(record.id)
  } catch (reason) { error.value = userMessage(reason) }
}

async function confirmTransition(): Promise<void> {
  if (!store.current || !target.value) return
  if (target.value === "applied" && !channel.value) {
    error.value = "确认已投递时必须选择渠道"
    return
  }
  error.value = ""
  try {
    await store.transition({
      base_version: store.current.version,
      to_status: target.value,
      occurred_at: new Date(occurredAt.value).toISOString(),
      channel: channel.value || null,
      note: note.value.trim() || null,
    })
    target.value = null
    channel.value = ""
    note.value = ""
    occurredAt.value = toLocalInput(new Date())
  } catch (reason) { error.value = userMessage(reason) }
}

watch(recordId, () => void load(), { immediate: true })
</script>

<template>
  <AppShell>
    <RouterLink
      class="back-link"
      to="/applications"
    >
      <ArrowLeft :size="16" /> 返回投递记录
    </RouterLink>
    <StatePanel
      v-if="store.loading && !store.current"
      mode="loading"
      title="正在读取投递记录"
    />
    <StatePanel
      v-else-if="error && !store.current"
      mode="error"
      title="无法读取投递记录"
      :message="error"
      @retry="load"
    />
    <template v-else-if="store.current">
      <header class="resume-detail-header">
        <div>
          <p class="eyebrow">
            用户确认状态
          </p>
          <h2>{{ statusLabels[store.current.status] }}</h2>
          <p>更新于 {{ new Date(store.current.updated_at).toLocaleString('zh-CN') }}</p>
        </div>
        <div class="detail-actions">
          <span class="immutable-badge">
            <ShieldCheck :size="18" />
            <span><strong>记录 v{{ store.current.version }}</strong><small>手工状态</small></span>
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
        <div><dt>投递决定</dt><dd>{{ store.current.application_decision_id }}</dd></div>
        <div><dt>决策案例</dt><dd>{{ store.current.decision_case_id }}</dd></div>
        <div><dt>定制简历</dt><dd>{{ store.current.resume_variant_id }} · v{{ store.current.resume_variant_version }}</dd></div>
        <div><dt>PDF Artifact</dt><dd>{{ store.current.artifact_id ? `${store.current.artifact_id} · v${store.current.artifact_version}` : '未选用' }}</dd></div>
        <div><dt>消息草稿</dt><dd>{{ store.current.message_draft_id ? `${store.current.message_draft_id} · v${store.current.message_draft_version}` : '未选用' }}</dd></div>
        <div><dt>创建人</dt><dd>{{ store.current.created_by }}</dd></div>
      </dl>

      <section
        v-if="availableTargets.length"
        class="application-transition-band"
      >
        <div class="message-band-heading">
          <Send :size="19" />
          <h3>记录状态变化</h3>
        </div>
        <div
          class="application-status-control"
          role="group"
          aria-label="目标状态"
        >
          <button
            v-for="value in availableTargets"
            :key="value"
            type="button"
            :class="{ active: target === value }"
            @click="target = value"
          >
            {{ statusLabels[value] }}
          </button>
        </div>
        <div
          v-if="target"
          class="form-grid two-columns application-transition-form"
        >
          <label>
            <span>发生时间</span>
            <input
              v-model="occurredAt"
              type="datetime-local"
              required
            >
          </label>
          <label>
            <span>{{ target === 'applied' ? '投递渠道' : '来源渠道（可选）' }}</span>
            <select
              v-model="channel"
              :required="target === 'applied'"
            >
              <option value="">未选择</option>
              <option
                v-for="option in channelOptions"
                :key="option"
                :value="option"
              >
                {{ option }}
              </option>
            </select>
          </label>
          <label class="application-note-field">
            <span>备注（可选）</span>
            <textarea
              v-model="note"
              rows="3"
              maxlength="1000"
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
        <div
          v-if="target"
          class="form-actions"
        >
          <button
            class="button button-primary"
            type="button"
            :disabled="store.saving || !occurredAt || (target === 'applied' && !channel)"
            @click="confirmTransition"
          >
            <Send :size="17" /> {{ store.saving ? '正在保存…' : `确认${statusLabels[target]}` }}
          </button>
        </div>
      </section>

      <section class="application-history-band">
        <div class="message-band-heading">
          <Clock3 :size="19" />
          <h3>转换历史</h3>
        </div>
        <p
          v-if="store.transitions.length === 0"
          class="empty-inline"
        >
          尚无状态转换
        </p>
        <ol
          v-else
          class="application-timeline"
        >
          <li
            v-for="item in store.transitions"
            :key="item.id"
          >
            <span class="timeline-marker" />
            <div>
              <strong>{{ statusLabels[item.from_status] }} → {{ statusLabels[item.to_status] }}</strong>
              <p>{{ new Date(item.occurred_at).toLocaleString('zh-CN') }} · {{ item.channel || '无渠道' }}</p>
              <small>{{ item.note || '无备注' }} · 记录 v{{ item.record_version }}</small>
            </div>
          </li>
        </ol>
      </section>
    </template>
  </AppShell>
</template>
