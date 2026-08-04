<script setup lang="ts">
defineProps<{ content: Record<string, unknown> }>()

const sectionLabels: Record<string, string> = {
  basic_information: "基本信息",
  preferences: "求职偏好",
  education: "教育经历",
  experiences: "工作经历",
  skills: "技能",
}
const fieldLabels: Record<string, string> = {
  display_name: "姓名", current_location: "当前所在地", target_locations: "目标地点",
  accepts_remote: "接受远程", target_roles: "目标职位", school: "学校", degree: "学历",
  major: "专业", start_date: "开始日期", end_date: "结束日期", company: "公司",
  job_title: "职位", responsibilities: "职责", achievements: "成果", name: "名称",
  proficiency: "熟练度", years: "使用年限",
}

function label(key: string): string { return fieldLabels[key] || key }
function display(value: unknown): string {
  if (Array.isArray(value)) return value.join("、")
  if (typeof value === "boolean") return value ? "是" : "否"
  if (value === null || value === undefined || value === "") return "—"
  return String(value)
}
function entries(value: unknown): Array<[string, unknown]> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? Object.entries(value as Record<string, unknown>).filter(([key]) => key !== "id") : []
}
</script>

<template>
  <div class="snapshot-content">
    <section
      v-for="(section, key) in content"
      :key="key"
      class="snapshot-section"
    >
      <h3>{{ sectionLabels[String(key)] || key }}</h3>
      <div
        v-if="Array.isArray(section)"
        class="snapshot-list"
      >
        <article
          v-for="(item, index) in section"
          :key="String((item as Record<string, unknown>).id || index)"
          class="snapshot-item"
        >
          <dl>
            <template
              v-for="([field, value]) in entries(item)"
              :key="field"
            >
              <dt>{{ label(field) }}</dt><dd>{{ display(value) }}</dd>
            </template>
          </dl>
        </article>
      </div>
      <dl v-else>
        <template
          v-for="([field, value]) in entries(section)"
          :key="field"
        >
          <dt>{{ label(field) }}</dt><dd>{{ display(value) }}</dd>
        </template>
      </dl>
    </section>
  </div>
</template>
