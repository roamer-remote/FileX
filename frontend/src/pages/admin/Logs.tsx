import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { DeleteActionIcon } from '@/components/DeleteActionIcon'
import KbPipelineMonitor from '@/components/admin/KbPipelineMonitor'
import { App, Button, Pagination, Select, Space, Spin, Table, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  deleteAdminLog,
  deleteAdminLogsBatch,
  listAdminLogs,
  listAdminUsers,
  purgeAdminLogs,
  type AdminLogItem,
} from '@/api/admin'
import {
  ADMIN_LOGS_TABS,
  adminLogsTabButtonId,
  adminLogsTabPanelId,
  applyAdminLogsUserIdToSearch,
  parseAdminLogsTabFromSearch,
  parseAdminLogsUserIdFromSearch,
  type AdminLogsTabId,
} from '@/pages/admin/adminLogsTabs'
import { formatDate } from '@/utils'
import { useFlexTableBodyScrollY } from '@/hooks/useFlexTableBodyScrollY'
import { formatAdminLogDetail } from './logDetail'
import '@/components/FileList.css'
import '@/styles/helpDoc.css'
import './AdminPage.css'

function actorLabel(row: AdminLogItem, systemLabel: string): string {
  if (row.username) return row.username
  if (row.user_id) return `#${row.user_id}`
  return systemLabel
}

function actionClass(action: string): string {
  const a = action.toLowerCase()
  if (/upload|create|register/i.test(a)) return 'create'
  if (/delete|remove|purge/i.test(a)) return 'delete'
  if (/update|rename|move|modify|edit/i.test(a)) return 'update'
  if (/login|auth|verify/i.test(a)) return 'auth'
  if (/download|access|view|preview/i.test(a)) return 'access'
  if (/share/i.test(a)) return 'share'
  return 'default'
}

interface UserOption {
  id: number
  username: string
}

type AdminLogsTabPanelProps = {
  tabId: AdminLogsTabId
  activeTab: AdminLogsTabId
  children: ReactNode
}

function AdminLogsTabPanel({ tabId, activeTab, children }: AdminLogsTabPanelProps) {
  return (
    <div
      role="tabpanel"
      id={adminLogsTabPanelId(tabId)}
      aria-labelledby={adminLogsTabButtonId(tabId)}
      hidden={activeTab !== tabId}
      className="admin-logs-tabs__panel"
    >
      {children}
    </div>
  )
}

export default function AdminLogsPage() {
  const { modal, message } = App.useApp()
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const [activeTab, setActiveTab] = useState<AdminLogsTabId>(() => parseAdminLogsTabFromSearch(searchParams))
  const [logs, setLogs] = useState<AdminLogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [acting, setActing] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [users, setUsers] = useState<UserOption[]>([])
  const [filterUserId, setFilterUserId] = useState<number | undefined>(() =>
    parseAdminLogsUserIdFromSearch(searchParams),
  )
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([])
  const bodyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setActiveTab(parseAdminLogsTabFromSearch(searchParams))
    setFilterUserId(parseAdminLogsUserIdFromSearch(searchParams))
    setPage(1)
  }, [searchParams])

  const setActiveTabWithUrl = useCallback(
    (tabId: AdminLogsTabId) => {
      const next = new URLSearchParams(searchParams)
      if (tabId === 'monitor') {
        next.set('tab', 'monitor')
      } else {
        next.delete('tab')
      }
      setSearchParams(next, { replace: true })
    },
    [searchParams, setSearchParams],
  )

  const loadLogs = useCallback(async (p: number, ps: number, userId?: number) => {
    setLoading(true)
    try {
      const res = await listAdminLogs({ page: p, page_size: ps, user_id: userId })
      setLogs(res.data.items)
      setTotal(res.data.total)
      setSelectedRowKeys([])
    } catch {
      /* interceptor */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (activeTab !== 'logs') return
    void loadLogs(page, pageSize, filterUserId)
  }, [activeTab, filterUserId, loadLogs, page, pageSize])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await listAdminUsers({ page: 1, page_size: 100 })
        if (!cancelled) {
          setUsers(res.data.items.map((u) => ({ id: u.id, username: u.username })))
        }
      } catch {
        /* interceptor */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const scrollY = useFlexTableBodyScrollY([loading, logs.length, page, pageSize, activeTab], {
    bodyRef,
  })

  const tableScroll = logs.length > 0 && scrollY > 0 ? { y: scrollY, x: 'max-content' as const } : { x: 'max-content' as const }

  const refreshAfterDelete = useCallback(
    async (deleted: number) => {
      if (deleted <= 0) return
      const remaining = Math.max(0, total - deleted)
      const nextPage =
        remaining === 0 ? 1 : page > Math.ceil(remaining / pageSize) ? Math.max(1, page - 1) : page
      setPage(nextPage)
      await loadLogs(nextPage, pageSize, filterUserId)
    },
    [filterUserId, loadLogs, page, pageSize, total],
  )

  const confirmDeleteOne = useCallback(
    (row: AdminLogItem) => {
      modal.confirm({
        title: t('admin.logs.deleteOneTitle'),
        content: t('admin.logs.deleteOneContent', { id: row.id, action: row.action }),
        okText: t('admin.logs.delete'),
        okButtonProps: { danger: true },
        cancelText: t('common.cancel'),
        onOk: async () => {
          setActing(true)
          try {
            const res = await deleteAdminLog(row.id)
            message.success(t('admin.logs.deleteSuccess', { count: res.data.deleted }))
            await refreshAfterDelete(res.data.deleted)
          } finally {
            setActing(false)
          }
        },
      })
    },
    [message, modal, refreshAfterDelete, t],
  )

  const confirmDeleteSelected = useCallback(() => {
    if (selectedRowKeys.length === 0) return
    modal.confirm({
      title: t('admin.logs.deleteSelectedTitle'),
      content: t('admin.logs.deleteSelectedContent', { count: selectedRowKeys.length }),
      okText: t('admin.logs.delete'),
      okButtonProps: { danger: true },
      cancelText: t('common.cancel'),
      onOk: async () => {
        setActing(true)
        try {
          const res = await deleteAdminLogsBatch(selectedRowKeys)
          message.success(t('admin.logs.deleteSuccess', { count: res.data.deleted }))
          await refreshAfterDelete(res.data.deleted)
        } finally {
          setActing(false)
        }
      },
    })
  }, [message, modal, refreshAfterDelete, selectedRowKeys, t])

  const confirmPurgeAll = useCallback(() => {
    if (total <= 0) return
    const filteredUser = users.find((u) => u.id === filterUserId)
    modal.confirm({
      title: filterUserId ? t('admin.logs.purgeUserTitle') : t('admin.logs.purgeAllTitle'),
      content: filterUserId
        ? t('admin.logs.purgeUserContent', {
            username: filteredUser?.username ?? `#${filterUserId}`,
            count: total,
          })
        : t('admin.logs.purgeAllContent', { count: total }),
      okText: t('admin.logs.purgeAll'),
      okButtonProps: { danger: true },
      cancelText: t('common.cancel'),
      onOk: async () => {
        setActing(true)
        try {
          const res = await purgeAdminLogs(filterUserId)
          message.success(t('admin.logs.purgeSuccess', { count: res.data.deleted }))
          setPage(1)
          await loadLogs(1, pageSize, filterUserId)
        } finally {
          setActing(false)
        }
      },
    })
  }, [filterUserId, loadLogs, message, modal, pageSize, t, total, users])

  const columns: ColumnsType<AdminLogItem> = [
    {
      title: t('admin.logs.timestamp'),
      dataIndex: 'created_at',
      width: 180,
      render: (d: string) => <span className="at-mono">{formatDate(d)}</span>,
    },
    {
      title: t('admin.logs.actor'),
      key: 'actor',
      width: 140,
      render: (_, row) => {
        const label = actorLabel(row, t('admin.logs.system'))
        return (
          <div className="at-ident">
            <span className="at-avatar-sm">{label.charAt(0).toUpperCase()}</span>
            <span className="at-name">{label}</span>
          </div>
        )
      },
    },
    {
      title: t('admin.logs.action'),
      dataIndex: 'action',
      width: 130,
      render: (action: string) => <span className={`al-action al-action--${actionClass(action)}`}>{action}</span>,
    },
    {
      title: t('admin.logs.detail'),
      dataIndex: 'detail',
      ellipsis: true,
      render: (d: string | null) => <span className="al-detail">{formatAdminLogDetail(d, t)}</span>,
    },
    {
      title: t('admin.logs.actions'),
      key: 'actions',
      width: 48,
      fixed: 'right',
      render: (_, row) => (
        <Tooltip title={t('admin.logs.delete')}>
          <Button
            type="link"
            danger
            size="small"
            icon={<DeleteActionIcon />}
            aria-label={t('admin.logs.delete')}
            disabled={acting}
            onClick={() => confirmDeleteOne(row)}
          />
        </Tooltip>
      ),
    },
  ]

  const pageTitle =
    activeTab === 'logs' ? t('admin.logs.operationTab') : t('admin.logs.retrievalMonitorTab')

  return (
    <div className="admin-root">
      <div className="admin-panel admin-panel--logs">
        <div className="admin-header">
          <div className="ah-title-group">
            <h2 className="ah-title">{pageTitle}</h2>
            {activeTab === 'logs' ? (
              <span className="ah-count-inline">
                <span className="ah-count-num">{total}</span>
                <span className="ah-count-label">{t('admin.logs.events')}</span>
              </span>
            ) : null}
          </div>
          {activeTab === 'logs' ? (
            <div className="ah-toolbar">
              <Space wrap>
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  placeholder={t('admin.logs.userFilter')}
                  style={{ minWidth: 160 }}
                  value={filterUserId}
                  onChange={(v) => {
                    const userId = v === null || v === undefined ? undefined : Number(v)
                    setSearchParams(applyAdminLogsUserIdToSearch(searchParams, userId), { replace: true })
                  }}
                  options={users.map((u) => ({ label: u.username, value: u.id }))}
                />
                <Button
                  danger
                  disabled={acting || selectedRowKeys.length === 0}
                  icon={<DeleteActionIcon />}
                  onClick={() => confirmDeleteSelected()}
                >
                  {t('admin.logs.deleteSelected', { count: selectedRowKeys.length })}
                </Button>
                <Button
                  danger
                  disabled={acting || total <= 0}
                  icon={<DeleteActionIcon />}
                  onClick={() => confirmPurgeAll()}
                >
                  {t('admin.logs.purgeAll')}
                </Button>
              </Space>
            </div>
          ) : null}
        </div>
        <div className="admin-logs-tabs">
          <nav
            className="wlg-help-section-nav wlg-help-section-nav--admin admin-logs-tabs__nav"
            role="tablist"
            aria-label={t('admin.logs.subTabsAria')}
          >
            {ADMIN_LOGS_TABS.map((tab) => {
              const isActive = activeTab === tab.tabId
              return (
                <button
                  key={tab.tabId}
                  type="button"
                  role="tab"
                  id={adminLogsTabButtonId(tab.tabId)}
                  className={`wlg-help-section-btn wlg-help-section-btn--admin${isActive ? ' is-active' : ''}`}
                  aria-selected={isActive}
                  aria-controls={adminLogsTabPanelId(tab.tabId)}
                  onClick={() => setActiveTabWithUrl(tab.tabId)}
                >
                  {t(tab.labelKey)}
                </button>
              )
            })}
          </nav>
          <div className="admin-logs-tabs__panels">
            <AdminLogsTabPanel tabId="logs" activeTab={activeTab}>
              <div className="admin-table-wrap admin-table-wrap--flex fl-table-shell">
                <div className="fl-body" ref={bodyRef}>
                  <Spin spinning={loading} className="fl-spin">
                    <div className="fl-table-host">
                      <Table
                        className="admin-logs-table"
                        rowKey="id"
                        columns={columns}
                        dataSource={logs}
                        size="small"
                        tableLayout="fixed"
                        pagination={false}
                        scroll={tableScroll}
                        rowSelection={{
                          selectedRowKeys,
                          onChange: (keys) => setSelectedRowKeys(keys.map((key) => Number(key))),
                          preserveSelectedRowKeys: false,
                        }}
                      />
                    </div>
                  </Spin>
                </div>
                <div className="fl-pager">
                  <Pagination
                    current={page}
                    pageSize={pageSize}
                    total={total}
                    showSizeChanger
                    pageSizeOptions={['10', '20', '50', '100']}
                    onChange={(p, ps) => {
                      setPage(p)
                      setPageSize(ps)
                    }}
                  />
                </div>
              </div>
            </AdminLogsTabPanel>
            <AdminLogsTabPanel tabId="monitor" activeTab={activeTab}>
              {activeTab === 'monitor' ? <KbPipelineMonitor /> : null}
            </AdminLogsTabPanel>
          </div>
        </div>
      </div>
    </div>
  )
}
