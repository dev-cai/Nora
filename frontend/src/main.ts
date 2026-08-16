import { createPinia } from "pinia"
import { createApp } from "vue"

import App from "./App.vue"
import { setUnauthorizedHandler } from "./api/client"
import { createAppRouter } from "./router"
import { useAuthStore } from "./stores/auth"
import { useAnalysisStore } from "./stores/analysis"
import { useJobsStore } from "./stores/jobs"
import { useInterviewsStore } from "./stores/interviews"
import "./styles.css"

const app = createApp(App)
const pinia = createPinia()
const router = createAppRouter(pinia)
const auth = useAuthStore(pinia)
const analysis = useAnalysisStore(pinia)
const jobs = useJobsStore(pinia)
const interviews = useInterviewsStore(pinia)

setUnauthorizedHandler(() => {
  auth.logout()
  jobs.reset()
  interviews.reset()
  analysis.reset()
  void router.push({ name: "login" })
})

app.use(pinia)
app.use(router)
app.mount("#app")
void auth.restoreSession()
