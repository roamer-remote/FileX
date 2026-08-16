import { getStorageToken } from './index'
import { parseContentDispositionFilename } from './files'
import { isWorkspaceBackupTooLargePayload } from '@/lib/apiErrorMessage'

export type WorkspaceBackupFetchError = Error & {
  workspaceBackupDetail?: unknown
}

async function readErrorDetail(res: Response): Promise<never> {
  try {
    const body = (await res.json()) as { detail?: unknown }
    const detail = body.detail
    if (isWorkspaceBackupTooLargePayload(detail)) {
      const err = new Error(detail.code) as WorkspaceBackupFetchError
      err.workspaceBackupDetail = detail
      throw err
    }
    if (typeof detail === 'string') throw new Error(detail)
    if (detail != null) throw new Error(String(detail))
  } catch (err) {
    if (err instanceof Error) throw err
  }
  throw new Error(`HTTP ${res.status}`)
}

/** 下载个人空间整包 ZIP；失败时 throw Error(detail) 供 formatApiError 解析。 */
export async function downloadWorkspaceBackup(
  workspaceId: number,
  fallbackFilename: string,
): Promise<void> {
  const token = getStorageToken()
  const res = await fetch(`/api/workspaces/${workspaceId}/backup`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    await readErrorDetail(res)
  }
  const blob = await res.blob()
  const name = parseContentDispositionFilename(res.headers.get('Content-Disposition')) ?? fallbackFilename
  const objectUrl = URL.createObjectURL(blob)
  try {
    const a = document.createElement('a')
    a.href = objectUrl
    a.download = name
    a.rel = 'noopener noreferrer'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}
