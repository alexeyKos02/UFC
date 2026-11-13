<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { currentUser, isStaff, signOut } from './auth'
import TourGuide from './components/TourGuide.vue'
import { toasts, useAction } from './feedback'
import { onboardingVisible, openOnboarding } from './onboarding'
import type { MyFights } from './types'

const route = useRoute()
const router = useRouter()
const menuOpen = ref(false)
const toConfirm = ref(0)
const { run } = useAction()

const showChrome = computed(() => Boolean(currentUser.value) && !route.meta.public)

async function refreshCounter(): Promise<void> {
  if (!currentUser.value) return
  try {
    const mine = await api.get<MyFights>('/fights/mine')
    // В счётчике и бои на подтверждение, и мои бои без итога, из-за которых ждут другие.
    toConfirm.value = new Set([...mine.to_confirm, ...mine.blocking.map((item) => item.fight)].map((fight) => fight.id)).size
  } catch {
    toConfirm.value = 0
  }
}

watch(
  () => route.fullPath,
  () => {
    menuOpen.value = false
    void refreshCounter()
  },
  { immediate: true },
)
watch(currentUser, () => void refreshCounter())

async function logout(): Promise<void> {
  await run(signOut)
  void router.push('/login')
}
</script>

<template>
  <header v-if="showChrome" class="header">
    <div class="container header-inner">
      <RouterLink to="/" class="brand">
        <svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
          <path fill="#e23a4e" d="M10 2h12l8 8v12l-8 8H10l-8-8V10z" />
          <path fill="#fff" d="M11 9h10v3h-7v3h6v3h-6v5h-3z" />
        </svg>
        Лига UFC
      </RouterLink>
      <button
        class="btn sm menu-toggle"
        data-tour="nav-my-fights"
        :aria-expanded="menuOpen"
        aria-controls="main-nav"
        @click="menuOpen = !menuOpen"
      >
        Меню<span v-if="toConfirm" class="counter">{{ toConfirm }}</span>
      </button>
      <nav id="main-nav" class="nav" :class="{ open: menuOpen }" aria-label="Основная навигация">
        <RouterLink to="/" active-class="" exact-active-class="router-link-active">Главная</RouterLink>
        <RouterLink to="/tournaments">Турниры</RouterLink>
        <RouterLink to="/league">Игроки и рейтинг</RouterLink>
        <RouterLink to="/fights">Бои</RouterLink>
        <RouterLink to="/my-fights" data-tour="nav-my-fights">
          Мои бои<span v-if="toConfirm" class="counter" :aria-label="`На подтверждение: ${toConfirm}`">{{ toConfirm }}</span>
        </RouterLink>
        <RouterLink to="/belts">Пояса</RouterLink>
        <RouterLink v-if="isStaff" to="/admin">Админка</RouterLink>
        <a class="nav-end nav-help" href="#" title="Как это работает" @click.prevent="openOnboarding">
          <span class="help-mark" aria-hidden="true">?</span><span class="help-text">Как это работает</span>
        </a>
        <RouterLink class="nav-me" :to="`/players/${currentUser?.id}`">{{ currentUser?.nickname }}</RouterLink>
        <a href="#" @click.prevent="logout">Выйти</a>
      </nav>
    </div>
  </header>

  <RouterView :key="route.path" />

  <TourGuide v-if="showChrome && onboardingVisible" />

  <div class="toasts" role="status" aria-live="polite">
    <div v-for="toast in toasts" :key="toast.id" class="toast" :class="toast.kind">{{ toast.text }}</div>
  </div>
</template>
