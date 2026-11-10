<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { signIn } from '../auth'
import { errorText } from '../feedback'

const route = useRoute()
const router = useRouter()
const login = ref('')
const password = ref('')
const problem = ref('')
const busy = ref(false)

async function submit(): Promise<void> {
  if (busy.value) return
  busy.value = true
  problem.value = ''
  try {
    await signIn(login.value.trim(), password.value)
    await router.replace(typeof route.query.next === 'string' ? route.query.next : '/')
  } catch (error) {
    problem.value = errorText(error)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <form class="card auth-card" @submit.prevent="submit">
      <div>
        <p class="kicker">Лига игроков UFC</p>
        <h1>Вход</h1>
      </div>
      <label class="field">
        Логин
        <input v-model="login" name="username" autocomplete="username" required />
      </label>
      <label class="field">
        Пароль
        <input v-model="password" name="password" type="password" autocomplete="current-password" required />
      </label>
      <p v-if="problem" class="error-box small">{{ problem }}</p>
      <button class="btn primary" type="submit" :disabled="busy">Войти</button>
      <p class="small muted">Ещё нет аккаунта? <RouterLink class="link" to="/register">Зарегистрироваться</RouterLink></p>
    </form>
  </main>
</template>
