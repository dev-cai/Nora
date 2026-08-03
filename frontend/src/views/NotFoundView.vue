<script setup lang="ts">
import { Compass } from "lucide-vue-next"
</script>

<template>
  <main class="not-found">
    <Compass :size="34" /><p class="eyebrow">
      404
    </p><h1>页面不存在</h1><p>你访问的地址无效，或该页面尚未开放。</p><RouterLink
      class="button button-primary"
      to="/"
    >
      返回工作台
    </RouterLink>
  </main>
</template>
