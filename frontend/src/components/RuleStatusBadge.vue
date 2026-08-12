<script setup lang="ts">
import type { RuleStatus } from "@/api/types"

defineProps<{ status: RuleStatus }>()

const labels: Record<RuleStatus, string> = {
  match: "满足",
  partial: "部分满足",
  mismatch: "不满足",
  unknown: "未知",
}
</script>

<template>
  <span
    class="rule-status"
    :class="`rule-status-${status}`"
  >{{ labels[status] }}</span>
</template>
