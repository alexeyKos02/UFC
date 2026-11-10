import { reactive, ref, type Ref } from 'vue'
import { ApiError } from './api'

export interface Toast {
  id: number
  text: string
  kind: 'ok' | 'error'
}

export const toasts = reactive<Toast[]>([])
let nextId = 1

export function notify(text: string, kind: Toast['kind'] = 'ok'): void {
  const id = nextId++
  toasts.push({ id, text, kind })
  window.setTimeout(() => {
    const index = toasts.findIndex((toast) => toast.id === id)
    if (index >= 0) toasts.splice(index, 1)
  }, kind === 'error' ? 7000 : 3500)
}

export function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Что-то пошло не так. Повторите попытку'
}

/** Кнопка с таким действием не сработает повторно, пока идёт запрос. */
export function useAction() {
  const busy = ref(false)
  async function run<T>(action: () => Promise<T>, success?: string): Promise<T | undefined> {
    if (busy.value) return undefined
    busy.value = true
    try {
      const result = await action()
      if (success) notify(success)
      return result
    } catch (error) {
      notify(errorText(error), 'error')
      return undefined
    } finally {
      busy.value = false
    }
  }
  return { busy, run }
}

export function useLoad<T>(loader: () => Promise<T>) {
  const data = ref<T | null>(null) as Ref<T | null>
  const error = ref('')
  const loading = ref(true)
  async function reload(): Promise<void> {
    try {
      data.value = await loader()
      error.value = ''
    } catch (failure) {
      error.value = errorText(failure)
    } finally {
      loading.value = false
    }
  }
  void reload()
  return { data, error, loading, reload }
}
