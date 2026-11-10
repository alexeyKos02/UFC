import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/oswald/500.css'
import '@fontsource/oswald/600.css'
import './styles.css'

import { createApp } from 'vue'
import App from './App.vue'
import { setSessionLostHandler } from './api'
import { currentUser } from './auth'
import { router } from './router'

setSessionLostHandler(() => {
  currentUser.value = null
  if (!router.currentRoute.value.meta.public) {
    void router.push('/login')
  }
})

createApp(App).use(router).mount('#app')
