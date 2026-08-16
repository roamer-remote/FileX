import { wsBaseUrl } from '@/utils/wsClient'

export const WS_AUTH_MESSAGE_TYPE = 'auth' as const

export function wsApiUrl(path: string): string {
  return `${wsBaseUrl()}${path}`
}

/** 首帧鉴权 JSON；避免 JWT 出现在 URL 查询串（日志/Referer 泄露）。 */
export function wsAuthFrame(token: string): string {
  return JSON.stringify({ type: WS_AUTH_MESSAGE_TYPE, token })
}
