import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Row,
  Segmented,
  Spin,
  Statistic,
  Table,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { EChartsOption } from 'echarts'
import * as echarts from 'echarts'
import { ReloadOutlined } from '@ant-design/icons'
import {
  getKbPipelineMetrics,
  type PipelineMetricsResponse,
  type PipelineMetricsWindow,
  type PipelineRecentEvent,
  type ProviderFailureStat,
} from '@/api/admin'
import { formatDate } from '@/utils'
import { adminLogsOperationPath } from '@/pages/admin/adminLogsTabs'
import {
  STAGE_MS_I18N_KEYS,
  buildStageMsBarOption,
  buildThroughputBarOption,
  collectStageMsEntries,
  hasAnyStageMs,
  throughputFromKpis,
} from '@/utils/kbPipelineMonitorCharts'
import './KbPipelineMonitor.css'

const WINDOW_OPTIONS: PipelineMetricsWindow[] = ['1h', '24h', '7d']

const KPI_LABEL_KEYS: Record<string, string> = {
  extract_queue_depth: 'admin.settings.pipelineMonitorKpiExtractQueue',
  index_queue_depth: 'admin.settings.pipelineMonitorKpiIndexQueue',
  extract_done_24h: 'admin.settings.pipelineMonitorKpiExtractDone',
  index_done_24h: 'admin.settings.pipelineMonitorKpiIndexDone',
  extract_failures_24h: 'admin.settings.pipelineMonitorKpiExtractFailures',
  index_failures_24h: 'admin.settings.pipelineMonitorKpiIndexFailures',
  dlq_total: 'admin.settings.pipelineMonitorKpiDlq',
}

const WARNING_KEYS: Record<string, string> = {
  dlq_nonzero: 'admin.settings.pipelineMonitorWarnDlq',
  extract_queue_backlog: 'admin.settings.pipelineMonitorWarnExtractQueue',
  index_queue_backlog: 'admin.settings.pipelineMonitorWarnIndexQueue',
  provider_failure_rate: 'admin.settings.pipelineMonitorWarnProviderRate',
}

function MonitorBarChart({ option, className }: { option: EChartsOption; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    chartRef.current?.dispose()
    chartRef.current = echarts.init(el)
    chartRef.current.setOption(option)
    const resize = () => chartRef.current?.resize()
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null
    observer?.observe(el)
    window.addEventListener('resize', resize)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', resize)
      chartRef.current?.dispose()
      chartRef.current = null
    }
  }, [option])

  return <div ref={ref} className={className} role="img" aria-hidden />
}

export default function KbPipelineMonitor() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [window, setWindow] = useState<PipelineMetricsWindow>('24h')
  const [data, setData] = useState<PipelineMetricsResponse | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getKbPipelineMetrics(window)
      setData(res.data)
    } catch (e) {
      message.error(String(e))
    } finally {
      setLoading(false)
    }
  }, [message, window])

  useEffect(() => {
    void load()
  }, [load])

  const throughputOption = useMemo(() => {
    if (!data) return null
    return buildThroughputBarOption(throughputFromKpis(data.kpis), t)
  }, [data, t])

  const stageEntries = useMemo(
    () => (data ? collectStageMsEntries(data.avg_stage_ms) : []),
    [data],
  )

  const stageOption = useMemo(() => {
    if (stageEntries.length === 0) return null
    return buildStageMsBarOption(stageEntries, t)
  }, [stageEntries, t])

  const providerColumns = useMemo<ColumnsType<ProviderFailureStat>>(
    () => [
      {
        title: t('admin.settings.pipelineMonitorProvider'),
        dataIndex: 'provider',
        key: 'provider',
      },
      {
        title: t('admin.settings.pipelineMonitorFailures'),
        dataIndex: 'failure_count',
        key: 'failure_count',
      },
      {
        title: t('admin.settings.pipelineMonitorSuccesses'),
        dataIndex: 'success_count',
        key: 'success_count',
      },
      {
        title: t('admin.settings.pipelineMonitorFailureRate'),
        key: 'failure_rate',
        render: (_, row) => `${Math.round(row.failure_rate * 1000) / 10}%`,
      },
    ],
    [t],
  )

  const eventColumns = useMemo<ColumnsType<PipelineRecentEvent>>(
    () => [
      {
        title: t('admin.settings.pipelineMonitorEventTime'),
        dataIndex: 'created_at',
        key: 'created_at',
        width: 170,
        render: (value: string) => formatDate(value),
      },
      {
        title: t('admin.settings.pipelineMonitorEventAction'),
        dataIndex: 'action',
        key: 'action',
      },
      {
        title: t('admin.settings.pipelineMonitorEventUser'),
        key: 'user',
        width: 120,
        render: (_, row) => row.username || `#${row.user_id}`,
      },
      {
        title: t('admin.settings.pipelineMonitorEventFile'),
        dataIndex: 'target_id',
        key: 'target_id',
        width: 90,
        render: (value: number | null) => (value != null ? `#${value}` : '—'),
      },
      {
        title: t('admin.settings.pipelineMonitorEventDetail'),
        dataIndex: 'detail',
        key: 'detail',
        ellipsis: true,
      },
      {
        title: t('admin.settings.pipelineMonitorEventLink'),
        key: 'link',
        width: 90,
        render: (_, row) => (
          <Link to={row.log_deep_link}>{t('admin.settings.pipelineMonitorViewLogs')}</Link>
        ),
      },
    ],
    [t],
  )

  if (loading && !data) {
    return (
      <div className="kb-pipeline-monitor kb-pipeline-monitor--loading">
        <Spin />
      </div>
    )
  }

  if (!data) return null

  return (
    <section className="kb-pipeline-monitor" aria-label={t('admin.settings.pipelineMonitorTitle')}>
      <header className="kb-pipeline-monitor__header">
        <div>
          <Typography.Text strong className="admin-settings-subsection__title kb-pipeline-monitor__title">
            {t('admin.settings.pipelineMonitorTitle')}
          </Typography.Text>
          <Typography.Text type="secondary" className="kb-pipeline-monitor__hint admin-settings-subsection__desc">
            {t('admin.settings.pipelineMonitorHint')}
          </Typography.Text>
        </div>
        <div className="kb-pipeline-monitor__toolbar">
          <Segmented
            size="small"
            value={window}
            options={WINDOW_OPTIONS.map((value) => ({
              value,
              label: t(`admin.settings.pipelineMonitorWindow${value}`),
            }))}
            onChange={(value) => setWindow(value as PipelineMetricsWindow)}
          />
          <Button size="small" icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
            {t('admin.settings.pipelineMonitorRefresh')}
          </Button>
        </div>
      </header>

      {data.warnings.length > 0 ? (
        <Alert
          type="warning"
          showIcon
          className="kb-pipeline-monitor__alert"
          message={t('admin.settings.pipelineMonitorWarningsTitle')}
          description={
            <ul className="kb-pipeline-monitor__warnings">
              {data.warnings.map((key) => (
                <li key={key}>{t(WARNING_KEYS[key] ?? key)}</li>
              ))}
            </ul>
          }
        />
      ) : null}

      <Row gutter={[12, 12]} className="kb-pipeline-monitor__kpis">
        {data.kpis.map((kpi) => (
          <Col xs={12} sm={8} lg={6} key={kpi.key}>
            <Card
              size="small"
              className={
                'kb-pipeline-monitor__kpi' + (kpi.warning ? ' kb-pipeline-monitor__kpi--warning' : '')
              }
            >
              <Statistic
                title={t(KPI_LABEL_KEYS[kpi.key] ?? kpi.key)}
                value={kpi.value}
              />
              {kpi.deep_link ? (
                <Link to={kpi.deep_link} className="kb-pipeline-monitor__kpi-link">
                  {t('admin.settings.pipelineMonitorOpenDetail')}
                </Link>
              ) : null}
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[12, 12]} className="kb-pipeline-monitor__charts">
        <Col xs={24} lg={12}>
          <Card size="small" title={t('admin.settings.pipelineMonitorChartThroughput')}>
            {throughputOption ? (
              <MonitorBarChart option={throughputOption} className="kb-pipeline-monitor__chart" />
            ) : null}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card size="small" title={t('admin.settings.pipelineMonitorChartStageMs')}>
            {stageOption ? (
              <MonitorBarChart option={stageOption} className="kb-pipeline-monitor__chart" />
            ) : (
              <Typography.Text type="secondary">{t('admin.settings.pipelineMonitorAvgEmpty')}</Typography.Text>
            )}
          </Card>
        </Col>
      </Row>

      <div className="kb-pipeline-monitor__section">
        <Typography.Text strong className="admin-settings-subsection__title">
          {t('admin.settings.pipelineMonitorAvgStage')}
        </Typography.Text>
        <div className="kb-pipeline-monitor__avg-grid">
          {hasAnyStageMs(data.avg_stage_ms) ? (
            collectStageMsEntries(data.avg_stage_ms).map((entry) => (
              <span key={entry.key}>
                {t(STAGE_MS_I18N_KEYS[entry.key], { ms: entry.ms })}
              </span>
            ))
          ) : (
            <Typography.Text type="secondary">{t('admin.settings.pipelineMonitorAvgEmpty')}</Typography.Text>
          )}
        </div>
      </div>

      <div className="kb-pipeline-monitor__section">
        <Typography.Text strong className="admin-settings-subsection__title">
          {t('admin.settings.pipelineMonitorProviderStats')}
        </Typography.Text>
        <Table
          className="admin-settings-pipeline-table"
          size="small"
          rowKey="provider"
          pagination={false}
          columns={providerColumns}
          dataSource={data.provider_failures}
          locale={{ emptyText: t('admin.settings.pipelineMonitorProviderEmpty') }}
        />
      </div>

      <div className="kb-pipeline-monitor__section">
        <div className="kb-pipeline-monitor__section-head">
          <Typography.Text strong className="admin-settings-subsection__title">
            {t('admin.settings.pipelineMonitorRecentEvents')}
          </Typography.Text>
          <Link to={adminLogsOperationPath()} className="kb-pipeline-monitor__section-link">
            {t('admin.settings.pipelineMonitorAllLogs')}
          </Link>
        </div>
        <Table
          className="admin-settings-pipeline-table"
          size="small"
          rowKey="id"
          pagination={false}
          columns={eventColumns}
          dataSource={data.recent_events}
          scroll={{ x: 960 }}
        />
      </div>

      <Typography.Text type="secondary" className="kb-pipeline-monitor__meta">
        {t('admin.settings.pipelineMonitorGeneratedAt', {
          time: formatDate(data.generated_at),
          cached: data.cached ? t('admin.settings.pipelineMonitorCachedYes') : '',
        })}
      </Typography.Text>
    </section>
  )
}
