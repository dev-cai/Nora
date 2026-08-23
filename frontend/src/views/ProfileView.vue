<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { onBeforeRouteLeave } from "vue-router"
import { FileUp, Plus, Save, Trash2 } from "lucide-vue-next"

import { api, userMessage } from "@/api/client"
import type {
  CandidateProfile,
  CandidateProfileInput,
  ConfirmationStatus,
  ProfileFact,
  ProfileFactInput,
} from "@/api/types"
import AppShell from "@/components/AppShell.vue"
import ConfirmationSelect from "@/components/ConfirmationSelect.vue"
import StatePanel from "@/components/StatePanel.vue"
import { cloneProfileInput } from "@/features/profile-input"
import { useProfileStore } from "@/stores/profile"

const store = useProfileStore()
const draft = ref<CandidateProfileInput>(blankProfile())
const baseline = ref("")
const error = ref("")
const success = ref("")
const saving = ref(false)
const importing = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const dirty = computed(() => baseline.value !== "" && JSON.stringify(draft.value) !== baseline.value)

function fact<T>(value: T, confirmation_status: ConfirmationStatus = "unconfirmed"): ProfileFactInput<T> {
  return { value, confirmation_status }
}

function blankProfile(): CandidateProfileInput {
  return {
    basic_information: { display_name: fact(""), current_location: fact("") },
    preferences: { target_locations: fact([]), accepts_remote: fact(false), target_roles: fact([]) },
    education: [], experiences: [], skills: [],
  }
}

function editableFact<T>(source: ProfileFact<T>): ProfileFactInput<T> {
  return { value: structuredClone(source.value), confirmation_status: source.confirmation_status }
}

function toInput(profile: CandidateProfile): CandidateProfileInput {
  const content = profile.content
  return {
    basic_information: {
      display_name: editableFact(content.basic_information.display_name),
      current_location: editableFact(content.basic_information.current_location),
    },
    preferences: {
      target_locations: editableFact(content.preferences.target_locations),
      accepts_remote: editableFact(content.preferences.accepts_remote),
      target_roles: editableFact(content.preferences.target_roles),
    },
    education: content.education.map((item) => ({
      id: item.id, school: editableFact(item.school), degree: editableFact(item.degree),
      major: editableFact(item.major), start_date: editableFact(item.start_date), end_date: editableFact(item.end_date),
    })),
    experiences: content.experiences.map((item) => ({
      id: item.id, company: editableFact(item.company), job_title: editableFact(item.job_title),
      start_date: editableFact(item.start_date), end_date: editableFact(item.end_date),
      responsibilities: editableFact(item.responsibilities), achievements: editableFact(item.achievements),
    })),
    skills: content.skills.map((item) => ({
      id: item.id, name: editableFact(item.name), proficiency: editableFact(item.proficiency), years: editableFact(item.years),
    })),
  }
}

function addEducation(): void {
  draft.value.education.push({
    id: crypto.randomUUID(), school: fact(""), degree: fact(""), major: fact(""), start_date: fact(null), end_date: fact(null),
  })
}

function addExperience(): void {
  draft.value.experiences.push({
    id: crypto.randomUUID(), company: fact(""), job_title: fact(""), start_date: fact(null), end_date: fact(null),
    responsibilities: fact([]), achievements: fact([]),
  })
}

function addSkill(): void {
  draft.value.skills.push({ id: crypto.randomUUID(), name: fact(""), proficiency: fact(null), years: fact(null) })
}

function listText(values: string[]): string { return values.join("\n") }
function setList(target: ProfileFactInput<string[]>, value: string): void {
  target.value = value.split("\n").map((item) => item.trim()).filter(Boolean)
}

function validate(): string {
  if (!draft.value.basic_information.display_name.value.trim() || !draft.value.basic_information.current_location.value.trim()) {
    return "请填写姓名和当前所在地"
  }
  for (const item of draft.value.education) {
    if (![item.school.value, item.degree.value, item.major.value].every((value) => value.trim())) return "请完整填写每段教育经历"
    if (item.start_date.value && item.end_date.value && item.end_date.value < item.start_date.value) return "教育经历结束日期不能早于开始日期"
  }
  for (const item of draft.value.experiences) {
    if (!item.company.value.trim() || !item.job_title.value.trim()) return "请完整填写每段工作经历"
    if (item.start_date.value && item.end_date.value && item.end_date.value < item.start_date.value) return "工作经历结束日期不能早于开始日期"
  }
  if (draft.value.skills.some((item) => !item.name.value.trim())) return "技能名称不能为空"
  return ""
}

async function load(): Promise<void> {
  error.value = ""
  try {
    const profile = await store.fetchProfile()
    draft.value = profile ? toInput(profile) : blankProfile()
    baseline.value = JSON.stringify(draft.value)
  } catch (reason) { error.value = userMessage(reason) }
}

async function save(): Promise<void> {
  error.value = validate()
  success.value = ""
  if (error.value) return
  saving.value = true
  try {
    const payload = cloneProfileInput(draft.value)
    for (const item of payload.education) {
      item.start_date.value ||= null
      item.end_date.value ||= null
    }
    for (const item of payload.experiences) {
      item.start_date.value ||= null
      item.end_date.value ||= null
    }
    for (const item of payload.skills) {
      item.proficiency.value = item.proficiency.value?.trim() || null
      item.years.value = typeof item.years.value === "number" ? item.years.value : null
    }
    const profile = await store.saveProfile(payload)
    draft.value = toInput(profile)
    baseline.value = JSON.stringify(draft.value)
    success.value = `主档第 ${profile.version} 版已保存`
  } catch (reason) { error.value = userMessage(reason) }
  finally { saving.value = false }
}

function chooseResumePdf(): void {
  fileInput.value?.click()
}

async function importResumePdf(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ""
  if (!file) return
  if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
    error.value = "请选择 PDF 简历文件"
    return
  }
  importing.value = true
  error.value = ""
  success.value = ""
  try {
    const result = await api.importProfilePdf(file)
    draft.value = result.draft
    success.value = "AI 已解析简历，请检查候选字段后保存主档"
  } catch (reason) { error.value = userMessage(reason) }
  finally { importing.value = false }
}

function beforeUnload(event: BeforeUnloadEvent): void {
  if (dirty.value) event.preventDefault()
}
onBeforeRouteLeave(() => !dirty.value || window.confirm("主档有未保存修改，确定离开吗？"))
onMounted(() => { window.addEventListener("beforeunload", beforeUnload); void load() })
onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload))
</script>

<template>
  <AppShell>
    <section class="section-toolbar page-toolbar">
      <div>
        <p class="eyebrow">
          候选人事实源
        </p><h2>我的主档</h2><p>维护可追溯的事实，并明确每个字段的确认状态。</p>
      </div>
      <div class="toolbar-actions">
        <input
          ref="fileInput"
          class="visually-hidden"
          type="file"
          accept="application/pdf,.pdf"
          @change="importResumePdf"
        >
        <button
          class="button button-secondary"
          type="button"
          :disabled="importing"
          @click="chooseResumePdf"
        >
          <FileUp :size="17" />{{ importing ? "正在解析简历…" : "AI 导入 PDF 简历" }}
        </button>
        <span
          v-if="store.current"
          class="version-badge"
        >主档 v{{ store.current.version }}</span>
      </div>
    </section>
    <StatePanel
      v-if="store.isLoading && !baseline"
      mode="loading"
      title="正在加载主档"
    />
    <StatePanel
      v-else-if="error && !baseline"
      mode="error"
      title="无法加载主档"
      :message="error"
      @retry="load"
    />
    <form
      v-else
      class="profile-form"
      @submit.prevent="save"
    >
      <section class="form-section">
        <div class="form-section-heading">
          <div><span>01</span><h3>基本信息</h3></div><p>用于简历识别的基础事实。</p>
        </div>
        <div class="fact-grid two-columns">
          <div class="fact-field">
            <label>姓名<input
              v-model="draft.basic_information.display_name.value"
              maxlength="200"
            ></label><ConfirmationSelect v-model="draft.basic_information.display_name.confirmation_status" />
          </div>
          <div class="fact-field">
            <label>当前所在地<input
              v-model="draft.basic_information.current_location.value"
              maxlength="200"
            ></label><ConfirmationSelect v-model="draft.basic_information.current_location.confirmation_status" />
          </div>
        </div>
      </section>

      <section class="form-section">
        <div class="form-section-heading">
          <div><span>02</span><h3>求职偏好</h3></div><p>每行填写一个地点或目标职位。</p>
        </div>
        <div class="fact-grid two-columns">
          <div class="fact-field">
            <label>目标地点<textarea
              :value="listText(draft.preferences.target_locations.value)"
              rows="3"
              @input="setList(draft.preferences.target_locations, ($event.target as HTMLTextAreaElement).value)"
            /></label><ConfirmationSelect v-model="draft.preferences.target_locations.confirmation_status" />
          </div>
          <div class="fact-field">
            <label>目标职位<textarea
              :value="listText(draft.preferences.target_roles.value)"
              rows="3"
              @input="setList(draft.preferences.target_roles, ($event.target as HTMLTextAreaElement).value)"
            /></label><ConfirmationSelect v-model="draft.preferences.target_roles.confirmation_status" />
          </div>
          <div class="fact-field compact">
            <label class="checkbox-label"><input
              v-model="draft.preferences.accepts_remote.value"
              type="checkbox"
            >接受远程工作</label><ConfirmationSelect v-model="draft.preferences.accepts_remote.confirmation_status" />
          </div>
        </div>
      </section>

      <section class="form-section">
        <div class="form-section-heading">
          <div><span>03</span><h3>教育经历</h3></div><button
            class="button button-secondary"
            type="button"
            @click="addEducation"
          >
            <Plus :size="16" />添加教育
          </button>
        </div>
        <p
          v-if="draft.education.length === 0"
          class="empty-inline"
        >
          尚未添加教育经历。
        </p>
        <div
          v-for="(item, index) in draft.education"
          :key="item.id"
          class="repeat-block"
        >
          <div class="repeat-header">
            <strong>教育 {{ index + 1 }}</strong><button
              class="icon-button danger"
              type="button"
              title="删除教育经历"
              @click="draft.education.splice(index, 1)"
            >
              <Trash2 :size="17" />
            </button>
          </div>
          <div class="fact-grid three-columns">
            <div class="fact-field">
              <label>学校<input
                v-model="item.school.value"
                maxlength="200"
              ></label><ConfirmationSelect v-model="item.school.confirmation_status" />
            </div>
            <div class="fact-field">
              <label>学历<input
                v-model="item.degree.value"
                maxlength="200"
              ></label><ConfirmationSelect v-model="item.degree.confirmation_status" />
            </div>
            <div class="fact-field">
              <label>专业<input
                v-model="item.major.value"
                maxlength="200"
              ></label><ConfirmationSelect v-model="item.major.confirmation_status" />
            </div>
            <div class="fact-field">
              <label>开始日期<input
                v-model="item.start_date.value"
                type="date"
              ></label><ConfirmationSelect v-model="item.start_date.confirmation_status" />
            </div>
            <div class="fact-field">
              <label>结束日期<input
                v-model="item.end_date.value"
                type="date"
              ></label><ConfirmationSelect v-model="item.end_date.confirmation_status" />
            </div>
          </div>
        </div>
      </section>

      <section class="form-section">
        <div class="form-section-heading">
          <div><span>04</span><h3>工作经历</h3></div><button
            class="button button-secondary"
            type="button"
            @click="addExperience"
          >
            <Plus :size="16" />添加经历
          </button>
        </div>
        <p
          v-if="draft.experiences.length === 0"
          class="empty-inline"
        >
          尚未添加工作经历。
        </p>
        <div
          v-for="(item, index) in draft.experiences"
          :key="item.id"
          class="repeat-block"
        >
          <div class="repeat-header">
            <strong>经历 {{ index + 1 }}</strong><button
              class="icon-button danger"
              type="button"
              title="删除工作经历"
              @click="draft.experiences.splice(index, 1)"
            >
              <Trash2 :size="17" />
            </button>
          </div>
          <div class="fact-grid two-columns">
            <div class="fact-field">
              <label>公司<input
                v-model="item.company.value"
                maxlength="200"
              ></label><ConfirmationSelect v-model="item.company.confirmation_status" />
            </div>
            <div class="fact-field">
              <label>职位<input
                v-model="item.job_title.value"
                maxlength="200"
              ></label><ConfirmationSelect v-model="item.job_title.confirmation_status" />
            </div>
            <div class="fact-field">
              <label>开始日期<input
                v-model="item.start_date.value"
                type="date"
              ></label><ConfirmationSelect v-model="item.start_date.confirmation_status" />
            </div>
            <div class="fact-field">
              <label>结束日期<input
                v-model="item.end_date.value"
                type="date"
              ></label><ConfirmationSelect v-model="item.end_date.confirmation_status" />
            </div>
            <div class="fact-field">
              <label>职责（每行一项）<textarea
                :value="listText(item.responsibilities.value)"
                rows="4"
                @input="setList(item.responsibilities, ($event.target as HTMLTextAreaElement).value)"
              /></label><ConfirmationSelect v-model="item.responsibilities.confirmation_status" />
            </div>
            <div class="fact-field">
              <label>成果（每行一项）<textarea
                :value="listText(item.achievements.value)"
                rows="4"
                @input="setList(item.achievements, ($event.target as HTMLTextAreaElement).value)"
              /></label><ConfirmationSelect v-model="item.achievements.confirmation_status" />
            </div>
          </div>
        </div>
      </section>

      <section class="form-section">
        <div class="form-section-heading">
          <div><span>05</span><h3>技能</h3></div><button
            class="button button-secondary"
            type="button"
            @click="addSkill"
          >
            <Plus :size="16" />添加技能
          </button>
        </div>
        <p
          v-if="draft.skills.length === 0"
          class="empty-inline"
        >
          尚未添加技能。
        </p>
        <div
          v-for="(item, index) in draft.skills"
          :key="item.id"
          class="repeat-block skill-row"
        >
          <div class="fact-grid three-columns">
            <div class="fact-field">
              <label>技能名称<input
                v-model="item.name.value"
                maxlength="200"
              ></label><ConfirmationSelect v-model="item.name.confirmation_status" />
            </div>
            <div class="fact-field">
              <label>熟练度<input
                v-model="item.proficiency.value"
                maxlength="200"
              ></label><ConfirmationSelect v-model="item.proficiency.confirmation_status" />
            </div>
            <div class="fact-field">
              <label>使用年限<input
                v-model.number="item.years.value"
                type="number"
                min="0"
                max="100"
                step="0.5"
              ></label><ConfirmationSelect v-model="item.years.confirmation_status" />
            </div>
          </div>
          <button
            class="icon-button danger skill-delete"
            type="button"
            title="删除技能"
            @click="draft.skills.splice(index, 1)"
          >
            <Trash2 :size="17" />
          </button>
        </div>
      </section>

      <p
        v-if="error"
        class="form-error"
        role="alert"
      >
        {{ error }}
      </p>
      <p
        v-if="success"
        class="form-success"
        role="status"
      >
        {{ success }}
      </p>
      <div class="sticky-actions">
        <span>{{ dirty ? "有未保存修改" : "所有修改已保存" }}</span><button
          class="button button-primary"
          type="submit"
          :disabled="saving || !dirty"
        >
          <Save :size="17" />{{ saving ? "正在保存…" : "保存主档新版本" }}
        </button>
      </div>
    </form>
  </AppShell>
</template>
