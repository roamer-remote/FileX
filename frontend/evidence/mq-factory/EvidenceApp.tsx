import { LinkOutlined, ReloadOutlined } from '@ant-design/icons'
import { Button, Tag } from 'antd'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import MqClassicQueueGroups from '@/components/mq/MqClassicQueueGroups'
import MqFactoryView from '@/components/mq/factory/MqFactoryView'
import MqMonitorTabNav from '@/components/mq/MqMonitorTabNav'
import {
  ADMIN_QUEUE_GROUPS,
  USER_QUEUE_GROUPS,
  queueSortIndex,
} from '@/components/mq/MqQueueCard'
import type { MqMonitorTab } from '@/hooks/useMqMonitorTab'
import {
  buildEvidenceActiveTasks,
  buildEvidenceQueuedPreviews,
  buildEvidenceQueues,
  buildEvidenceSystemResources,
  type EvidenceScene,
} from './fixtures'
import '@/pages/admin/AdminPage.css'
import '@/pages/admin/MqMonitor.css'

type EvidenceAppProps = {
  mode: 'admin' | 'user'
  scene?: EvidenceScene
}

/** 与 /admin/mq 同壳：标题、连接条、Tab；仅数据为 fixture。 */
export default function EvidenceApp({ mode, scene = 'default' }: EvidenceAppProps) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<MqMonitorTab>('factory')
  const sortedQueues = useMemo(
    () => [...buildEvidenceQueues(scene)].sort((a, b) => queueSortIndex(a.label) - queueSortIndex(b.label)),
    [scene],
  )
  const activeTasks = useMemo(() => buildEvidenceActiveTasks(scene), [scene])
  const queuedPreviewsOverride = useMemo(() => buildEvidenceQueuedPreviews(scene), [scene])
  const systemResources = useMemo(() => buildEvidenceSystemResources(), [])
  const groups = mode === 'admin' ? ADMIN_QUEUE_GROUPS : USER_QUEUE_GROUPS

  return (
    <div className="admin-root">
      <div className="admin-panel mq-panel">
        <div className="admin-header admin-header--compact mq-panel-header mq-panel-header--with-tabs">
          <div className="mq-panel-header__lead">
            <div className="mq-panel-header__title-row">
              <h2 className="ah-title">{mode === 'admin' ? t('admin.mq.title') : t('userMq.title')}</h2>
              <MqMonitorTabNav
                tab={tab}
                onChange={setTab}
                factoryLabel={t('admin.mq.tabFactory')}
                classicLabel={t('admin.mq.tabClassic')}
              />
            </div>
            <span className="ah-sub mq-panel-sub">
              {mode === 'admin' ? t('admin.mq.subtitle') : t('userMq.subtitle')}
            </span>
          </div>
          <Button type="primary" size="small" icon={<ReloadOutlined />}>
            {t('admin.mq.reconnect')}
          </Button>
        </div>

        <div className="mq-body">
          <div className="mq-conn-strip">
            <div className="mq-conn-strip-main">
              <span className="mq-conn-label">
                <LinkOutlined aria-hidden /> {t('admin.mq.connection')}
              </span>
              <Tag color="success">{t('admin.mq.connected')}</Tag>
              <code className="mq-broker-val">amqp://admin:***@10.0.11.5:5672/%2f</code>
            </div>
            <span className="mq-updated">{t('admin.mq.lastUpdate', { time: '17:28:46' })}</span>
          </div>

          <div className="mq-monitor-tab-content">
            {tab === 'factory' ? (
              <MqFactoryView
                sortedQueues={sortedQueues}
                activeTasks={activeTasks}
                systemResources={mode === 'admin' ? systemResources : undefined}
                queuedPreviewsOverride={queuedPreviewsOverride}
                mode={mode}
                showSidecarStations={mode === 'admin'}
                t={t}
                onViewMessages={() => {}}
              />
            ) : (
              <MqClassicQueueGroups
                groups={groups}
                sortedQueues={sortedQueues}
                activeTasks={activeTasks}
                t={t}
                groupsLabel={t('admin.mq.allQueues')}
                onViewMessages={() => {}}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
