import { LinkOutlined, ReloadOutlined } from '@ant-design/icons'
import { Button, Spin, Tag } from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import type { UserMqMessageQueueLabel } from '@/api/mq'
import MqClassicQueueGroups from '@/components/mq/MqClassicQueueGroups'
import MqFactoryView from '@/components/mq/factory/MqFactoryView'
import MqMonitorTabNav from '@/components/mq/MqMonitorTabNav'
import {
  formatMqUpdatedAt,
  mainQueueDbSource,
  MqSidecarActiveTasks,
  queueSortIndex,
  USER_MQ_MESSAGE_LABELS,
  USER_QUEUE_GROUPS,
  type MainQueueDbSource,
} from '@/components/mq/MqQueueCard'
import { useMqMonitorTab } from '@/hooks/useMqMonitorTab'
import { useMqStatus } from '@/providers/MqStatusProvider'
import { useAuthStore } from '@/stores/authStore'
import MqUserQueueDetailsModal from './MqUserQueueDetailsModal'
import MqUserQueueMessagesModal from './MqUserQueueMessagesModal'
import '@/pages/admin/AdminPage.css'
import '@/pages/admin/MqMonitor.css'
import './MqTaskMonitor.css'

type DetailModalState =
  | { open: false }
  | { open: true; mode: 'db'; queueLabel: string; dbSource: Exclude<MainQueueDbSource, null> }
  | { open: true; mode: 'mq'; queueLabel: string; mqQueueLabel: UserMqMessageQueueLabel }

export default function MqTaskMonitorPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const isAdmin = useAuthStore((s) => s.user?.is_admin === true)
  const { data, loading, refreshing, requestRefresh, lastReceivedAt } = useMqStatus()
  const displayUpdatedAt = lastReceivedAt || data?.updated_at || ''
  const [tab, setTab] = useMqMonitorTab()
  const [detailModal, setDetailModal] = useState<DetailModalState>({ open: false })

  useEffect(() => {
    if (isAdmin) {
      navigate('/admin/mq', { replace: true })
    }
  }, [isAdmin, navigate])

  const openDetails = (
    _queueName: string,
    queueLabel: string,
    queueKey: string,
    dbSource: MainQueueDbSource,
  ) => {
    if (dbSource) {
      setDetailModal({ open: true, mode: 'db', queueLabel, dbSource })
      return
    }
    if (USER_MQ_MESSAGE_LABELS.has(queueKey)) {
      setDetailModal({
        open: true,
        mode: 'mq',
        queueLabel,
        mqQueueLabel: queueKey as UserMqMessageQueueLabel,
      })
    }
  }

  const sortedQueues = data?.queues
    ? [...data.queues].sort((a, b) => queueSortIndex(a.label) - queueSortIndex(b.label))
    : []

  if (isAdmin) {
    return null
  }

  return (
    <div className="admin-root user-mq-root">
      <div className="admin-panel mq-panel">
        <div className="admin-header admin-header--compact mq-panel-header mq-panel-header--with-tabs">
          <div className="mq-panel-header__lead">
            <div className="mq-panel-header__title-row">
              <h2 className="ah-title">{t('userMq.title')}</h2>
              <MqMonitorTabNav
                tab={tab}
                onChange={setTab}
                factoryLabel={t('admin.mq.tabFactory')}
                classicLabel={t('admin.mq.tabClassic')}
              />
            </div>
            <span className="ah-sub mq-panel-sub">{t('userMq.subtitle')}</span>
          </div>
          <Button
            type="primary"
            size="small"
            icon={<ReloadOutlined spin={refreshing} />}
            onClick={() => requestRefresh()}
          >
            {t('admin.mq.reconnect')}
          </Button>
        </div>

        <Spin spinning={loading && !data} wrapperClassName="mq-body-spin">
          <div className="mq-body">
            <div className="mq-conn-strip">
              <div className="mq-conn-strip-main">
                <span className="mq-conn-label">
                  <LinkOutlined aria-hidden /> {t('userMq.connection')}
                </span>
                <Tag color={data?.connected ? 'success' : 'error'}>
                  {data?.connected ? t('admin.mq.connected') : t('admin.mq.disconnected')}
                </Tag>
              </div>
              <span className="mq-updated">
                {t('admin.mq.lastUpdate', { time: formatMqUpdatedAt(displayUpdatedAt) })}
              </span>
            </div>
            {data?.error ? <div className="mq-error">{data.error}</div> : null}

            <div className="mq-monitor-tab-content">
              {tab === 'factory' ? (
                <MqFactoryView
                  sortedQueues={sortedQueues}
                  activeTasks={data?.active_tasks ?? []}
                  mode="user"
                  showSidecarStations={false}
                  t={t}
                  onViewMessages={openDetails}
                />
              ) : (
                <MqClassicQueueGroups
                  groups={USER_QUEUE_GROUPS}
                  sortedQueues={sortedQueues}
                  activeTasks={data?.active_tasks ?? []}
                  t={t}
                  mode="user"
                  groupsLabel={t('userMq.allQueues')}
                  onViewMessages={openDetails}
                  trailing={<MqSidecarActiveTasks activeTasks={data?.active_tasks ?? []} t={t} />}
                />
              )}
            </div>
          </div>
        </Spin>
      </div>

      {detailModal.open && detailModal.mode === 'db' ? (
        <MqUserQueueDetailsModal
          open
          queueLabel={detailModal.queueLabel}
          dbSource={detailModal.dbSource}
          onClose={() => setDetailModal({ open: false })}
          onMutated={requestRefresh}
        />
      ) : null}
      {detailModal.open && detailModal.mode === 'mq' ? (
        <MqUserQueueMessagesModal
          open
          queueLabel={detailModal.queueLabel}
          mqQueueLabel={detailModal.mqQueueLabel}
          onClose={() => setDetailModal({ open: false })}
          onMutated={requestRefresh}
        />
      ) : null}
    </div>
  )
}
