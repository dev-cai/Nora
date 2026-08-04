<script setup lang="ts">
import type { ConfirmationStatus } from "@/api/types"

defineProps<{ modelValue: ConfirmationStatus }>()
const emit = defineEmits<{ "update:modelValue": [value: ConfirmationStatus] }>()

const labels: Record<ConfirmationStatus, string> = {
  unconfirmed: "待确认",
  confirmed: "已确认",
  rejected: "已否决",
  superseded: "已替代",
}
</script>

<template>
  <label class="confirmation-control">
    <span class="sr-only">确认状态</span>
    <select
      :value="modelValue"
      :class="`confirmation-${modelValue}`"
      :disabled="modelValue === 'superseded'"
      @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value as ConfirmationStatus)"
    >
      <option
        v-for="(label, value) in labels"
        :key="value"
        :value="value"
      >
        {{ label }}
      </option>
    </select>
  </label>
</template>
