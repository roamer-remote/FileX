import api from './index'

export type RuntimeMeta = {
  filex_env: string | null
}

export function getRuntimeMeta() {
  return api.get<RuntimeMeta>('/meta/runtime', { skipErrorToast: true })
}
