import { computed, ref } from 'vue'
import { api } from './api'
import { currentUser, setAccount } from './auth'
import type { Account } from './types'

/** Открыто вручную из меню («Как это работает»). */
const openedByUser = ref(false)
/** Закрыто в этой вкладке: не показываем снова, даже если сервер не успел сохранить отметку. */
const dismissed = ref(false)

export const onboardingVisible = computed(
  () => openedByUser.value || (Boolean(currentUser.value) && currentUser.value?.onboarded === false && !dismissed.value),
)

export function openOnboarding(): void {
  openedByUser.value = true
}

export async function closeOnboarding(): Promise<void> {
  openedByUser.value = false
  dismissed.value = true
  if (currentUser.value && !currentUser.value.onboarded) {
    try {
      setAccount(await api.post<Account>('/me/onboarding'))
    } catch {
      // Не страшно: знакомство покажется ещё раз при следующем входе.
    }
  }
}
