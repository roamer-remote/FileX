import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { App, Button, Empty, Pagination, Select, Space, Spin, Table, Tag } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { DeleteActionIcon } from '@/components/DeleteActionIcon'
import { deleteAgentRuns, listAgentRuns, type AgentRunSummary } from '@/api/agentRuns'
import { listAdminUsers, type AdminUserRow } from '@/api/admin'
import { useAuthStore } from '@/stores/authStore'
import { useFlexTableBodyScrollY } from '@/hooks/useFlexTableBodyScrollY'
import { formatDate } from '@/utils'
import {
  canDeleteAgentRuns,
  isAgentRunRowSelectionClick,
  planRefreshAfterDelete,
} from '@/pages/agentRunListActions'
import '@/pages/admin/AdminPage.css'
import './AgentRunPages.css'

function statusColor(status: string): string {
  switch (status) {
    case 'running':
      return 'processing'
    case 'completed':
      return 'success'
    case 'failed':
      return 'error'
    default:
      return 'default'
  }
}

export default function AgentRunListPage() {
  const { t } = useTranslation()
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const bodyRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [acting, setActing] = useState(false)
  const [items, setItems] = useState<AgentRunSummary[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const user = useAuthStore((s) => s.user)
  const isAdmin = user?.is_admin === true
  const currentUsername = user?.username
  const [filterUserId, setFilterUserId] = useState<number | undefined>(undefined)
  const [userOptions, setUserOptions] = useState<{ value: number; label: string }[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    // Load user list for admin filter (once)
    if (isAdmin && userOptions.length === 0) {
      try {
        const uRes = await listAdminUsers({ page: 1, page_size: 100 })
        const data = uRes.data as { items?: AdminUserRow[]; total?: number }
        if (Array.isArray(data?.items)) {
          setUserOptions(data.items.map((u) => ({ value: u.id, label: u.username })))
        }
      } catch { /* ignore */ }
    }
    try {
      const params: { page: number; page_size: number; user_id?: number; all_users?: boolean } = {
        page,
        page_size: pageSize,
      }
      if (isAdmin && filterUserId != null) {
        params.user_id = filterUserId
      } else if (isAdmin) {
        params.all_users = true
      }
      const res = await listAgentRuns(params)
      setItems(res.data.items)
      setTotal(res.data.total)
    } catch (e) {
      message.error(String(e))
    } finally {
      setLoading(false)
    }
  }, [message, page, pageSize, isAdmin, filterUserId, userOptions.length])

  useEffect(() => {
    void load()
  }, [load])

  const refreshAfterDelete = useCallback(
    async (deletedCount: number) => {
      setSelectedRowKeys([])
      const plan = planRefreshAfterDelete({ page, pageSize, total, deletedCount })
      if (plan.nextPage != null) {
        setPage(plan.nextPage)
        return
      }
      if (plan.shouldReloadCurrentPage) {
        await load()
      }
    },
    [load, page, pageSize, total],
  )

  const confirmDeleteSelected = useCallback(() => {
    if (selectedRowKeys.length === 0) return
    modal.confirm({
      title: t('agentRuns.deleteSelectedTitle'),
      content: t('agentRuns.deleteSelectedContent', { count: selectedRowKeys.length }),
      okText: t('agentRuns.delete'),
      okButtonProps: { danger: true },
      cancelText: t('common.cancel'),
      onOk: async () => {
        setActing(true)
        try {
          const res = await deleteAgentRuns(selectedRowKeys)
          message.success(t('agentRuns.deleteSuccess', { count: res.data.deleted }))
          await refreshAfterDelete(res.data.deleted)
        } catch (e) {
          message.error(String(e))
        } finally {
          setActing(false)
        }
      },
    })
  }, [message, modal, refreshAfterDelete, selectedRowKeys, t])

  const scrollY = useFlexTableBodyScrollY([loading, items.length, page, pageSize], { bodyRef })
  const tableScroll = items.length > 0 && scrollY > 0 ? { y: scrollY } : undefined

  const columns: ColumnsType<AgentRunSummary> = useMemo(
    () => [
      { title: t('agentRuns.colTime'), dataIndex: 'started_at', width: 180, render: (v: string) => formatDate(v) },
      ...(isAdmin ? [{ title: t('admin.users.ident'), dataIndex: 'username' as const, width: 120, ellipsis: true, render: (v?: string | null) => v || '—' }] : []),
      { title: t('agentRuns.colQuestion'), dataIndex: 'question_preview', ellipsis: true },
      { title: t('agentRuns.colStatus'), dataIndex: 'status', width: 110, render: (v: string) => <Tag color={statusColor(v)}>{v}</Tag> },
      { title: t('agentRuns.colIntent'), dataIndex: 'intent', width: 120, render: (v?: string | null) => v || '—' },
      { title: t('agentRuns.colDuration'), dataIndex: 'duration_ms', width: 100, render: (v?: number | null) => (v != null ? `${(v / 1000).toFixed(1)}s` : '—') },
      { title: t('agentRuns.colThread'), dataIndex: 'thread_id', width: 160, ellipsis: true, render: (v?: string | null) => v || '—' },
    ],
    [t, isAdmin],
  )

  return (
    <div className="admin-root agent-run-root">
      <div className="admin-panel agent-run-panel">
        <header className="admin-header admin-header--compact agent-run-panel__header">
          <div className="ah-title-group">
            <h2 className="ah-title">{t('agentRuns.listTitle')}</h2>
            <span className="ah-sub agent-run-panel__sub">
              {isAdmin ? `全站 ${total} 条 · ${userOptions.length} 位用户` : t('agentRuns.listHint')}
            </span>
          </div>
          <div className="ah-toolbar agent-run-panel__toolbar">
            <Space>
              {isAdmin && (
                <Select
                  allowClear
                  showSearch
                  placeholder={t('admin.agentRuns.filterUserPlaceholder')}
                  value={filterUserId}
                  onChange={(val) => { setFilterUserId(val); setPage(1) }}
                  style={{ minWidth: 180 }}
                  filterOption={(input, option) =>
                    (option?.children as unknown as string)?.toLowerCase().includes(input.toLowerCase())
                  }
                >
                  {userOptions.map((u) => (
                    <Select.Option key={u.value} value={u.value}>{u.label}</Select.Option>
                  ))}
                </Select>
              )}
              <Button danger size="small" disabled={!canDeleteAgentRuns(selectedRowKeys, acting)} icon={<DeleteActionIcon />} onClick={() => confirmDeleteSelected()}>
                {t('agentRuns.deleteSelected', { count: selectedRowKeys.length })}
              </Button>
              <Button type="primary" size="small" icon={<ReloadOutlined spin={loading} />} onClick={() => void load()}>
                {t('agentRuns.refresh')}
              </Button>
            </Space>
          </div>
        </header>
        <div className="admin-table-wrap admin-table-wrap--flex fl-table-shell agent-run-table-wrap">
          <div className="fl-body" ref={bodyRef}>
            <Spin spinning={loading} className="fl-spin">
              <div className="fl-table-host">
                <Table<AgentRunSummary>
                  className="agent-run-table fl-file-table" rowKey="id" size="small" tableLayout="fixed"
                  columns={columns} dataSource={items} pagination={false} scroll={tableScroll}
                  rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys as string[]), getCheckboxProps: () => ({ disabled: acting }) }}
                  locale={{ emptyText: <Empty className="agent-run-empty" description={t('agentRuns.empty')} /> }}
                  onRow={(row) => {
                    const isOwn = !isAdmin || (row.username && row.username === currentUsername)
                    return {
                      onClick: (event) => {
                        const target = event.target as HTMLElement
                        if (isAgentRunRowSelectionClick(target)) return
                        if (!isOwn) return
                        navigate(`/agent/runs/${row.id}`)
                      },
                      style: { cursor: isOwn ? 'pointer' : 'default' },
                    }
                  }}
                />
              </div>
            </Spin>
          </div>
          <div className="fl-pager">
            <Pagination current={page} pageSize={pageSize} total={total} showSizeChanger
              pageSizeOptions={['10', '20', '50', '100']}
              onChange={(p, ps) => { setSelectedRowKeys([]); setPage(p); setPageSize(ps) }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
