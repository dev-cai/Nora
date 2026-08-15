import { computed, ref } from "vue"
import { defineStore } from "pinia"

import { api, setAccessToken, setUnauthorizedHandler } from "@/api/client"
import type { User } from "@/api/types"

export const AUTH_SESSION_STORAGE_KEY = "nora.auth.session"

type StoredSession = { token: string; user: User }

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(null)
  hydrate()
  const isAuthenticated = computed(() => Boolean(token.value && user.value))

  function hydrate(): void {
    try {
      const raw = sessionStorage.getItem(AUTH_SESSION_STORAGE_KEY)
      if (!raw) return
      const stored = JSON.parse(raw) as Partial<StoredSession>
      if (typeof stored.token !== "string" || !stored.user) {
        sessionStorage.removeItem(AUTH_SESSION_STORAGE_KEY)
        return
      }
      token.value = stored.token
      user.value = stored.user
      setAccessToken(stored.token)
    } catch {
      sessionStorage.removeItem(AUTH_SESSION_STORAGE_KEY)
    }
  }

  function persistSession(): void {
    if (token.value && user.value) {
      sessionStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify({ token: token.value, user: user.value }))
    }
  }

  function clearSession(): void {
    token.value = null
    user.value = null
    setAccessToken(null)
    sessionStorage.removeItem(AUTH_SESSION_STORAGE_KEY)
  }

  async function login(username: string, password: string): Promise<void> {
    const response = await api.login(username, password)
    token.value = response.access_token
    setAccessToken(response.access_token)
    try {
      user.value = await api.me()
      persistSession()
    } catch (error) {
      clearSession()
      throw error
    }
  }

  async function restoreSession(): Promise<void> {
    if (!token.value) return
    try {
      user.value = await api.me()
      persistSession()
    } catch {
      clearSession()
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

  return { user, token, isAuthenticated, login, register, restoreSession, logout, clearSession, connectUnauthorizedHandler }
})
