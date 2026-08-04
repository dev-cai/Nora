const baseUrl = process.env.NORA_WEB_URL || "http://localhost:5173"
const deadline = Date.now() + 30_000

async function fetchReady(path) {
  let lastError
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}${path}`)
      if (response.ok) return response
      lastError = new Error(`${path} returned ${response.status}`)
    } catch (error) {
      lastError = error
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error(`${path} was not ready within 30 seconds`, { cause: lastError })
}

const response = await fetchReady("/")
if (!response.ok) throw new Error(`Web returned ${response.status}`)
const html = await response.text()
if (!html.includes("Nora")) throw new Error("Web shell did not contain Nora")
const health = await fetchReady("/api/health")
if (!health.ok) throw new Error(`API proxy returned ${health.status}`)
const payload = await health.json()
if (payload.status !== "healthy") throw new Error(`Unexpected API health: ${JSON.stringify(payload)}`)
const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
const username = `smoke-${suffix}`
const password = "smoke-password-123"

async function jsonRequest(path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  })
  if (!response.ok) throw new Error(`${path} returned ${response.status}: ${await response.text()}`)
  return response.json()
}

await jsonRequest("/api/auth/register", {
  method: "POST",
  body: JSON.stringify({ username, email: `${username}@example.com`, password }),
})
const session = await jsonRequest("/api/auth/login", {
  method: "POST",
  body: JSON.stringify({ username, password }),
})
const authorization = { Authorization: `Bearer ${session.access_token}` }
const currentUser = await jsonRequest("/api/auth/me", { headers: authorization })
if (currentUser.username !== username) throw new Error("Authenticated user did not round-trip")
await jsonRequest("/api/job-postings", {
  method: "POST",
  headers: { ...authorization, "Idempotency-Key": `smoke-${suffix}` },
  body: JSON.stringify({ jd_text: "Nora integration smoke job", job_title: "Smoke Engineer", company_name: "Nora", location: "Remote", source_type: "manual" }),
})
await jsonRequest("/api/profile", {
  method: "PUT",
  headers: authorization,
  body: JSON.stringify({
    basic_information: { display_name: { value: "Smoke User" }, current_location: { value: "Remote" } },
    preferences: { target_locations: { value: ["Remote"] }, accepts_remote: { value: true }, target_roles: { value: ["Engineering"] } },
    education: [],
    experiences: [],
    skills: [],
  }),
})
console.log(`Web/API smoke passed: ${baseUrl}`)
