import { LinkOutlined, ReloadOutlined } from '@ant-design/icons'
import { Button, Spin, Tag } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import MqClassicQueueGroups from '@/components/mq/MqClassicQueueGroups'
import MqFactoryView from '@/components/mq/factory/MqFactoryView'
import MqMonitorTabNav from '@/components/mq/MqMonitorTabNav'
import {
  ADMIN_QUEUE_GROUPS,
  formatMqUpdatedAt,
  mainQueueDbSource,
  queueSortIndex,
  type MainQueueDbSource,
} from '@/components/mq/MqQueueCard'
import { useMqMonitorTab } from '@/hooks/useMqMonitorTab'
import { useMqStatus } from '@/providers/MqStatusProvider'
import MqQueueMessagesModal from './MqQueueMessagesModal'
import './AdminPage.css'
import './MqMonitor.css'

export default function AdminMqMonitorPage() {
  const { t } = useTranslation()
  const { data, loading, refreshing, requestRefresh, lastReceivedAt } = useMqStatus()
  const displayUpdatedAt = lastReceivedAt || data?.updated_at || ''
  const [tab, setTab] = useMqMonitorTab()
  const [msgModal, setMsgModal] = useState<{
    open: boolean
    queueName: string
    queueLabel: string
    queueKey: string
    dbSource: MainQueueDbSource
  }>({ open: false, queueName: '', queueLabel: '', queueKey: '', dbSource: null })

  const openMessages = (
    queueName: string,
    queueLabel: string,
    queueKey: string,
    dbSource: MainQueueDbSource,
  ) => {
    setMsgModal({ open: true, queueName, queueLabel, queueKey, dbSource })
  }

  const sortedQueues = data?.queues
    ? [...data.queues].sort((a, b) => queueSortIndex(a.label) - queueSortIndex(b.label))
    : []

  return (
    <div className="admin-root">
      <div className="admin-panel mq-panel">
        <div className="admin-header admin-header--compact mq-panel-header mq-panel-header--with-tabs">
          <div className="mq-panel-header__lead">
            <div className="mq-panel-header__title-row">
              <h2 className="ah-title">{t('admin.mq.title')}</h2>
              <MqMonitorTabNav
                tab={tab}
                onChange={setTab}
                factoryLabel={t('admin.mq.tabFactory')}
                classicLabel={t('admin.mq.tabClassic')}
              />
            </div>
            <span className="ah-sub mq-panel-sub">{t('admin.mq.subtitle')}</span>
          </div>
          <Button type="primary" size="small" icon={<ReloadOutlined spin={refreshing} />} onClick={requestRefresh}>
            {t('admin.mq.reconnect')}
          </Button>
        </div>

        <Spin spinning={loading && !data} wrapperClassName="mq-body-spin">
          <div className="mq-body">
            <div className="mq-conn-strip">
              <div className="mq-conn-strip-main">
                <span className="mq-conn-label">
                  <LinkOutlined aria-hidden /> {t('admin.mq.connection')}
                </span>
                <Tag color={data?.connected ? 'success' : 'error'}>
                  {data?.connected ? t('admin.mq.connected') : t('admin.mq.disconnected')}
                </Tag>
                <code className="mq-broker-val">{data?.broker_display || '—'}</code>
              </div>
              <span className="mq-updated">{t('admin.mq.lastUpdate', { time: formatMqUpdatedAt(displayUpdatedAt) })}</span>
            </div>
            {data?.error ? <div className="mq-error">{data.error}</div> : null}

            <div className="mq-monitor-tab-content">
              {tab === 'factory' ? (
                <MqFactoryView
                  sortedQueues={sortedQueues}
                  activeTasks={data?.active_tasks ?? []}
                  systemResources={data?.system_resources}
                  mode="admin"
                  t={t}
                  onViewMessages={openMessages}
                />
              ) : (
                <MqClassicQueueGroups
                  groups={ADMIN_QUEUE_GROUPS}
                  sortedQueues={sortedQueues}
                  activeTasks={data?.active_tasks ?? []}
                  t={t}
                  groupsLabel={t('admin.mq.allQueues')}
                  onViewMessages={openMessages}
                />
              )}
            </div>
          </div>
        </Spin>
      </div>

      <MqQueueMessagesModal
        open={msgModal.open}
        queueName={msgModal.queueName}
        queueLabel={msgModal.queueLabel}
        queueKey={msgModal.queueKey}
        dbSource={msgModal.dbSource}
        activeTasks={data?.active_tasks ?? []}
        onClose={() => setMsgModal((s) => ({ ...s, open: false }))}
        onMutated={requestRefresh}
      />
    </div>
  )
}
