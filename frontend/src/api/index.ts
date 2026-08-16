import axios from 'axios'
import { message } from 'antd'
import { resolveApiErrorDetailUnknown, isWorkspaceBackupTooLargePayload } from '@/lib/apiErrorMessage'
import i18n from '@/i18n'
import { dispatchLicenseInvalidEvent } from '@/api/license'

declare module 'axios' {
  interface AxiosRequestConfig {
    skipErrorToast?: boolean
    /** 401 时不清理存储、不跳转登录页（由调用方处理，如 ProtectedRoute 会话校验） */
    skipAuthRedirect?: boolean
  }
}

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// -------- 跨 storage 认证工具 ----------
// "记住我" 使用 localStorage（关闭浏览器后保留），否则使用 sessionStorage（当前会话）
const TOKEN_KEY = 'filex_token'
const USER_KEY = 'filex_user'

export function getStorageToken(): string | null {
  return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY)
}

export function getStorageUser(): string | null {
  return localStorage.getItem(USER_KEY) || sessionStorage.getItem(USER_KEY)
}

export function setStorageToken(token: string, remember: boolean): void {
  if (remember) {
    localStorage.setItem(TOKEN_KEY, token)
    sessionStorage.removeItem(TOKEN_KEY)
  } else {
    sessionStorage.setItem(TOKEN_KEY, token)
    localStorage.removeItem(TOKEN_KEY)
  }
}

export function setStorageUser(user: string, remember: boolean): void {
  if (remember) {
    localStorage.setItem(USER_KEY, user)
    sessionStorage.removeItem(USER_KEY)
  } else {
    sessionStorage.setItem(USER_KEY, user)
    localStorage.removeItem(USER_KEY)
  }
}

/** 当前 token 是否在 localStorage（与「记住我」一致），用于刷新用户信息时写回同一存储。 */
export function isAuthPersistedToLocalStorage(): boolean {
  return localStorage.getItem(TOKEN_KEY) !== null
}

export function isAuthEntryPath(pathname: string = window.location.pathname): boolean {
  return pathname === '/login' || pathname === '/register'
}

export function clearAuthStorage(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(USER_KEY)
}

/** 登录/注册请求不应附带旧 Bearer，避免干扰公开鉴权接口。 */
function isPublicAuthUrl(config: { url?: string } | undefined): boolean {
  const u = config?.url || ''
  return u.includes('/auth/login') || u.includes('/auth/register')
}

api.interceptors.request.use((config) => {
  const token = getStorageToken()
  if (token && !isPublicAuthUrl(config)) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export function isFormValidationError(err: unknown): boolean {
  return err != null && typeof err === 'object' && 'errorFields' in err
}

export function formatApiError(err: unknown): string {
  const e = err as {
    response?: { data?: { detail?: unknown }; status?: number }
    message?: string
    code?: string
    workspaceBackupDetail?: unknown
  }
  if (isWorkspaceBackupTooLargePayload(e.workspaceBackupDetail)) {
    const resolved = resolveApiErrorDetailUnknown(e.workspaceBackupDetail)
    if (resolved) return resolved
  }
  const payload = e.response?.data as { detail?: unknown; code?: string } | undefined
  const d = payload?.detail
  if (d && typeof d === 'object' && isWorkspaceBackupTooLargePayload(d)) {
    const resolved = resolveApiErrorDetailUnknown(d)
    if (resolved) return resolved
  }
  if (typeof d === 'string') {
    const resolved = resolveApiErrorDetailUnknown(d)
    if (resolved) return resolved
  }
  if (Array.isArray(d)) {
    const parts = d.map((x: unknown) => {
      if (typeof x === 'string') {
        return resolveApiErrorDetailUnknown(x) ?? x
      }
      if (x && typeof x === 'object' && 'msg' in x) return String((x as { msg: string }).msg)
      return ''
    }).filter(Boolean)
    if (parts.length) return parts.join('；')
  }
  if (d && typeof d === 'object' && d !== null && 'msg' in d) {
    return String((d as { msg: string }).msg)
  }
  if (!e.response && (e.message === 'Network Error' || e.code === 'ECONNABORTED')) {
    return i18n.t('api.networkError')
  }
  if (typeof e.message === 'string') {
    const resolved = resolveApiErrorDetailUnknown(e.message)
    if (resolved) return resolved
  }
  return e.message || i18n.t('api.requestFailed')
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const onAuthEntry = isAuthEntryPath()
    const suppress401Toast = error.response?.status === 401 && onAuthEntry
    if (error.response?.status === 403) {
      const data = error.response.data as { code?: string; detail?: string } | undefined
      const code = data?.code
      if (code === 'license_expired' || code === 'license_invalid') {
        dispatchLicenseInvalidEvent()
        if (!error.config?.skipErrorToast) {
          message.error(typeof data?.detail === 'string' ? data.detail : i18n.t('license.expired'))
        }
        return Promise.reject(error)
      }
    }
    if (!error.config?.skipErrorToast && !suppress401Toast) {
      message.error(formatApiError(error))
    }
    if (error.response?.status === 401) {
      // 登录/注册失败也会返回 401，不得整页跳转，否则打断界面与 Toast
      const skipRedirect = error.config?.skipAuthRedirect === true
      if (!isPublicAuthUrl(error.config) && !skipRedirect) {
        clearAuthStorage()
        if (!onAuthEntry) {
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(error)
  },
)

export default api
