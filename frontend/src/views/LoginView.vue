<script setup lang="ts">
import { ref } from "vue"
import { ArrowRight, KeyRound, ShieldCheck } from "lucide-vue-next"
import { useRoute, useRouter } from "vue-router"

import { userMessage } from "@/api/client"
import { useAuthStore } from "@/stores/auth"
import { publicRegistrationEnabled } from "@/config"

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const username = ref("")
const password = ref("")
const error = ref("")
const loading = ref(false)

async function submit(): Promise<void> {
  error.value = ""
  if (!username.value.trim() || password.value.length < 1) {
    error.value = "请输入用户名和密码"
    return
  }
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    const next = typeof route.query.next === "string" ? route.query.next : "/"
    await router.push(next)
  } catch (reason) {
    error.value = userMessage(reason)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-intro">
      <div class="brand brand-large">
        <span class="brand-mark">N</span>
        <span><strong>Nora</strong><small>求职决策工作台</small></span>
      </div>
      <p class="eyebrow">
        个人求职操作系统
      </p>
      <h1>把每一次求职选择，变成可回看的证据。</h1>
      <p class="auth-copy">
        从岗位快照开始，逐步建立你的事实、版本与决策记录。
      </p>
      <div class="trust-row">
        <ShieldCheck :size="18" /> 数据按账号隔离，认证令牌仅保存在当前会话
      </div>
    </section>
    <section
      class="auth-card"
      aria-labelledby="login-title"
    >
      <div class="section-heading">
        <div class="icon-badge">
          <KeyRound :size="18" />
        </div>
        <div>
          <p class="eyebrow">
            欢迎回来
          </p><h2 id="login-title">
            登录工作台
          </h2>
        </div>
      </div>
      <form
        class="form-stack"
        @submit.prevent="submit"
      >
        <label>用户名<input
          v-model="username"
          autocomplete="username"
          placeholder="例如 alice"
        ></label>
        <label>密码<input
          v-model="password"
          type="password"
          autocomplete="current-password"
          placeholder="输入密码"
        ></label>
        <p
          v-if="error"
          class="form-error"
          role="alert"
        >
          {{ error }}
        </p>
        <button
          class="button button-primary button-wide"
          type="submit"
          :disabled="loading"
        >
          {{ loading ? "正在登录…" : "登录" }} <ArrowRight :size="17" />
        </button>
      </form>
      <p
        v-if="publicRegistrationEnabled"
        class="form-footnote"
      >
        还没有账号？ <RouterLink to="/register">
          创建账号
        </RouterLink>
      </p>
    </section>
  </main>
</template>
