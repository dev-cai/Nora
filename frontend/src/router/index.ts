import type { Pinia } from "pinia"
import { createRouter, createWebHistory } from "vue-router"

import { useAuthStore } from "@/stores/auth"

const LoginView = () => import("@/views/LoginView.vue")

export function createAppRouter(pinia: Pinia) {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: "/", name: "dashboard", component: () => import("@/views/DashboardView.vue"), meta: { requiresAuth: true } },
      { path: "/login", name: "login", component: LoginView, meta: { guestOnly: true } },
      { path: "/register", name: "register", component: () => import("@/views/RegisterView.vue"), meta: { guestOnly: true } },
      { path: "/jobs", name: "jobs", component: () => import("@/views/JobsView.vue"), meta: { requiresAuth: true } },
      { path: "/jobs/new", name: "job-new", component: () => import("@/views/JobCreateView.vue"), meta: { requiresAuth: true } },
      { path: "/jobs/:id", name: "job-detail", component: () => import("@/views/JobDetailView.vue"), meta: { requiresAuth: true } },
      { path: "/:pathMatch(.*)*", name: "not-found", component: () => import("@/views/NotFoundView.vue") },
    ],
  })

  router.beforeEach((to) => {
    const auth = useAuthStore(pinia)
    if (to.meta.requiresAuth && !auth.isAuthenticated) return { name: "login", query: { next: to.fullPath } }
    if (to.meta.guestOnly && auth.isAuthenticated) return { name: "dashboard" }
    return true
  })
  return router
}
