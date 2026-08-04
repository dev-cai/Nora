import { createPinia } from "pinia"
import { createApp } from "vue"

import App from "./App.vue"
import { setUnauthorizedHandler } from "./api/client"
import { createAppRouter } from "./router"
import { useAuthStore } from "./stores/auth"
import { useJobsStore } from "./stores/jobs"
import "./styles.css"

const app = createApp(App)
const pinia = createPinia()
const router = createAppRouter(pinia)
const auth = useAuthStore(pinia)
const jobs = useJobsStore(pinia)

setUnauthorizedHandler(() => {
  auth.logout()
  jobs.reset()
  void router.push({ name: "login" })
})

app.use(pinia)
app.use(router)
app.mount("#app")
