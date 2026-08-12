<script setup lang="ts">
import { ref } from "vue"
import { Check, Send, X } from "lucide-vue-next"

import type {
  ApplicationDecision,
  ApplicationDecisionStatus,
  CreateApplicationDecisionInput,
} from "@/api/types"

defineProps<{
  decision: ApplicationDecision | null
  saving: boolean
}>()

const emit = defineEmits<{
  submit: [input: CreateApplicationDecisionInput]
}>()

const status = ref<ApplicationDecisionStatus>("apply")
const reason = ref("")

function submit(): void {
  emit("submit", {
    status: status.value,
    reason: reason.value.trim() || null,
  })
}
</script>

<template>
  <section
    class="decision-bar"
    aria-label="投递决定"
  >
    <template v-if="decision">
      <div class="decision-recorded">
        <span
          class="decision-icon"
          :class="`decision-${decision.status}`"
        >
          <Check
            v-if="decision.status === 'apply'"
            :size="18"
          />
          <X
            v-else
            :size="18"
          />
        </span>
        <div>
          <p class="eyebrow">
            已记录决定
          </p>
          <h3>{{ decision.status === 'apply' ? '准备投递' : '暂不投递' }}</h3>
          <p v-if="decision.reason">
            {{ decision.reason }}
          </p>
          <small>
            报告 v{{ decision.report_version }} · 简历 v{{ decision.resume_version }} ·
            {{ new Date(decision.decided_at).toLocaleString('zh-CN') }}
          </small>
        </div>
      </div>
    </template>
    <form
      v-else
      @submit.prevent="submit"
    >
      <div class="decision-heading">
        <div>
          <p class="eyebrow">
            下一步
          </p>
          <h3>记录投不投决定</h3>
          <p>决定固定引用本报告和分析所用简历，不会自动投递或生成材料。</p>
        </div>
        <div
          class="decision-segments"
          aria-label="决定类型"
        >
          <button
            type="button"
            :class="{ active: status === 'apply' }"
            @click="status = 'apply'"
          >
            <Check :size="16" /> 投递
          </button>
          <button
            type="button"
            :class="{ active: status === 'skip' }"
            @click="status = 'skip'"
          >
            <X :size="16" /> 不投
          </button>
        </div>
      </div>
      <label v-if="status === 'skip'">不投原因
        <textarea
          v-model="reason"
          maxlength="1000"
          required
          placeholder="记录本次不投的关键原因"
        />
      </label>
      <div class="decision-actions">
        <span>{{ status === 'apply' ? '仅记录投递意图' : '原因将保留用于后续复盘' }}</span>
        <button
          class="button button-primary"
          type="submit"
          :disabled="saving || (status === 'skip' && !reason.trim())"
        >
          <Send :size="16" />{{ saving ? '正在记录' : '确认决定' }}
        </button>
      </div>
    </form>
  </section>
</template>
