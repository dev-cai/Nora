<script setup lang="ts">
import { ref } from "vue"
import { ArrowRight, UserPlus } from "lucide-vue-next"
import { useRouter } from "vue-router"

import { userMessage } from "@/api/client"
import { useAuthStore } from "@/stores/auth"

const auth = useAuthStore()
const router = useRouter()
const username = ref("")
const email = ref("")
const password = ref("")
const confirmPassword = ref("")
const error = ref("")
const loading = ref(false)

async function submit(): Promise<void> {
  error.value = ""
  if (password.value.length < 8) { error.value = "密码至少需要 8 个字符"; return }
  if (password.value !== confirmPassword.value) { error.value = "两次输入的密码不一致"; return }
  loading.value = true
  try {
    await auth.register(username.value, email.value, password.value)
    await router.push({ name: "login", query: { registered: "1" } })
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
        <span class="brand-mark">N</span><span><strong>Nora</strong><small>求职决策工作台</small></span>
      </div>
      <p class="eyebrow">
        从事实开始
      </p>
      <h1>建立属于你的求职上下文。</h1>
      <p class="auth-copy">
        先保存真实岗位，再逐步补齐主档和简历版本。每个阶段都能回到清晰的历史记录。
      </p>
    </section>
    <section
      class="auth-card"
      aria-labelledby="register-title"
    >
      <div class="section-heading">
        <div class="icon-badge">
          <UserPlus :size="18" />
        </div><div>
          <p class="eyebrow">
            新用户
          </p><h2 id="register-title">
            创建账号
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
          placeholder="3–64 个字符"
          required
        ></label>
        <label>邮箱<input
          v-model="email"
          type="email"
          autocomplete="email"
          placeholder="name@example.com"
          required
        ></label>
        <label>密码<input
          v-model="password"
          type="password"
          autocomplete="new-password"
          placeholder="至少 8 个字符"
          required
        ></label>
        <label>确认密码<input
          v-model="confirmPassword"
          type="password"
          autocomplete="new-password"
          placeholder="再次输入密码"
          required
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
          {{ loading ? "正在创建…" : "创建账号" }} <ArrowRight :size="17" />
        </button>
      </form>
      <p class="form-footnote">
        已有账号？ <RouterLink to="/login">
          返回登录
        </RouterLink>
      </p>
    </section>
  </main>
</template>
