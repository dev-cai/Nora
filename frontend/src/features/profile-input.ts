import type { CandidateProfileInput } from "@/api/types"

export function cloneProfileInput(input: CandidateProfileInput): CandidateProfileInput {
  return JSON.parse(JSON.stringify(input)) as CandidateProfileInput
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function hasCandidateValue(value: unknown): boolean {
  if (typeof value === "string") return value.trim().length > 0
  if (Array.isArray(value)) return value.length > 0
  return typeof value === "number" || value === true
}

/** Confirm all non-empty facts from an imported draft in one user action. */
export function confirmImportedProfile(input: CandidateProfileInput): CandidateProfileInput {
  const confirmed = cloneProfileInput(input)

  function visit(value: unknown): void {
    if (Array.isArray(value)) {
      value.forEach(visit)
      return
    }
    if (!isRecord(value)) return
    if ("value" in value && "confirmation_status" in value) {
      if (hasCandidateValue(value.value)) value.confirmation_status = "confirmed"
      return
    }
    Object.values(value).forEach(visit)
  }

  visit(confirmed)
  return confirmed
}
