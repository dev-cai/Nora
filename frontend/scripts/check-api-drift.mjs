import { spawnSync } from "node:child_process"
import console from "node:console"
import path from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"

const EXPECTED_FILES = ["openapi.json", "schema.d.ts"]

function git(repositoryRoot, args) {
  return spawnSync("git", args, {
    cwd: repositoryRoot,
    encoding: "utf8",
  })
}

function commandFailure(command, result) {
  if (result.error) {
    return `${command}: ${result.error.message}`
  }
  return `${command}: ${result.stderr.trim() || result.stdout.trim() || `exit ${result.status}`}`
}

export function findApiDrift(repositoryRoot, generatedDirectory) {
  const relativeDirectory = path.relative(repositoryRoot, generatedDirectory).split(path.sep).join("/")
  const expectedPaths = EXPECTED_FILES.map((file) => `${relativeDirectory}/${file}`)
  const failures = []

  const tracked = git(repositoryRoot, ["ls-files", "--", relativeDirectory])
  if (tracked.status !== 0) {
    failures.push(commandFailure("generated API tracked files could not be inspected", tracked))
  } else {
    const trackedPaths = tracked.stdout.trim().split("\n").filter(Boolean).sort()
    if (JSON.stringify(trackedPaths) !== JSON.stringify(expectedPaths.sort())) {
      failures.push(
        `generated API tracked files must be exactly:\n${expectedPaths.join("\n")}`,
      )
    }
  }

  const diff = git(repositoryRoot, ["diff", "--exit-code", "--", relativeDirectory])
  if (diff.status !== 0) {
    failures.push(commandFailure("generated API files differ from the committed contract", diff))
  }

  const status = git(repositoryRoot, [
    "status",
    "--porcelain=v1",
    "--untracked-files=all",
    "--",
    relativeDirectory,
  ])
  if (status.status !== 0) {
    failures.push(commandFailure("generated API status could not be inspected", status))
  } else if (status.stdout.trim()) {
    failures.push(`generated API directory is not clean:\n${status.stdout.trim()}`)
  }

  return failures
}

function main() {
  const scriptDirectory = path.dirname(fileURLToPath(import.meta.url))
  const repositoryRoot = path.resolve(process.argv[2] || path.join(scriptDirectory, "..", ".."))
  const generatedDirectory = path.resolve(
    repositoryRoot,
    process.argv[3] || "frontend/src/api/generated",
  )
  const failures = findApiDrift(repositoryRoot, generatedDirectory)
  if (failures.length) {
    console.error(failures.join("\n"))
    process.exitCode = 1
    return
  }
  console.log("Generated OpenAPI contract is current.")
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : ""
if (invokedPath === fileURLToPath(import.meta.url)) {
  main()
}
