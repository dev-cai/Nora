import type { ResumeVersion, TemplateDefinition, VariantBlock } from "@/api/types"

const labels: Record<string, string> = {
  display_name: "姓名",
  current_location: "所在地",
  school: "学校",
  degree: "学历",
  major: "专业",
  company: "公司",
  job_title: "职位",
  start_date: "开始时间",
  end_date: "结束时间",
  responsibilities: "职责",
  achievements: "成果",
  name: "技能",
  proficiency: "熟练度",
  years: "年限",
}

export function resumeBlocks(resume: ResumeVersion): VariantBlock[] {
  const blocks: VariantBlock[] = []
  walk(resume.content, "", blocks)
  return blocks
}

function walk(value: unknown, prefix: string, blocks: VariantBlock[]): void {
  if (Array.isArray(value)) {
    if (value.every((item) => item === null || ["string", "number", "boolean"].includes(typeof item))) {
      const text = value.filter((item) => item !== null && item !== "").join("、")
      if (text) pushBlock(prefix, text, blocks)
      return
    }
    for (const item of value) walk(item, prefix, blocks)
    return
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>
    const itemId = typeof record.id === "string" ? record.id : null
    for (const [key, child] of Object.entries(record)) {
      if (key === "id") continue
      const path = itemId ? `${prefix}.${itemId}.${key}` : prefix ? `${prefix}.${key}` : key
      walk(child, path, blocks)
    }
    return
  }
  if (value === null || value === undefined || value === "") return
  pushBlock(prefix, String(value), blocks)
}

function pushBlock(prefix: string, value: string, blocks: VariantBlock[]): void {
  blocks.push({
    source_path: prefix,
    label: labels[prefix.split(".").at(-1) || ""] || prefix,
    value,
  })
}

export function templateAllows(template: TemplateDefinition, path: string): boolean {
  return template.allowed_fields.some((pattern) => pathMatches(pattern, path))
}

export function templateRequires(template: TemplateDefinition, path: string): boolean {
  return template.required_fields.some((pattern) => pathMatches(pattern, path))
}

function pathMatches(pattern: string, path: string): boolean {
  const expected = pattern.split(".")
  const actual = path.split(".")
  return expected.length === actual.length && expected.every((part, index) => part === "*" || part === actual[index])
}
