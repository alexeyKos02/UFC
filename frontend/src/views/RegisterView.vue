<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { signUp } from '../auth'
import { errorText } from '../feedback'

const router = useRouter()
const login = ref('')
const password = ref('')
const repeat = ref('')
const problem = ref('')
const busy = ref(false)

async function submit(): Promise<void> {
  if (busy.value) return
  if (password.value !== repeat.value) {
    problem.value = 'Пароли не совпадают'
    return
  }
  busy.value = true
  problem.value = ''
  try {
    await signUp(login.value.trim(), password.value)
    await router.replace('/')
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
        <h1>Регистрация</h1>
      </div>
      <label class="field">
        Логин
        <input v-model="login" name="username" autocomplete="username" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_.\-]+" />
        <span class="small muted">Латиница, цифры и символы _ . -, от 3 до 32 знаков</span>
      </label>
      <label class="field">
        Пароль
        <input v-model="password" name="password" type="password" autocomplete="new-password" required minlength="8" maxlength="128" />
        <span class="small muted">Минимум 8 символов</span>
      </label>
      <label class="field">
        Повторите пароль
        <input v-model="repeat" type="password" autocomplete="new-password" required />
      </label>
      <p v-if="problem" class="error-box small">{{ problem }}</p>
      <button class="btn primary" type="submit" :disabled="busy">Создать аккаунт</button>
      <p class="small muted">Уже есть аккаунт? <RouterLink class="link" to="/login">Войти</RouterLink></p>
    </form>
  </main>
</template>
