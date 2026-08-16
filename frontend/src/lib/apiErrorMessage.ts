import type { TFunction } from 'i18next'
import i18n from '@/i18n'
import { formatByteSize } from '@/lib/formatByteSize'

export type WorkspaceBackupTooLargePayload = {
  code: string
  total_bytes: number
  max_bytes: number
  file_count?: number
}

export function isWorkspaceBackupTooLargePayload(value: unknown): value is WorkspaceBackupTooLargePayload {
  if (!value || typeof value !== 'object') return false
  const v = value as Record<string, unknown>
  return (
    v.code === 'workspaceBackup.tooLarge' &&
    typeof v.total_bytes === 'number' &&
    Number.isFinite(v.total_bytes) &&
    typeof v.max_bytes === 'number' &&
    Number.isFinite(v.max_bytes)
  )
}

export function resolveWorkspaceBackupTooLargeMessage(
  payload: WorkspaceBackupTooLargePayload,
  t?: TFunction,
): string {
  const translate = t ?? i18n.t.bind(i18n)
  if (payload.file_count != null && Number.isFinite(payload.file_count)) {
    return translate('workspaceBackup.errors.tooLargeWithSizesAndCount', {
      count: payload.file_count,
      current: formatByteSize(payload.total_bytes),
      limit: formatByteSize(payload.max_bytes),
    })
  }
  return translate('workspaceBackup.errors.tooLargeWithSizes', {
    current: formatByteSize(payload.total_bytes),
    limit: formatByteSize(payload.max_bytes),
  })
}

/** 后端 detail 稳定错误码或遗留中文文案 → i18n key */
const API_DETAIL_TO_KEY: Record<string, string> = {
  'folder.root_create_forbidden': 'folders.errors.rootCreateForbidden',
  'folder.manage_forbidden': 'folders.errors.manageForbidden',
  'folder.parent_not_found': 'folders.errors.parentNotFound',
  'folder.not_found': 'folders.errors.notFound',
  'folder.depth_exceeded': 'folders.errors.depthExceeded',
  'folder.move_to_descendant': 'folders.errors.moveToDescendant',
  'workspaceBackup.sharedNotSupported': 'workspaceBackup.errors.sharedNotSupported',
  'workspaceBackup.notOwner': 'workspaceBackup.errors.notOwner',
  'workspaceBackup.tooLarge': 'workspaceBackup.errors.tooLarge',
  无权创建根级目录: 'folders.errors.rootCreateForbidden',
  无权管理该空间的目录结构: 'folders.errors.manageForbidden',
  父文件夹不存在: 'folders.errors.parentNotFound',
  文件夹不存在: 'folders.errors.notFound',
  '目录层级不能超过 10 级': 'folders.errors.depthExceeded',
}

/** 将 API 业务错误 detail 转为当前语言文案 */
export function resolveApiErrorDetail(detail: string, t?: TFunction): string {
  const trimmed = detail.trim()
  if (!trimmed) return t ? t('api.requestFailed') : i18n.t('api.requestFailed')
  const key = API_DETAIL_TO_KEY[trimmed]
  if (key) {
    return t ? t(key) : i18n.t(key)
  }
  return trimmed
}

export function resolveApiErrorDetailUnknown(detail: unknown, t?: TFunction): string | null {
  if (isWorkspaceBackupTooLargePayload(detail)) {
    return resolveWorkspaceBackupTooLargeMessage(detail, t)
  }
  if (typeof detail !== 'string') return null
  return resolveApiErrorDetail(detail, t)
}
