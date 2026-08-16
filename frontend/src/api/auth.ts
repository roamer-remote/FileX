import type { AxiosRequestConfig } from 'axios'
import api from './index'

export interface LoginParams {
  username: string
  password: string
  wechat_state?: string | null
}

export function login(params: LoginParams) {
  return api.post('/auth/login', params, { skipErrorToast: true })
}

/** 由页面自行提示成功/失败时使用 skipErrorToast */
export function register(params: LoginParams) {
  return api.post('/auth/register', params, { skipErrorToast: true })
}

export function changePassword(params: { current_password: string; new_password: string }) {
  return api.post('/auth/change-password', params, { skipErrorToast: true })
}

export function getMe(config?: AxiosRequestConfig) {
  return api.get('/auth/me', config)
}

export function uploadAvatar(file: File, config?: AxiosRequestConfig) {
  const form = new FormData()
  form.append('file', file)
  return api.post('/auth/avatar', form, {
    ...config,
  })
}

export function deleteAvatar(config?: AxiosRequestConfig) {
  return api.delete('/auth/avatar', config)
}

export type FetchAvatarBlobConfig = AxiosRequestConfig & { cacheBust?: number }

/** 当前用户头像二进制；无头像时返回 null（不弹全局错误）。 */
export async function fetchAvatarBlob(config?: FetchAvatarBlobConfig): Promise<Blob | null> {
  const { cacheBust, params, ...rest } = config ?? {}
  try {
    const res = await api.get('/auth/avatar', {
      ...rest,
      params: cacheBust != null ? { ...(params as object), _v: cacheBust } : params,
      responseType: 'blob',
      validateStatus: (s) => (s >= 200 && s < 300) || s === 404,
    })
    if (res.status === 404) return null
    return res.data as Blob
  } catch {
    return null
  }
}
