<script setup lang="ts">
import { ref, onErrorCaptured } from "vue"
import { TriangleAlert } from "lucide-vue-next"

const failed = ref(false)
onErrorCaptured(() => {
  failed.value = true
  return false
})
</script>

<template>
  <div
    v-if="failed"
    class="fatal-error"
  >
    <TriangleAlert :size="28" />
    <h2>页面暂时无法显示</h2>
    <p>刷新后重试；你的登录令牌不会写入浏览器地址或日志。</p>
    <button
      class="button button-primary"
      type="button"
      @click="failed = false"
    >
      重试
    </button>
  </div>
  <slot v-else />
</template>
