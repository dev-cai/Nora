import type { Pinia } from "pinia"
import { createRouter, createWebHistory } from "vue-router"

import { useAuthStore } from "@/stores/auth"
import { publicRegistrationEnabled } from "@/config"

const LoginView = () => import("@/views/LoginView.vue")

export function createAppRouter(pinia: Pinia) {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: "/", name: "dashboard", component: () => import("@/views/DashboardView.vue"), meta: { requiresAuth: true } },
      { path: "/login", name: "login", component: LoginView, meta: { guestOnly: true } },
      ...(publicRegistrationEnabled
        ? [{ path: "/register", name: "register", component: () => import("@/views/RegisterView.vue"), meta: { guestOnly: true } }]
        : []),
      { path: "/jobs", name: "jobs", component: () => import("@/views/JobsView.vue"), meta: { requiresAuth: true } },
      { path: "/jobs/new", name: "job-new", component: () => import("@/views/JobCreateView.vue"), meta: { requiresAuth: true } },
      { path: "/jobs/:id", name: "job-detail", component: () => import("@/views/JobDetailView.vue"), meta: { requiresAuth: true } },
      { path: "/jobs/:id/requirements", name: "job-requirements", component: () => import("@/views/JobRequirementsView.vue"), meta: { requiresAuth: true, title: "岗位要求确认" } },
      { path: "/profile", name: "profile", component: () => import("@/views/ProfileView.vue"), meta: { requiresAuth: true, title: "我的主档" } },
      { path: "/resumes", name: "resumes", component: () => import("@/views/ResumesView.vue"), meta: { requiresAuth: true, title: "简历版本" } },
      { path: "/resumes/new", name: "resume-new", component: () => import("@/views/ResumeNewView.vue"), meta: { requiresAuth: true, title: "发布新简历" } },
      { path: "/resumes/:id/customize", name: "resume-customize", component: () => import("@/views/ResumeCustomizeView.vue"), meta: { requiresAuth: true, title: "定制简历" } },
      { path: "/resumes/:id", name: "resume-detail", component: () => import("@/views/ResumeDetailView.vue"), meta: { requiresAuth: true, title: "简历详情" } },
      { path: "/templates", name: "templates", component: () => import("@/views/TemplatesView.vue"), meta: { requiresAuth: true, title: "定制简历" } },
      { path: "/resume-variants/:id", name: "resume-variant-detail", component: () => import("@/views/ResumeVariantDetailView.vue"), meta: { requiresAuth: true, title: "定制简历详情" } },
      { path: "/messages/:id", name: "message-draft", component: () => import("@/views/MessageDraftView.vue"), meta: { requiresAuth: true, title: "消息草稿" } },
      { path: "/applications", name: "applications", component: () => import("@/views/ApplicationRecordsView.vue"), meta: { requiresAuth: true, title: "投递记录" } },
      { path: "/applications/new", name: "application-new", component: () => import("@/views/ApplicationRecordCreateView.vue"), meta: { requiresAuth: true, title: "确认投递材料" } },
      { path: "/applications/:id", name: "application-detail", component: () => import("@/views/ApplicationRecordDetailView.vue"), meta: { requiresAuth: true, title: "投递详情" } },
      { path: "/analysis/new", name: "analysis-new", component: () => import("@/views/AnalysisNewView.vue"), meta: { requiresAuth: true, title: "发起分析" } },
      { path: "/analysis/:id", name: "analysis-detail", component: () => import("@/views/AnalysisDetailView.vue"), meta: { requiresAuth: true, title: "分析结果" } },
      { path: "/reports", name: "reports", component: () => import("@/views/ReportsView.vue"), meta: { requiresAuth: true, title: "分析报告" } },
      { path: "/reports/:id", name: "report-detail", component: () => import("@/views/ReportDetailView.vue"), meta: { requiresAuth: true, title: "报告详情" } },
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
