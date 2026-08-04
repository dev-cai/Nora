import { createPinia, setActivePinia } from "pinia"
import { reactive } from "vue"

import { api } from "@/api/client"
import type { CandidateProfile, ResumeVersion } from "@/api/types"
import { cloneProfileInput } from "@/features/profile-input"
import { confirmedSnapshot, hasSnapshotFacts } from "@/features/profile-snapshot"
import { useProfileStore } from "@/stores/profile"
import { useResumesStore } from "@/stores/resumes"

vi.mock("@/api/client", () => ({
  api: {
    getProfile: vi.fn(), saveProfile: vi.fn(), listResumes: vi.fn(), getResume: vi.fn(), publishResume: vi.fn(),
  },
  ApiError: class ApiError extends Error { status = 404 },
}))

const profile = { version: 2, content: {} } as CandidateProfile
const resume = { id: "resume-1", title: "Backend", version: 1 } as ResumeVersion

describe("career stores and snapshot", () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

  it("reloads and saves the current profile", async () => {
    vi.mocked(api.getProfile).mockResolvedValue(profile)
    vi.mocked(api.saveProfile).mockResolvedValue({ ...profile, version: 3 })
    const store = useProfileStore()
    await expect(store.fetchProfile()).resolves.toBe(profile)
    await expect(store.saveProfile({} as never)).resolves.toMatchObject({ version: 3 })
    expect(store.current?.version).toBe(3)
    store.reset()
    expect(store.current).toBeNull()
  })

  it("lists, publishes and resets user-scoped resumes", async () => {
    vi.mocked(api.listResumes).mockResolvedValue({ items: [resume], page: 1, page_size: 20, total: 1 })
    vi.mocked(api.publishResume).mockResolvedValue(resume)
    const store = useResumesStore()
    await store.fetchResumes()
    await store.publishResume("Backend", 2)
    expect(store.resumes).toHaveLength(1)
    store.reset()
    expect(store.resumes).toEqual([])
  })

  it("keeps only confirmed facts in a publish preview", () => {
    const result = confirmedSnapshot({
      name: { value: "Alice", confirmation_status: "confirmed" },
      hidden: { value: "secret", confirmation_status: "unconfirmed" },
      skills: [
        { id: "one", name: { value: "Python", confirmation_status: "confirmed" } },
        { id: "two", name: { value: "Rust", confirmation_status: "rejected" } },
      ],
    })
    expect(result).toEqual({ name: "Alice", skills: [{ id: "one", name: "Python" }] })
    expect(hasSnapshotFacts(result)).toBe(true)
  })

  it("clones a reactive profile draft into a request payload", () => {
    const draft = reactive({
      basic_information: {
        display_name: { value: "Alice", confirmation_status: "confirmed" as const },
        current_location: { value: "Shanghai", confirmation_status: "confirmed" as const },
      },
      preferences: {
        target_locations: { value: [], confirmation_status: "unconfirmed" as const },
        accepts_remote: { value: false, confirmation_status: "unconfirmed" as const },
        target_roles: { value: [], confirmation_status: "unconfirmed" as const },
      },
      education: [], experiences: [], skills: [],
    })

    const payload = cloneProfileInput(draft)

    expect(payload).toEqual(draft)
    expect(payload).not.toBe(draft)
  })
})
