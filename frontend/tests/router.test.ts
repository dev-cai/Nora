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

  it("protects analysis routes and resolves their intended page", async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore(pinia)
    auth.$patch({ token: "runtime-token", user: { id: "1", username: "alice", email: "alice@example.com" } })
    const router = createAppRouter(pinia)

    await router.push("/reports/report-1")

    expect(router.currentRoute.value.name).toBe("report-detail")
    expect(router.currentRoute.value.meta.requiresAuth).toBe(true)
  })

  it("updates the immutable object id when navigating within one detail route", async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore(pinia)
    auth.$patch({ token: "runtime-token", user: { id: "1", username: "alice", email: "alice@example.com" } })
    const router = createAppRouter(pinia)

    await router.push("/reports/report-1")
    await router.push("/reports/report-2")

    expect(router.currentRoute.value.params.id).toBe("report-2")
  })
})
