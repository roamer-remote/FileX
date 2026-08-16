/** 存储路径文件名：`{32位hex}_原名` → 展示用原名 */
const STORAGE_NAME_PREFIX_RE = /^[0-9a-f]{32}_/i

export function storageFilenameDisplayName(filename: string): string {
  if (!filename) return filename
  return filename.replace(STORAGE_NAME_PREFIX_RE, '')
}
