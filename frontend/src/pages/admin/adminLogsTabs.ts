export const ADMIN_LOGS_TABS = [
  {
    tabId: 'logs',
    labelKey: 'admin.logs.operationTab',
  },
  {
    tabId: 'monitor',
    labelKey: 'admin.logs.retrievalMonitorTab',
  },
] as const

export type AdminLogsTabId = (typeof ADMIN_LOGS_TABS)[number]['tabId']

export const DEFAULT_ADMIN_LOGS_TAB: AdminLogsTabId = 'logs'

/** 操作日志 Tab 深链（含 tab=logs，避免停留在检索监控 Tab 时同路由无反应） */
export function adminLogsOperationPath(userId?: number): string {
  const params = new URLSearchParams({ tab: 'logs' })
  if (userId != null && userId > 0) {
    params.set('user_id', String(userId))
  }
  return `/admin/logs?${params.toString()}`
}

export function parseAdminLogsTabFromSearch(params: URLSearchParams): AdminLogsTabId {
  const tab = params.get('tab')
  if (tab === 'monitor') return 'monitor'
  if (tab === 'logs') return 'logs'
  if (params.get('user_id')) return 'logs'
  return DEFAULT_ADMIN_LOGS_TAB
}

export function parseAdminLogsUserIdFromSearch(params: URLSearchParams): number | undefined {
  const raw = params.get('user_id')
  if (!raw) return undefined
  const n = Number(raw)
  if (!Number.isFinite(n) || n <= 0) return undefined
  return Math.trunc(n)
}

/** 将用户筛选写入查询串（与 searchParams 同步，供 Select 与深链共用） */
export function applyAdminLogsUserIdToSearch(
  params: URLSearchParams,
  userId: number | undefined,
): URLSearchParams {
  const next = new URLSearchParams(params)
  if (userId == null) {
    next.delete('user_id')
  } else {
    next.set('user_id', String(userId))
  }
  return next
}

export function adminLogsTabButtonId(tabId: AdminLogsTabId): string {
  return `admin-logs-tab-${tabId}`
}

export function adminLogsTabPanelId(tabId: AdminLogsTabId): string {
  return `admin-logs-tabpanel-${tabId}`
}
