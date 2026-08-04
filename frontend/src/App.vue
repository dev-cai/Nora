<script setup lang="ts">
import AppErrorBoundary from "@/components/AppErrorBoundary.vue"
</script>

<template>
  <AppErrorBoundary>
    <RouterView v-slot="{ Component }">
      <Transition
        name="route"
        mode="out-in"
      >
        <component :is="Component" />
      </Transition>
    </RouterView>
  </AppErrorBoundary>
</template>
