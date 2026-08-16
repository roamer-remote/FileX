import { LoadingOutlined, RadarChartOutlined } from '@ant-design/icons'
import { Button, Spin, Tag, Tooltip } from 'antd'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import type { MqQueueStatus } from '@/api/admin'
import { useMqStatus } from '@/providers/MqStatusProvider'
import { useAuthStore } from '@/stores/authStore'
import { mqBacklogBreakdown, shouldShowMqWaiting } from '@/utils/mqQueueMetrics'
import './SidebarMqQueue.css'

function SidebarMqStatusTags({
  q,
  t,
  ignoreMessageCount,
}: {
  q: MqQueueStatus
  t: (key: string) => string
  ignoreMessageCount?: boolean
}) {
  const showWaiting = shouldShowMqWaiting(q, { ignoreMessageCount })
  if (!showWaiting && !q.consumer_busy) return null

  return (
    <>
      {showWaiting ? (
        <Tag className="sidebar-mq-running-tag" color="warning">
          {t('admin.mq.consumerWaiting')}
        </Tag>
      ) : null}
      {q.consumer_busy ? (
        <Tag className="sidebar-mq-running-tag" color="processing" icon={<LoadingOutlined spin />}>
          {t('admin.mq.consumerRunning')}
        </Tag>
      ) : null}
    </>
  )
}

function SidebarMainQueueCard({
  q,
  title,
  t,
}: {
  q: MqQueueStatus
  title: string
  t: (key: string, opts?: Record<string, unknown>) => string
}) {
  const { total } = mqBacklogBreakdown(q)

  return (
    <div className="sidebar-mq-queue-card">
      <div className="sidebar-mq-queue-head">
        <span className="sidebar-mq-queue-title">{title}</span>
        <span className={`sidebar-mq-status-pill ${q.online ? 'sidebar-mq-status-pill--on' : ''}`}>
          {q.online ? t('admin.mq.online') : t('admin.mq.offline')}
        </span>
      </div>
      <div className="sidebar-mq-stats">
        <div className="sidebar-mq-stat">
          <Tooltip title={t('admin.mq.backlogTotalTip')}>
            <span className="sidebar-mq-stat-label sidebar-mq-stat-label--tip">
              {t('admin.mq.backlogTotal')}
            </span>
          </Tooltip>
          <span className="sidebar-mq-stat-value">{total}</span>
        </div>
      </div>
    </div>
  )
}

export default function SidebarMqQueue() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const isAdmin = useAuthStore((s) => s.user?.is_admin === true)
  const { data, loading } = useMqStatus()

  const indexMain = data?.queues.find((q) => q.label === 'index_main')
  const extractMain = data?.queues.find((q) => q.label === 'extract_main')
  const postMain = data?.queues.find((q) => q.label === 'post_main')
  const hasQueueSummary = Boolean(indexMain || extractMain || postMain)
  const activeQueues = [extractMain, indexMain, postMain].filter((q): q is MqQueueStatus => Boolean(q))
  const hasStatusTags = activeQueues.some(
    (q) => shouldShowMqWaiting(q, { ignoreMessageCount: !isAdmin }) || q.consumer_busy,
  )
  const showSectionFoot = hasStatusTags || hasQueueSummary

  return (
    <div className="sidebar-panel-section sidebar-mq-section">
      <div className="sidebar-panel-card sidebar-mq-card double-bezel-shell">
        {loading && !data ? (
          <div className="sidebar-mq-loading">
            <Spin size="small" />
          </div>
        ) : (
          <>
            {hasQueueSummary ? (
              <>
                <div className="sidebar-mq-queue-stack">
                  {extractMain ? (
                    <SidebarMainQueueCard
                      q={extractMain}
                      title={t('sidebarMq.extractTitle')}
                      t={t}
                    />
                  ) : null}
                  {indexMain ? (
                    <SidebarMainQueueCard
                      q={indexMain}
                      title={t('sidebarMq.indexTitle')}
                      t={t}
                    />
                  ) : null}
                  {postMain ? (
                    <SidebarMainQueueCard
                      q={postMain}
                      title={t('sidebarMq.postTitle')}
                      t={t}
                    />
                  ) : null}
                </div>
                {showSectionFoot ? (
                  <div className="sidebar-mq-queue-foot">
                    <div className="sidebar-mq-queue-foot-tags">
                      {extractMain ? (
                        <SidebarMqStatusTags q={extractMain} t={t} ignoreMessageCount={!isAdmin} />
                      ) : null}
                      {indexMain ? (
                        <SidebarMqStatusTags q={indexMain} t={t} ignoreMessageCount={!isAdmin} />
                      ) : null}
                      {postMain ? (
                        <SidebarMqStatusTags q={postMain} t={t} ignoreMessageCount={!isAdmin} />
                      ) : null}
                    </div>
                    <Button
                      type="link"
                      size="small"
                      className="sidebar-mq-monitor-btn"
                      icon={<RadarChartOutlined />}
                      onClick={() => navigate(isAdmin ? '/admin/mq' : '/mq')}
                    >
                      {isAdmin ? t('sidebarMq.openMonitor') : t('sidebarMq.openUserMonitor')}
                    </Button>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="sidebar-mq-empty">{t('sidebarMq.unavailable')}</p>
            )}
            {data?.error ? <p className="sidebar-mq-error">{data.error}</p> : null}
            {!data?.connected && !data?.error ? (
              <p className="sidebar-mq-hint">{t('admin.mq.disconnected')}</p>
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}
