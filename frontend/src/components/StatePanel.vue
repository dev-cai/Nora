<script setup lang="ts">
import { AlertCircle, Inbox, LoaderCircle } from "lucide-vue-next"

defineProps<{
  mode: "loading" | "empty" | "error"
  title: string
  message?: string
}>()

defineEmits<{ retry: [] }>()
</script>

<template>
  <div
    class="state-panel"
    :class="`state-${mode}`"
  >
    <LoaderCircle
      v-if="mode === 'loading'"
      class="spin"
      :size="24"
    />
    <Inbox
      v-else-if="mode === 'empty'"
      :size="24"
    />
    <AlertCircle
      v-else
      :size="24"
    />
    <strong>{{ title }}</strong>
    <p v-if="message">
      {{ message }}
    </p>
    <button
      v-if="mode === 'error'"
      class="button button-secondary"
      type="button"
      @click="$emit('retry')"
    >
      重新加载
    </button>
  </div>
</template>
