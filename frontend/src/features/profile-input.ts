import type { CandidateProfileInput } from "@/api/types"

export function cloneProfileInput(input: CandidateProfileInput): CandidateProfileInput {
  return JSON.parse(JSON.stringify(input)) as CandidateProfileInput
}
