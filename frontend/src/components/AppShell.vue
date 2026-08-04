<script setup lang="ts">
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"
import {
  BriefcaseBusiness,
  FileText,
  LayoutDashboard,
  LogOut,
  LockKeyhole,
  Plus,
  UserRound,
} from "lucide-vue-next"

import { useAuthStore } from "@/stores/auth"
import { useJobsStore } from "@/stores/jobs"

const auth = useAuthStore()
const jobs = useJobsStore()
const route = useRoute()
const router = useRouter()
const initials = computed(() => auth.user?.username.slice(0, 2).toUpperCase() || "N")

function logout(): void {
  auth.logout()
  jobs.reset()
  void router.push({ name: "login" })
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <RouterLink
        class="brand"
        to="/"
        aria-label="Nora 工作台"
      >
        <span class="brand-mark">N</span>
        <span>
          <strong>Nora</strong>
          <small>求职决策工作台</small>
        </span>
      </RouterLink>

      <nav
        class="main-nav"
        aria-label="主导航"
      >
        <RouterLink
          class="nav-item"
          :class="{ active: route.name === 'dashboard' }"
          to="/"
        >
          <LayoutDashboard :size="18" />
          <span>工作台</span>
        </RouterLink>
        <RouterLink
          class="nav-item"
          :class="{ active: route.name === 'jobs' || route.name === 'job-detail' }"
          to="/jobs"
        >
          <BriefcaseBusiness :size="18" />
          <span>岗位库</span>
        </RouterLink>
        <RouterLink
          class="nav-item"
          :class="{ active: route.name === 'job-new' }"
          to="/jobs/new"
        >
          <Plus :size="18" />
          <span>录入岗位</span>
        </RouterLink>
        <span class="nav-divider">工作资产</span>
        <span
          class="nav-item disabled"
          title="M2.6 开放"
        >
          <UserRound :size="18" />
          <span>我的主档</span>
          <LockKeyhole
            class="nav-lock"
            :size="14"
          />
        </span>
        <span
          class="nav-item disabled"
          title="M2.6 开放"
        >
          <FileText :size="18" />
          <span>简历版本</span>
          <LockKeyhole
            class="nav-lock"
            :size="14"
          />
        </span>
      </nav>

      <div class="sidebar-footer">
        <div class="user-chip">
          <span class="avatar">{{ initials }}</span>
          <span class="user-meta">
            <strong>{{ auth.user?.username }}</strong>
            <small>{{ auth.user?.email }}</small>
          </span>
        </div>
        <button
          class="text-button"
          type="button"
          @click="logout"
        >
          <LogOut :size="16" />
          退出登录
        </button>
      </div>
    </aside>

    <main class="main-content">
      <header class="topbar">
        <div>
          <p class="eyebrow">
            NORA / M2 工作台
          </p>
          <h1>{{ route.meta.title || '求职工作台' }}</h1>
        </div>
        <RouterLink
          class="button button-primary top-action"
          to="/jobs/new"
        >
          <Plus :size="17" />
          录入岗位
        </RouterLink>
      </header>
      <div class="page-content">
        <slot />
      </div>
    </main>
  </div>
</template>
