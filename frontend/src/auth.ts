import { computed, ref } from 'vue'
import { ApiError, api } from './api'
import type { Account } from './types'

export const currentUser = ref<Account | null>(null)
export const isStaff = computed(() => currentUser.value?.role === 'admin' || currentUser.value?.role === 'owner')
export const isOwner = computed(() => currentUser.value?.role === 'owner')

let restored: Promise<void> | null = null

export function restoreSession(): Promise<void> {
  restored ??= api
    .get<Account>('/auth/me')
    .then((user) => {
      currentUser.value = user
    })
    .catch((error: unknown) => {
      if (!(error instanceof ApiError)) throw error
      currentUser.value = null
    })
  return restored
}

export async function signIn(login: string, password: string): Promise<void> {
  currentUser.value = await api.post<Account>('/auth/login', { login, password })
}

export async function signUp(login: string, password: string): Promise<void> {
  currentUser.value = await api.post<Account>('/auth/register', { login, password })
}

export async function signOut(): Promise<void> {
  await api.post('/auth/logout')
  currentUser.value = null
}

export function setAccount(account: Account): void {
  currentUser.value = account
}
