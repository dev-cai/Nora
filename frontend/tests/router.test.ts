import { createPinia, setActivePinia } from "pinia"

import { createAppRouter } from "@/router"
import { useAuthStore } from "@/stores/auth"

describe("route guards", () => {
  it("redirects anonymous users to login and preserves the destination", async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createAppRouter(pinia)

    await router.push("/jobs/new")

    expect(router.currentRoute.value.name).toBe("login")
    expect(router.currentRoute.value.query.next).toBe("/jobs/new")
  })

  it("keeps authenticated users out of guest routes", async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore(pinia)
    auth.$patch({ token: "runtime-token", user: { id: "1", username: "alice", email: "alice@example.com" } })
    const router = createAppRouter(pinia)

    await router.push("/login")

    expect(router.currentRoute.value.name).toBe("dashboard")
  })
})
