import { ReloadOutlined } from '@ant-design/icons'
import { DeleteActionIcon } from '@/components/DeleteActionIcon'
import { Alert, App, Button, Modal, Space, Table, Tabs, Tooltip, Typography } from 'antd'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  dedupeAdminMqQueueMessages,
  deleteAdminMqQueueMessages,
  getAdminMqQueueMessages,
  getAdminMqExtractQueuedJobs,
  getAdminMqPostQueuedJobs,
  getAdminMqQueuedJobs,
  type MqQueueMessageItem,
  type MqQueuedJobItem,
} from '@/api/admin'
import { mqActiveTaskUsername, type MqUserActiveTask } from '@/api/mq'
import MqStorageFilenameCell from '@/components/MqStorageFilenameCell'
import './MqQueueMessagesModal.css'

const AUTO_REFRESH_MS = 5000

const LABEL_TO_TASK_KIND: Record<string, string> = {
  index_main: 'kb_index',
  post_main: 'kb_post',
  extract_main: 'kb_extract',
  mineru_main: 'kb_mineru',
  docling_main: 'kb_docling',
}

type DbSource = 'index' | 'post' | 'extract' | null

type Props = {
  open: boolean
  queueName: string
  queueLabel: string
  queueKey: string
  dbSource: DbSource
  activeTasks?: MqUserActiveTask[]
  onClose: () => void
  onMutated: () => void
}

function formatTaskTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export default function MqQueueMessagesModal({
  open,
  queueName,
  queueLabel,
  queueKey,
  dbSource,
  activeTasks = [],
  onClose,
  onMutated,
}: Props) {
  const { modal, message } = App.useApp()
  const { t } = useTranslation()
  const [tab, setTab] = useState<'mq' | 'db'>('mq')
  const [loading, setLoading] = useState(false)
  const [items, setItems] = useState<MqQueueMessageItem[]>([])
  const [messageCount, setMessageCount] = useState(0)
  const [peekCount, setPeekCount] = useState(0)
  const [rawPeekCount, setRawPeekCount] = useState(0)
  const [truncated, setTruncated] = useState(false)
  const [dbLoading, setDbLoading] = useState(false)
  const [dbItems, setDbItems] = useState<MqQueuedJobItem[]>([])
  const [dbTotal, setDbTotal] = useState(0)
  const [dbTruncated, setDbTruncated] = useState(false)
  const [acting, setActing] = useState(false)
  const tableScrollRef = useRef<HTMLDivElement>(null)
  const mqLoadSeqRef = useRef(0)
  const dbLoadSeqRef = useRef(0)
  const [tableScrollY, setTableScrollY] = useState(400)

  const taskKind = queueKey ? LABEL_TO_TASK_KIND[queueKey] : undefined
  const queueActiveTasks = taskKind
    ? activeTasks.filter((task) => task.kind === taskKind)
    : []

  useLayoutEffect(() => {
    if (!open) return
    const host = tableScrollRef.current
    if (!host) return

    const measure = () => {
      const header =
        (host.querySelector('.ant-table-header') as HTMLElement | null) ??
        (host.querySelector('.ant-table-thead') as HTMLElement | null)
      const headerH = header ? Math.ceil(header.getBoundingClientRect().height) : 39
      const slot = host.clientHeight
      setTableScrollY(Math.max(120, Math.floor(slot - headerH - 8)))
    }

    const run = () => {
      requestAnimationFrame(() => {
        requestAnimationFrame(measure)
      })
    }

    run()
    const ro = new ResizeObserver(run)
    ro.observe(host)
    window.addEventListener('resize', run)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', run)
    }
  }, [open, loading, dbLoading, dbSource, truncated, dbTruncated, items.length, dbItems.length, tab])

  const loadMq = useCallback(async (opts?: { silent?: boolean }) => {
    if (!queueName) return
    const seq = ++mqLoadSeqRef.current
    if (!opts?.silent) setLoading(true)
    try {
      const res = await getAdminMqQueueMessages(queueName)
      if (seq !== mqLoadSeqRef.current) return
      const peeked = res.data.peek_count ?? res.data.items.length
      const raw = res.data.raw_peek_count ?? peeked
      setItems(res.data.items)
      setMessageCount(res.data.message_count)
      setPeekCount(peeked)
      setRawPeekCount(raw)
      setTruncated(res.data.truncated)
    } catch {
      if (seq !== mqLoadSeqRef.current) return
      if (!opts?.silent) {
        message.error(t('admin.mq.messagesLoadFailed'))
      }
      setItems([])
      setMessageCount(0)
      setPeekCount(0)
      setRawPeekCount(0)
      setTruncated(false)
    } finally {
      if (seq === mqLoadSeqRef.current && !opts?.silent) setLoading(false)
    }
  }, [queueName, t])

  const loadDb = useCallback(async (opts?: { silent?: boolean }) => {
    if (!dbSource) return
    const seq = ++dbLoadSeqRef.current
    if (!opts?.silent) setDbLoading(true)
    try {
      if (dbSource === 'post') {
        const res = await getAdminMqPostQueuedJobs()
        if (seq !== dbLoadSeqRef.current) return
        setDbItems(res.data.items)
        setDbTotal(res.data.total)
        setDbTruncated(res.data.truncated)
        return
      }
      const res =
        dbSource === 'extract'
          ? await getAdminMqExtractQueuedJobs()
          : await getAdminMqQueuedJobs()
      if (seq !== dbLoadSeqRef.current) return
      setDbItems(res.data.items)
      setDbTotal(res.data.total)
      setDbTruncated(res.data.truncated)
    } catch {
      if (seq !== dbLoadSeqRef.current) return
      if (!opts?.silent) {
        message.error(t('admin.mq.dbQueuedLoadFailed'))
      }
      setDbItems([])
      setDbTotal(0)
      setDbTruncated(false)
    } finally {
      if (seq === dbLoadSeqRef.current && !opts?.silent) setDbLoading(false)
    }
  }, [dbSource, t])

  const loadAll = useCallback(
    async (opts?: { silent?: boolean }) => {
      await Promise.all([loadMq(opts), dbSource ? loadDb(opts) : Promise.resolve()])
    },
    [loadMq, loadDb, dbSource],
  )

  useEffect(() => {
    if (!open) return
    void loadAll()
    const timer = window.setInterval(() => {
      if (acting) return
      void loadAll({ silent: true })
      onMutated()
    }, AUTO_REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [open, loadAll, onMutated, acting])

  const handleDelete = (row: MqQueueMessageItem) => {
    modal.confirm({
      title: t('admin.mq.deleteConfirmTitle'),
      content: t('admin.mq.deleteConfirmContent'),
      okText: t('admin.mq.deleteMessage'),
      okType: 'danger',
      cancelText: t('common.cancel'),
      onOk: async () => {
        setActing(true)
        try {
          const res = await deleteAdminMqQueueMessages(queueName, { index: row.index })
          if (res.data.removed < 1) {
            message.warning(t('admin.mq.deleteNotFound'))
          } else {
            message.success(t('admin.mq.deleteSuccess', { count: res.data.removed }))
          }
          await loadAll()
          onMutated()
        } catch {
          message.error(t('admin.mq.messagesActionFailed'))
        } finally {
          setActing(false)
        }
      },
    })
  }

  const handlePurge = () => {
    modal.confirm({
      title: t('admin.mq.purgeConfirmTitle'),
      content: t('admin.mq.purgeConfirmContent', { queue: queueName, count: messageCount }),
      okText: t('admin.mq.purgeQueue'),
      okType: 'danger',
      cancelText: t('common.cancel'),
      onOk: async () => {
        setActing(true)
        try {
          const res = await deleteAdminMqQueueMessages(queueName, { purge: true })
          if (res.data.removed < 1 && res.data.message_count > 0) {
            message.warning(t('admin.mq.purgeNotFound'))
          } else {
            message.success(t('admin.mq.purgeSuccess', { count: res.data.removed }))
          }
          await loadAll()
          onMutated()
        } catch {
          message.error(t('admin.mq.messagesActionFailed'))
        } finally {
          setActing(false)
        }
      },
    })
  }

  const duplicateExtra = Math.max(0, rawPeekCount - peekCount)

  const handleDedupe = () => {
    modal.confirm({
      title: t('admin.mq.dedupeConfirmTitle'),
      content: t('admin.mq.dedupeConfirmContent', { count: duplicateExtra }),
      okText: t('admin.mq.dedupeQueue'),
      okType: 'danger',
      cancelText: t('common.cancel'),
      onOk: async () => {
        setActing(true)
        try {
          const res = await dedupeAdminMqQueueMessages(queueName)
          if (res.data.removed < 1) {
            message.info(t('admin.mq.dedupeNoop'))
          } else {
            message.success(t('admin.mq.dedupeSuccess', { count: res.data.removed }))
          }
          await loadAll()
          onMutated()
        } catch {
          message.error(t('admin.mq.messagesActionFailed'))
        } finally {
          setActing(false)
        }
      },
    })
  }

  const mqTable = (
    <div ref={tableScrollRef} className="mq-msg-table-scroll">
      <Table<MqQueueMessageItem>
        className="mq-msg-table"
        size="small"
        sticky
        rowKey={(row) => `mq-msg-${row.index}`}
        loading={loading}
        dataSource={items}
        pagination={false}
        locale={{ emptyText: t('admin.mq.messagesEmpty') }}
        scroll={{ x: 640, y: tableScrollY }}
        columns={[
          {
            title: t('admin.mq.colJobId'),
            dataIndex: 'job_id',
            width: 88,
            render: (v: number | null) => (v != null ? v : '—'),
          },
          {
            title: t('admin.mq.colDuplicateCount'),
            dataIndex: 'duplicate_count',
            width: 56,
            align: 'center' as const,
            render: (v: number | undefined) => ((v ?? 1) > 1 ? `×${v}` : '—'),
          },
          {
            title: t('admin.mq.colLastError'),
            dataIndex: 'last_error',
            ellipsis: true,
            render: (v: string | null) => v || '—',
          },
          {
            title: t('admin.mq.colBody'),
            dataIndex: 'body_preview',
            ellipsis: true,
          },
          {
            title: t('admin.mq.colActions'),
            key: 'actions',
            width: 48,
            render: (_: unknown, row) => (
              <Tooltip title={t('admin.mq.deleteMessage')}>
                <Button
                  type="link"
                  danger
                  size="small"
                  icon={<DeleteActionIcon />}
                  aria-label={t('admin.mq.deleteMessage')}
                  disabled={acting}
                  onClick={() => handleDelete(row)}
                />
              </Tooltip>
            ),
          },
        ]}
      />
    </div>
  )

  const dbTable = (
    <div ref={tableScrollRef} className="mq-msg-table-scroll">
      <Table<MqQueuedJobItem>
        className="mq-msg-table"
        size="small"
        sticky
        rowKey={(row) => `mq-db-${row.job_id}`}
        loading={dbLoading}
        dataSource={dbItems}
        pagination={false}
        locale={{ emptyText: t('admin.mq.dbQueuedEmpty') }}
        scroll={{ x: 640, y: tableScrollY }}
        columns={[
          {
            title: t('admin.mq.colJobId'),
            dataIndex: 'job_id',
            width: 88,
          },
          {
            title: t('admin.mq.colUser'),
            dataIndex: 'username',
            width: 96,
            ellipsis: true,
          },
          {
            title: t('admin.mq.colFile'),
            dataIndex: 'filename',
            ellipsis: false,
            render: (v: string | null | undefined) => <MqStorageFilenameCell filename={v} />,
          },
          {
            title: t('admin.mq.colUpdatedAt'),
            dataIndex: 'updated_at',
            width: 148,
            render: (v: string | null | undefined) => formatTaskTime(v),
          },
        ]}
      />
    </div>
  )

  return (
    <Modal
      open={open}
      title={t(dbSource ? 'admin.mq.detailTitle' : 'admin.mq.messagesTitle', { queue: queueLabel })}
      onCancel={onClose}
      width={760}
      rootClassName="mq-msg-modal"
      footer={
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => void loadAll()} loading={loading || dbLoading}>
            {t('admin.mq.refreshMessages')}
          </Button>
          {tab === 'mq' && duplicateExtra > 0 ? (
            <Button danger loading={acting} icon={<DeleteActionIcon />} onClick={handleDedupe}>
              {t('admin.mq.dedupeQueue')}
            </Button>
          ) : null}
          {tab === 'mq' ? (
            <Button danger disabled={messageCount < 1} loading={acting} icon={<DeleteActionIcon />} onClick={handlePurge}>
              {t('admin.mq.purgeQueue')}
            </Button>
          ) : null}
          <Button onClick={onClose}>{t('admin.mq.modalClose')}</Button>
        </Space>
      }
      destroyOnClose
    >
      <div className="mq-msg-layout">
        {dbSource && queueActiveTasks.length > 0 ? (
          <div className="mq-msg-active-block">
            <Typography.Text strong className="mq-msg-section-label">
              {t('admin.mq.activeTasksTitle')}
            </Typography.Text>
            <ul className="mq-msg-active-list">
              {queueActiveTasks.map((task) => (
                <li key={`${task.kind}-${task.file_id}-${mqActiveTaskUsername(task) ?? '?'}`}>
                  <span className="mq-msg-active-user">{mqActiveTaskUsername(task) ?? '—'}</span>
                  <span className="mq-msg-active-file">
                    <MqStorageFilenameCell filename={task.filename || `#${task.file_id ?? '?'}`} />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="mq-msg-head-sticky">
          {dbSource ? (
            <Alert type="info" showIcon message={t('admin.mq.detailHint')} className="mq-msg-warn" />
          ) : null}
          {tab === 'mq' && dbSource ? (
            <Alert type="warning" showIcon message={t('admin.mq.mainQueueDeleteWarn')} className="mq-msg-warn" />
          ) : null}
          {tab === 'mq' && duplicateExtra > 0 ? (
            <Alert type="info" showIcon message={t('admin.mq.messagesDuplicatesHint')} className="mq-msg-warn" />
          ) : null}
          {tab === 'mq' && !truncated && peekCount > 0 && messageCount !== peekCount ? (
            <Typography.Paragraph type="secondary" className="mq-msg-hint">
              {t('admin.mq.messagesDepthDrift', { listed: peekCount, live: messageCount })}
            </Typography.Paragraph>
          ) : null}
          {tab === 'mq' && truncated ? (
            <Typography.Paragraph type="secondary" className="mq-msg-hint">
              {t('admin.mq.messagesTruncated', { limit: 50, total: messageCount })}
            </Typography.Paragraph>
          ) : null}
          {tab === 'db' && dbTruncated ? (
            <Typography.Paragraph type="secondary" className="mq-msg-hint">
              {t('admin.mq.dbQueuedTruncated', { limit: 50, total: dbTotal })}
            </Typography.Paragraph>
          ) : null}
        </div>

        {dbSource ? (
          <Tabs
            activeKey={tab}
            onChange={(key) => setTab(key as 'mq' | 'db')}
            className="mq-msg-tabs"
            items={[
              {
                key: 'mq',
                label: `${t('admin.mq.tabMqMessages')} (${peekCount})`,
                children: mqTable,
              },
              {
                key: 'db',
                label: `${t('admin.mq.tabDbQueued')} (${dbTotal})`,
                children: dbTable,
              },
            ]}
          />
        ) : (
          mqTable
        )}
      </div>
    </Modal>
  )
}
