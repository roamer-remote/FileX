import { CloseCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { App, Button, Modal, Space, Table } from 'antd'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  cancelUserMqExtractJob,
  cancelUserMqIndexJob,
  getUserMqExtractQueuedJobs,
  getUserMqIndexQueuedJobs,
  getUserMqPostQueuedJobs,
  type MqUserQueuedJobItem,
} from '@/api/mq'
import MqStorageFilenameCell from '@/components/MqStorageFilenameCell'
import '@/pages/admin/MqQueueMessagesModal.css'

const AUTO_REFRESH_MS = 5000

type DbSource = 'index' | 'post' | 'extract'

type Props = {
  open: boolean
  queueLabel: string
  dbSource: DbSource
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

export default function MqUserQueueDetailsModal({ open, queueLabel, dbSource, onClose, onMutated }: Props) {
  const { modal, message } = App.useApp()
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [items, setItems] = useState<MqUserQueuedJobItem[]>([])
  const [total, setTotal] = useState(0)
  const [truncated, setTruncated] = useState(false)
  const [acting, setActing] = useState(false)
  const tableScrollRef = useRef<HTMLDivElement>(null)
  const loadSeqRef = useRef(0)
  const [tableScrollY, setTableScrollY] = useState(400)

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
  }, [open, loading, truncated, items.length])

  const loadDb = useCallback(
    async (opts?: { silent?: boolean }) => {
      const seq = ++loadSeqRef.current
      if (!opts?.silent) setLoading(true)
      try {
        if (dbSource === 'post') {
          const res = await getUserMqPostQueuedJobs()
          if (seq !== loadSeqRef.current) return
          setItems(res.data.items)
          setTotal(res.data.total)
          setTruncated(res.data.truncated)
          return
        }
        const res =
          dbSource === 'extract' ? await getUserMqExtractQueuedJobs() : await getUserMqIndexQueuedJobs()
        if (seq !== loadSeqRef.current) return
        setItems(res.data.items)
        setTotal(res.data.total)
        setTruncated(res.data.truncated)
      } catch {
        if (seq !== loadSeqRef.current) return
        if (!opts?.silent) message.error(t('userMq.loadFailed'))
        setItems([])
        setTotal(0)
        setTruncated(false)
      } finally {
        if (seq === loadSeqRef.current && !opts?.silent) setLoading(false)
      }
    },
    [dbSource, message, t],
  )

  useEffect(() => {
    if (!open) return
    void loadDb()
    const timer = window.setInterval(() => {
      if (acting) return
      void loadDb({ silent: true })
      onMutated()
    }, AUTO_REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [open, loadDb, onMutated, acting])

  const handleCancel = (row: MqUserQueuedJobItem) => {
    modal.confirm({
      title: t('userMq.cancelConfirmTitle'),
      content: t('userMq.cancelConfirmContent', { name: row.filename, jobId: row.job_id }),
      okText: t('userMq.cancelOk'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        setActing(true)
        try {
          if (dbSource === 'index') {
            await cancelUserMqIndexJob(row.job_id)
          } else {
            await cancelUserMqExtractJob(row.job_id)
          }
          message.success(t('userMq.cancelSuccess'))
          await loadDb()
          onMutated()
        } catch {
          message.error(t('userMq.cancelFailed'))
        } finally {
          setActing(false)
        }
      },
    })
  }

  return (
    <Modal
      open={open}
      title={t('admin.mq.detailTitle', { queue: queueLabel })}
      onCancel={onClose}
      width={720}
      rootClassName="mq-msg-modal"
      footer={
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => void loadDb()} loading={loading}>
            {t('userMq.refreshQueued')}
          </Button>
          <Button onClick={onClose}>{t('common.close')}</Button>
        </Space>
      }
    >
      {truncated ? (
        <p className="mq-msg-truncated-hint">{t('admin.mq.dbQueuedTruncated', { limit: 50, total })}</p>
      ) : null}
      <div ref={tableScrollRef} className="mq-msg-table-scroll">
        <Table<MqUserQueuedJobItem>
          className="mq-msg-table"
          size="small"
          sticky
          rowKey={(row) => `user-mq-${row.job_id}`}
          loading={loading}
          dataSource={items}
          pagination={false}
          locale={{ emptyText: t('userMq.emptyQueued') }}
          scroll={{ x: 560, y: tableScrollY }}
          columns={[
            {
              title: t('admin.mq.colJobId'),
              dataIndex: 'job_id',
              width: 88,
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
            {
              title: t('admin.mq.colActions'),
              key: 'actions',
              width: 88,
              render: (_: unknown, row) => (
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<CloseCircleOutlined />}
                  disabled={acting}
                  onClick={() => handleCancel(row)}
                >
                  {t('userMq.cancel')}
                </Button>
              ),
            },
          ]}
        />
      </div>
    </Modal>
  )
}
