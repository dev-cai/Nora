import { computed, ref } from "vue"
import { defineStore } from "pinia"

import { api, setAccessToken, setUnauthorizedHandler } from "@/api/client"
import type { User } from "@/api/types"

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(null)
  const isAuthenticated = computed(() => Boolean(token.value && user.value))

  function clearSession(): void {
    token.value = null
    user.value = null
    setAccessToken(null)
  }

  async function login(username: string, password: string): Promise<void> {
    const response = await api.login(username, password)
    token.value = response.access_token
    setAccessToken(response.access_token)
    try {
      user.value = await api.me()
    } catch (error) {
      clearSession()
      throw error
    }
  }

  async function register(username: string, email: string, password: string): Promise<void> {
    await api.register(username, email, password)
  }

  function logout(): void {
    clearSession()
  }

  function connectUnauthorizedHandler(): void {
    setUnauthorizedHandler(clearSession)
  }

  return { user, token, isAuthenticated, login, register, logout, clearSession, connectUnauthorizedHandler }
})
