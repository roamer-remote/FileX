import { DeleteActionIcon } from '@/components/DeleteActionIcon'
import { ReloadOutlined } from '@ant-design/icons'
import { App, Button, Modal, Space, Table, Tooltip } from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  getUserMqQueueMessages,
  removeUserMqQueueMessage,
  type MqUserQueueMessageItem,
  type UserMqMessageQueueLabel,
} from '@/api/mq'
import '@/pages/admin/MqQueueMessagesModal.css'

const AUTO_REFRESH_MS = 5000

type Props = {
  open: boolean
  queueLabel: string
  mqQueueLabel: UserMqMessageQueueLabel
  onClose: () => void
  onMutated: () => void
}

export default function MqUserQueueMessagesModal({
  open,
  queueLabel,
  mqQueueLabel,
  onClose,
  onMutated,
}: Props) {
  const { modal, message } = App.useApp()
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [items, setItems] = useState<MqUserQueueMessageItem[]>([])
  const [total, setTotal] = useState(0)
  const [truncated, setTruncated] = useState(false)
  const [acting, setActing] = useState(false)

  const load = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!opts?.silent) setLoading(true)
      try {
        const res = await getUserMqQueueMessages(mqQueueLabel)
        setItems(res.data.items)
        setTotal(res.data.total)
        setTruncated(res.data.truncated)
      } catch {
        if (!opts?.silent) message.error(t('userMq.loadFailed'))
        setItems([])
        setTotal(0)
        setTruncated(false)
      } finally {
        if (!opts?.silent) setLoading(false)
      }
    },
    [message, mqQueueLabel, t],
  )

  useEffect(() => {
    if (!open) return
    void load()
    const timer = window.setInterval(() => {
      if (acting) return
      void load({ silent: true })
    }, AUTO_REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [open, load, onMutated, acting])

  const handleRemove = (row: MqUserQueueMessageItem) => {
    if (row.job_id == null) return
    modal.confirm({
      title: t('userMq.removeConfirmTitle'),
      content: t('userMq.removeConfirmContent', { jobId: row.job_id }),
      okText: t('userMq.removeOk'),
      okType: 'danger',
      cancelText: t('common.cancel'),
      onOk: async () => {
        setActing(true)
        try {
          const res = await removeUserMqQueueMessage(mqQueueLabel, row.job_id!)
          if (res.data.removed < 1) {
            message.warning(t('userMq.removeNotFound'))
          } else {
            message.success(t('userMq.removeSuccess'))
          }
          await load()
          onMutated()
        } catch {
          message.error(t('userMq.removeFailed'))
        } finally {
          setActing(false)
        }
      },
    })
  }

  return (
    <Modal
      open={open}
      title={t('admin.mq.messagesTitle', { queue: queueLabel })}
      onCancel={onClose}
      width={720}
      rootClassName="mq-msg-modal"
      footer={
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
            {t('userMq.refreshQueued')}
          </Button>
          <Button onClick={onClose}>{t('common.close')}</Button>
        </Space>
      }
    >
      {truncated ? (
        <p className="mq-msg-truncated-hint">{t('userMq.messagesTruncated', { total })}</p>
      ) : null}
      <Table<MqUserQueueMessageItem>
        className="mq-msg-table"
        size="small"
        rowKey={(row) => `user-mq-msg-${row.job_id ?? row.index}`}
        loading={loading}
        dataSource={items}
        pagination={false}
        locale={{ emptyText: t('admin.mq.messagesEmpty') }}
        scroll={{ x: 640, y: 360 }}
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
            render: (_: unknown, row) =>
              row.job_id != null ? (
                <Tooltip title={t('userMq.removeMessage')}>
                  <Button
                    type="link"
                    danger
                    size="small"
                    icon={<DeleteActionIcon />}
                    disabled={acting}
                    onClick={() => handleRemove(row)}
                  />
                </Tooltip>
              ) : null,
          },
        ]}
      />
    </Modal>
  )
}
