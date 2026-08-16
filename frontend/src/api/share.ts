import type { AxiosRequestConfig } from 'axios'
import api from './index'

export interface ShareParams {
  file_id: number
  expires_in_hours?: number
  password?: string
  max_downloads?: number
}

export interface ShareInfo {
  id: number
  token: string
  file_id: number
  file_name: string
  file_size: number
  mime_type: string
  expires_at: string | null
  has_password: boolean
  max_downloads: number | null
  download_count: number
  created_at: string
}

export function createShare(params: ShareParams, config?: AxiosRequestConfig) {
  return api.post<{ token: string; url: string }>('/share', params, config)
}

export function getShareInfo(token: string) {
  return api.get<ShareInfo>(`/share/${token}`)
}

export function verifySharePassword(token: string, password: string) {
  return api.post(`/share/${token}/verify`, { password }, { skipErrorToast: true })
}

export function getShareDownloadUrl(token: string): string {
  return `/api/share/${token}/download`
}
