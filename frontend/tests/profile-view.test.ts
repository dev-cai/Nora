import { flushPromises, mount } from "@vue/test-utils"
import { createPinia } from "pinia"
import { createMemoryHistory, createRouter } from "vue-router"

import { api } from "@/api/client"
import type { CandidateProfile, CandidateProfileInput } from "@/api/types"
import ProfileView from "@/views/ProfileView.vue"

vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client")
  return {
    ...actual,
    api: {
      getProfile: vi.fn(),
      saveProfile: vi.fn(),
      importProfilePdf: vi.fn(),
    },
  }
})

const stubs = {
  AppShell: { template: "<main><slot /></main>" },
}

function storedFact<T>(value: T): { value: T; confirmation_status: "unconfirmed"; source_type: "user_input"; updated_at: string } {
  return { value, confirmation_status: "unconfirmed", source_type: "user_input", updated_at: "2026-08-01T00:00:00Z" }
}

const existingProfile = {
  id: "profile-1",
  owner_id: "owner-1",
  version: 1,
  content: {
    basic_information: { display_name: storedFact("Existing"), current_location: storedFact("Shanghai") },
    preferences: {
      target_locations: storedFact(["Shanghai"]),
      accepts_remote: storedFact(false),
      target_roles: storedFact(["Engineer"]),
    },
    education: [],
    experiences: [],
    skills: [],
  },
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
} as CandidateProfile

const importedDraft: CandidateProfileInput = {
  basic_information: {
    display_name: { value: "Alice", confirmation_status: "unconfirmed" },
    current_location: { value: "Shanghai", confirmation_status: "unconfirmed" },
  },
  preferences: {
    target_locations: { value: ["Shanghai"], confirmation_status: "unconfirmed" },
    accepts_remote: { value: false, confirmation_status: "unconfirmed" },
    target_roles: { value: ["Backend Engineer"], confirmation_status: "unconfirmed" },
  },
  education: [],
  experiences: [],
  skills: [],
}

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/profile", component: ProfileView }],
  })
  await router.push("/profile")
  const wrapper = mount(ProfileView, { global: { plugins: [createPinia(), router], stubs } })
  await flushPromises()
  return wrapper
}

describe("ProfileView", () => {
  beforeEach(() => {
    vi.mocked(api.getProfile).mockResolvedValue(existingProfile)
    vi.mocked(api.importProfilePdf).mockReset()
    vi.mocked(api.saveProfile).mockResolvedValue({ ...existingProfile, version: 2 })
  })

  it("confirms an imported profile with one submit instead of field confirmations", async () => {
    vi.mocked(api.importProfilePdf).mockResolvedValue({ draft: importedDraft })
    const wrapper = await mountView()
    const file = new File(["resume"], "resume.pdf", { type: "application/pdf" })
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, "files", { value: [file] })

    await input.trigger("change")
    await flushPromises()

    expect(wrapper.findAll(".confirmation-control")).toHaveLength(0)
    expect(wrapper.text()).toContain("一次确认导入主档")

    await wrapper.get("form").trigger("submit")
    await flushPromises()

    const saved = vi.mocked(api.saveProfile).mock.calls[0]?.[0]
    expect(saved?.basic_information.display_name.confirmation_status).toBe("confirmed")
    expect(saved?.preferences.target_roles.confirmation_status).toBe("confirmed")
    expect(saved?.preferences.accepts_remote.confirmation_status).toBe("unconfirmed")
  })
})
