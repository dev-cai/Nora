import type { ProfileFact } from "@/api/types"

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function filterConfirmed(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value
      .map(filterConfirmed)
      .filter((item) => item !== undefined && (!isRecord(item) || Object.keys(item).length > 1))
  }
  if (!isRecord(value)) return value
  if ("confirmation_status" in value && "value" in value) {
    return (value as unknown as ProfileFact<unknown>).confirmation_status === "confirmed"
      ? value.value
      : undefined
  }
  const output: Record<string, unknown> = {}
  for (const [key, item] of Object.entries(value)) {
    if (key === "id") {
      output[key] = item
      continue
    }
    const filtered = filterConfirmed(item)
    if (filtered !== undefined && (!isRecord(filtered) || Object.keys(filtered).length > 0)) {
      output[key] = filtered
    }
  }
  return output
}

export function confirmedSnapshot(content: unknown): Record<string, unknown> {
  const filtered = filterConfirmed(content)
  return isRecord(filtered) ? filtered : {}
}

export function hasSnapshotFacts(content: Record<string, unknown>): boolean {
  return Object.values(content).some((value) =>
    Array.isArray(value) ? value.length > 0 : isRecord(value) && Object.keys(value).length > 0,
  )
}
