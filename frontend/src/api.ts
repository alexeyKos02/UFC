export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

let onSessionLost: () => void = () => {}

export function setSessionLostHandler(handler: () => void): void {
  onSessionLost = handler
}

// Отказ на этих адресах не значит, что открытая сессия потеряна.
const NO_SESSION_PATHS = ['/auth/login', '/auth/register', '/auth/me']

async function request<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: 'same-origin',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: form ?? (body === undefined ? undefined : JSON.stringify(body)),
    })
  } catch {
    throw new ApiError(0, 'Нет связи с сервером. Проверьте подключение и повторите')
  }
  if (response.status === 204) {
    return undefined as T
  }
  const text = await response.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }
  if (!response.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail
    const message = typeof detail === 'string' ? detail : 'Сервер не смог выполнить запрос'
    const sessionLost =
      response.status === 401 || (response.status === 403 && message === 'Учётная запись заблокирована')
    if (sessionLost && !NO_SESSION_PATHS.includes(path)) {
      onSessionLost()
    }
    throw new ApiError(response.status, message)
  }
  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body: unknown = {}) => request<T>('POST', path, body),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
  upload: <T>(path: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<T>('POST', path, undefined, form)
  },
}
