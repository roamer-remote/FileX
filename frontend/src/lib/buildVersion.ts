export const BUILD_VERSION_RE = /^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-[0-9a-f]{7}$/

export function normalizeBuildVersion(raw: string | undefined): string {
  const trimmed = raw?.trim() ?? ''
  return BUILD_VERSION_RE.test(trimmed) ? trimmed : ''
}

export const APP_BUILD_VERSION = normalizeBuildVersion(
  import.meta.env.VITE_APP_BUILD_VERSION,
)
