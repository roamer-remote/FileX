import api from './index'

export interface ApiKeyItem {
  id: number
  name: string
  prefix: string
  created_at: string
  last_used_at: string | null
  is_active: boolean
  can_reveal: boolean
}

export interface ApiKeyCreateResponse {
  id: number
  name: string
  prefix: string
  plain_text_key: string
  created_at: string
}

export function getApiKeys() {
  return api.get<ApiKeyItem[]>('/api-keys')
}

export function createApiKey(name: string) {
  return api.post<ApiKeyCreateResponse>('/api-keys', { name })
}

export function patchApiKey(id: number, body: { is_active: boolean }) {
  return api.patch<ApiKeyItem>(`/api-keys/${id}`, body)
}

export function deleteApiKey(id: number) {
  return api.delete(`/api-keys/${id}`)
}

export function revealApiKey(id: number, options?: { preview?: boolean }) {
  const body = options?.preview ? { preview: true } : {}
  return api.post<{ plain_text_key: string }>(`/api-keys/${id}/reveal`, body)
}
