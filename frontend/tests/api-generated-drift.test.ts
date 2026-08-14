import { execFileSync } from "node:child_process"
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"

const checker = path.resolve("scripts/check-api-drift.mjs")

function run(command: string, args: string[], cwd: string): void {
  execFileSync(command, args, { cwd, stdio: "pipe" })
}

describe("generated API drift gate", () => {
  it("accepts the committed pair and rejects modified or untracked output", () => {
    const repository = mkdtempSync(path.join(tmpdir(), "nora-api-drift-"))
    const generated = path.join(repository, "generated")
    try {
      run("git", ["init", "--quiet"], repository)
      run("git", ["config", "user.email", "contract-test@example.com"], repository)
      run("git", ["config", "user.name", "Contract Test"], repository)
      mkdirSync(generated)
      writeFileSync(path.join(generated, "openapi.json"), "{}\n")
      writeFileSync(path.join(generated, "schema.d.ts"), "// generated\n")
      run("git", ["add", "generated"], repository)
      run("git", ["commit", "--quiet", "-m", "contract fixture"], repository)

      expect(() => run(process.execPath, [checker, repository, "generated"], repository)).not.toThrow()

      writeFileSync(path.join(generated, "openapi.json"), '{"drift":true}\n')
      expect(() => run(process.execPath, [checker, repository, "generated"], repository)).toThrow()

      run("git", ["restore", "generated/openapi.json"], repository)
      writeFileSync(path.join(generated, "unexpected.json"), "{}\n")
      expect(() => run(process.execPath, [checker, repository, "generated"], repository)).toThrow()

      run("git", ["add", "generated/unexpected.json"], repository)
      run("git", ["commit", "--quiet", "-m", "unexpected generated file"], repository)
      expect(() => run(process.execPath, [checker, repository, "generated"], repository)).toThrow()
    } finally {
      rmSync(repository, { recursive: true, force: true })
    }
  })
})
