import { create } from 'zustand'
import { login as loginApi, register as registerApi, getMe, type LoginParams } from '@/api/auth'
import {
  getStorageToken,
  getStorageUser,
  setStorageToken,
  setStorageUser,
  clearAuthStorage,
  isAuthPersistedToLocalStorage,
} from '@/api/index'
import { bootstrapUiStateAfterAuth, resetUiStateSync, syncLoginPrefsToServer } from '@/lib/uiStateSync'
import { teardownKbVoiceNotify } from '@/lib/kbVoiceNotifyLifecycle'

export interface User {
  id: number
  username: string
  is_admin: boolean
  is_active: boolean
  created_at: string
  has_avatar?: boolean
  wechat_bound?: boolean
}


function normalizeUser(raw: Partial<User>): User {
  return {
    ...(raw as User),
    is_active: raw.is_active ?? true,
    is_admin: raw.is_admin === true,
  }
}

type AuthState = {
  user: User | null
  token: string | null
  avatarRevision: number
  loadFromStorage: () => void
  login: (params: LoginParams, rememberMe?: boolean) => Promise<void>
  register: (params: LoginParams, rememberMe?: boolean) => Promise<void>
  completeWechatAuth: (accessToken: string, rememberMe?: boolean) => Promise<void>
  loginWithWechatToken: (accessToken: string, rememberMe?: boolean) => Promise<void>
  logout: () => void
  setUser: (user: User) => void
  refreshUser: () => Promise<void>
  bumpAvatarRevision: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  avatarRevision: 0,

  loadFromStorage: () => {
    const storedToken = getStorageToken()
    const storedUser = getStorageUser()
    if (storedToken && storedUser) {
      try {
        const parsed = JSON.parse(storedUser) as Partial<User>
        set({
          token: storedToken,
          user: normalizeUser(parsed),
        })
      } catch {
        clearAuthStorage()
        set({ token: null, user: null })
      }
    } else {
      set({ token: storedToken, user: null })
    }
  },

  login: async (params: LoginParams, rememberMe = true) => {
    const loginRes = await loginApi(params)
    const accessToken = loginRes.data.access_token as string
    setStorageToken(accessToken, rememberMe)
    set({ token: accessToken })
    const meRes = await getMe()
    const user = normalizeUser(meRes.data as User)
    setStorageUser(JSON.stringify(user), rememberMe)
    set({ user })
    await bootstrapUiStateAfterAuth()
    await syncLoginPrefsToServer(rememberMe, 'password')
  },


  completeWechatAuth: async (accessToken: string, rememberMe = true) => {
    setStorageToken(accessToken, rememberMe)
    set({ token: accessToken })
    const meRes = await getMe({ skipErrorToast: true })
    const user = normalizeUser(meRes.data as User)
    setStorageUser(JSON.stringify(user), rememberMe)
    set({ user })
    await bootstrapUiStateAfterAuth()
    await syncLoginPrefsToServer(rememberMe, 'wechat')
  },

  register: async (params: LoginParams, rememberMe = true) => {
    const res = await registerApi(params)
    const accessToken = res.data.access_token as string
    setStorageToken(accessToken, rememberMe)
    set({ token: accessToken })
    try {
      const meRes = await getMe({ skipErrorToast: true })
      const user = normalizeUser(meRes.data as User)
      setStorageUser(JSON.stringify(user), rememberMe)
      set({ user })
      await bootstrapUiStateAfterAuth()
      await syncLoginPrefsToServer(rememberMe, 'password')
    } catch (err) {
      clearAuthStorage()
      set({ token: null, user: null })
      throw err
    }
  },

  logout: () => {
    teardownKbVoiceNotify()
    resetUiStateSync()
    clearAuthStorage()
    set({ token: null, user: null })
  },

  setUser: (user: User) => {
    const normalized = normalizeUser(user)
    const remember = isAuthPersistedToLocalStorage()
    setStorageUser(JSON.stringify(normalized), remember)
    set({ user: normalized })
  },

  loginWithWechatToken: async (accessToken: string, rememberMe = true) => {
    setStorageToken(accessToken, rememberMe)
    set({ token: accessToken })
    const meRes = await getMe({ skipErrorToast: true })
    const user = normalizeUser(meRes.data as User)
    setStorageUser(JSON.stringify(user), rememberMe)
    set({ user })
    await bootstrapUiStateAfterAuth()
    await syncLoginPrefsToServer(rememberMe, 'wechat')
  },

  refreshUser: async () => {
    const meRes = await getMe({ skipErrorToast: true })
    const user = normalizeUser(meRes.data as User)
    const remember = isAuthPersistedToLocalStorage()
    setStorageUser(JSON.stringify(user), remember)
    set({ user })
  },

  bumpAvatarRevision: () => {
    set((s) => ({ avatarRevision: s.avatarRevision + 1 }))
  },
}))
