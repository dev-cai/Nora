import { createPinia, setActivePinia } from "pinia"

import { api } from "@/api/client"
import { AUTH_SESSION_STORAGE_KEY, useAuthStore } from "@/stores/auth"

const user = { id: "user-1", username: "alice", email: "alice@example.com" }

describe("auth session", () => {
  beforeEach(() => {
    sessionStorage.clear()
    setActivePinia(createPinia())
  })

  it("persists login and restores the session from storage", async () => {
    vi.spyOn(api, "login").mockResolvedValue({ access_token: "token-1", token_type: "bearer" })
    vi.spyOn(api, "me").mockResolvedValue(user)
    const store = useAuthStore()
    await store.login("alice", "password")
    expect(JSON.parse(sessionStorage.getItem(AUTH_SESSION_STORAGE_KEY) || "{}"))
      .toMatchObject({ token: "token-1", user })

    setActivePinia(createPinia())
    const restored = useAuthStore()
    expect(restored.isAuthenticated).toBe(true)
    await restored.restoreSession()
    expect(restored.user).toEqual(user)
  })

  it("clears persisted session on logout and invalid restoration", async () => {
    sessionStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify({ token: "expired", user }))
    vi.spyOn(api, "me").mockRejectedValue(new Error("expired"))
    const store = useAuthStore()
    await store.restoreSession()
    expect(sessionStorage.getItem(AUTH_SESSION_STORAGE_KEY)).toBeNull()
    expect(store.isAuthenticated).toBe(false)
  })
})
