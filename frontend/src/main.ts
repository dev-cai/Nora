import { createPinia } from "pinia"
import { createApp } from "vue"

import App from "./App.vue"
import { setUnauthorizedHandler } from "./api/client"
import { createAppRouter } from "./router"
import { useAuthStore } from "./stores/auth"
import "./styles.css"

const app = createApp(App)
const pinia = createPinia()
const router = createAppRouter(pinia)
const auth = useAuthStore(pinia)

setUnauthorizedHandler(() => {
  auth.logout()
  void router.push({ name: "login" })
})

app.use(pinia)
app.use(router)
app.mount("#app")
