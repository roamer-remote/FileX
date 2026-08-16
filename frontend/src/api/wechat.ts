import api from './index'

export type WechatQrcodeSession = {
  state: string
  app_id: string
  redirect_uri: string
  mock_mode: boolean
  poll_token: string
}

export type WechatStatusResponse =
  | { status: 'pending' | 'invalid' }
  | { status: 'error'; message: string }
  | { status: 'need_register' }
  | { status: 'awaiting_bind_confirm'; wechat_nickname?: string }
  | {
      status: 'success'
      access_token: string
      user: {
        id: number
        username: string
        is_admin: boolean
        is_active: boolean
        created_at: string
        has_avatar: boolean
        wechat_bound: boolean
      }
    }

export function fetchWechatQrcode() {
  return api.get<WechatQrcodeSession>('/wechat/qrcode', { skipErrorToast: true })
}

export function fetchWechatBindQrcode() {
  return api.get<WechatQrcodeSession>('/wechat/bind-qrcode', { skipErrorToast: true })
}

export function fetchWechatStatus(state: string, pollToken?: string) {
  return api.get<WechatStatusResponse>(`/wechat/status/${encodeURIComponent(state)}`, {
    skipErrorToast: true,
    params: pollToken ? { poll_token: pollToken } : undefined,
  })
}

export function confirmWechatBind(state: string, pollToken?: string) {
  return api.post<Extract<WechatStatusResponse, { status: 'success' }>>('/wechat/confirm-bind', {
    state,
    poll_token: pollToken ?? undefined,
  })
}

export function triggerMockWechatCallback(state: string, scenario: 'need_register' | 'login' = 'need_register') {
  return api.get(`/wechat/mock-callback`, {
    params: { state, scenario },
    skipErrorToast: true,
  })
}
