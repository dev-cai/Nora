<script setup lang="ts">
import { computed, ref } from "vue"
import { ArrowLeft, Building2 } from "lucide-vue-next"
import { useRoute, useRouter } from "vue-router"

import { userMessage } from "@/api/client"
import AppShell from "@/components/AppShell.vue"
import CompanySnapshotForm from "@/components/CompanySnapshotForm.vue"
import type { CompanySnapshotSubmission } from "@/stores/companies"
import { useCompaniesStore } from "@/stores/companies"

const route = useRoute()
const router = useRouter()
const store = useCompaniesStore()
const error = ref("")
const returnReportId = computed(() => typeof route.query.report === "string" ? route.query.report : null)

async function save(input: CompanySnapshotSubmission): Promise<void> {
  error.value = ""
  try {
    const reportId = returnReportId.value
    if (reportId) {
      await store.createAndAttach(reportId, input)
      await router.push({ name: "report-detail", params: { id: reportId } })
      return
    }
    const created = await store.create(input)
    await router.push({ name: "company-detail", params: { id: created.id } })
  } catch (reason) {
    error.value = userMessage(reason)
  }
}
</script>

<template>
  <AppShell>
    <RouterLink
      class="back-link"
      :to="returnReportId ? { name: 'report-detail', params: { id: returnReportId } } : { name: 'reports' }"
    >
      <ArrowLeft :size="16" /> 返回
    </RouterLink>
    <section class="section-heading company-page-heading">
      <span class="icon-badge"><Building2 :size="20" /></span>
      <div>
        <p class="eyebrow">
          版本化来源事实
        </p><h2>录入公司情报</h2>
      </div>
    </section>
    <CompanySnapshotForm
      :saving="store.saving || store.attaching"
      @submit="save"
    />
    <p
      v-if="error"
      class="form-error company-page-error"
    >
      {{ error }}
    </p>
  </AppShell>
</template>
