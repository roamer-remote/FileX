import type { ApiKeyItem } from '@/api/apiKeys'

export function hasActiveApiKey(keys: ApiKeyItem[]): boolean {
  return keys.some((key) => key.is_active)
}
