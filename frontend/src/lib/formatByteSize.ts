/** 人类可读体积（二进制单位，保留 2 位小数）。 */
export function formatByteSize(bytes: number): string {
  const n = Math.max(0, Math.round(bytes))
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(2)} MB`
  if (n >= 1024) return `${(n / 1024).toFixed(2)} KB`
  return `${n} B`
}
