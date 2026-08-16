export type AgentRunListRefreshAfterDeletePlan = {
  nextPage: number | null
  shouldReloadCurrentPage: boolean
}

export function planRefreshAfterDelete(args: {
  page: number
  pageSize: number
  total: number
  deletedCount: number
}): AgentRunListRefreshAfterDeletePlan {
  const newTotal = Math.max(0, args.total - args.deletedCount)
  const maxPage = Math.max(1, Math.ceil(newTotal / args.pageSize))
  if (args.page > maxPage) {
    return { nextPage: maxPage, shouldReloadCurrentPage: false }
  }
  return { nextPage: null, shouldReloadCurrentPage: true }
}

export function isAgentRunRowSelectionClick(target: HTMLElement): boolean {
  return Boolean(target.closest('.ant-checkbox-wrapper, .ant-checkbox, label'))
}

export function canDeleteAgentRuns(selectedRowKeys: string[], acting: boolean): boolean {
  return !acting && selectedRowKeys.length > 0
}
