import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { App, Button, Card, Col, Empty, InputNumber, Pagination, Progress, Row, Select, Space, Spin, Statistic, Table, Tag, Tooltip, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import type { TFunction } from 'i18next'
import type { EChartsOption } from 'echarts'
import * as echarts from 'echarts'
import { useTranslation } from 'react-i18next'
import {
  getAdminKbSearchEvalSamples,
  getAdminKbSearchEvalSummary,
  getAdminKbSearchEvalTrend,
  type KbSearchEvalSample,
  type KbSearchEvalStatus,
  type KbSearchEvalSummary,
  type KbSearchEvalTrendPoint,
} from '@/api/admin'
import { useFlexTableBodyScrollY } from '@/hooks/useFlexTableBodyScrollY'
import { echartsTooltipChrome } from '@/lib/chartTooltipStyle'
import './AdminPage.css'
import './KbSearchEval.css'

type DaysWindow = 1 | 7 | 14 | 30 | 90

const DAY_OPTIONS: DaysWindow[] = [1, 7, 14, 30, 90]
const STATUS_OPTIONS: KbSearchEvalStatus[] = ['succeeded', 'failed', 'skipped', 'running', 'pending']

function formatDate(value: string | null): string {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString()
}

function pct(value: number | null | undefined): string {
  if (value == null) return '-'
  return `${Math.round(value * 1000) / 10}%`
}

function scorePercent(value: number | null): number {
  if (value == null) return 0
  return Math.max(0, Math.min(100, Math.round(value * 100)))
}

function scoreStatus(value: number | null): 'success' | 'normal' | 'exception' {
  if (value == null) return 'normal'
  if (value < 0.5) return 'exception'
  if (value < 0.7) return 'normal'
  return 'success'
}

function chartThemeColors() {
  const root = document.documentElement
  const cs = getComputedStyle(root)
  return {
    isDark: root.getAttribute('data-theme') === 'dark',
    ink: cs.getPropertyValue('--text-primary').trim() || '#1d1d1f',
    muted: cs.getPropertyValue('--text-muted').trim() || '#6e6e73',
    grid: cs.getPropertyValue('--border-subtle').trim() || 'rgba(0,0,0,0.08)',
  }
}

function buildTrendOption(points: KbSearchEvalTrendPoint[], t: TFunction): EChartsOption {
  const { isDark, ink, muted, grid } = chartThemeColors()
  const reducedMotion = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const labels = points.map((point) => {
    const d = new Date(point.bucket)
    return Number.isNaN(d.getTime()) ? point.bucket : d.toLocaleDateString()
  })

  return {
    animation: !reducedMotion,
    grid: { left: 44, right: 18, top: 34, bottom: 34 },
    tooltip: {
      trigger: 'axis',
      ...echartsTooltipChrome(isDark),
      valueFormatter: (value) => (typeof value === 'number' ? pct(value) : '-'),
    },
    legend: {
      top: 0,
      textStyle: { color: muted, fontSize: 11 },
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: labels,
      axisLabel: { color: muted, fontSize: 11 },
      axisLine: { lineStyle: { color: grid } },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 1,
      axisLabel: { color: muted, fontSize: 11, formatter: (value: number) => `${Math.round(value * 100)}%` },
      splitLine: { lineStyle: { color: grid } },
    },
    series: [
      {
        name: t('admin.kbEval.faithfulness'),
        type: 'line',
        smooth: true,
        symbolSize: 6,
        itemStyle: { color: isDark ? '#65a8ff' : '#0071e3' },
        data: points.map((point) => point.avg_faithfulness),
      },
      {
        name: t('admin.kbEval.contextPrecision'),
        type: 'line',
        smooth: true,
        symbolSize: 6,
        itemStyle: { color: isDark ? '#49b07d' : '#2d7a52' },
        data: points.map((point) => point.avg_context_precision),
      },
    ],
    textStyle: { color: ink },
  }
}

function EvalTrendChart({ option }: { option: EChartsOption }) {
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

  return <div ref={ref} className="kb-eval-chart" role="img" aria-label="RAGAS score trend" />
}

function statusTag(status: KbSearchEvalStatus, t: TFunction) {
  const colors: Record<KbSearchEvalStatus, string> = {
    succeeded: 'success',
    failed: 'error',
    skipped: 'default',
    running: 'processing',
    pending: 'warning',
  }
  return <Tag color={colors[status]}>{t(`admin.kbEval.status.${status}`)}</Tag>
}

export default function KbSearchEvalPage() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const bodyRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [summary, setSummary] = useState<KbSearchEvalSummary | null>(null)
  const [trend, setTrend] = useState<KbSearchEvalTrendPoint[]>([])
  const [samples, setSamples] = useState<KbSearchEvalSample[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [days, setDays] = useState<DaysWindow>(7)
  const [status, setStatus] = useState<KbSearchEvalStatus | undefined>(undefined)
  const [workspaceId, setWorkspaceId] = useState<number | null>(null)
  const [userId, setUserId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [summaryRes, trendRes, samplesRes] = await Promise.all([
        getAdminKbSearchEvalSummary({ days }),
        getAdminKbSearchEvalTrend({ days }),
        getAdminKbSearchEvalSamples({
          days,
          status_filter: status,
          workspace_id: workspaceId ?? undefined,
          user_id: userId ?? undefined,
          limit: pageSize,
        }),
      ])
      setSummary(summaryRes.data)
      setTrend(trendRes.data.points)
      setSamples(samplesRes.data.items)
      setTotal(samplesRes.data.total)
    } catch (e) {
      message.error(String(e))
    } finally {
      setLoading(false)
    }
  }, [message, days, status, workspaceId, userId, pageSize])

  useEffect(() => {
    void load()
  }, [load])

  const trendOption = useMemo(() => buildTrendOption(trend, t), [trend, t])

  const scrollY = useFlexTableBodyScrollY([loading, samples.length, page, pageSize], {
    bodyRef,
  })
  const tableScroll = samples.length > 0 && scrollY > 0 ? { y: scrollY, x: 1500 as const } : { x: 1500 as const }

  const columns: ColumnsType<KbSearchEvalSample> = useMemo(
    () => [
      {
        title: t('admin.kbEval.sampleTime'),
        dataIndex: 'created_at',
        width: 170,
        render: (value: string | null) => formatDate(value),
      },
      {
        title: t('admin.kbEval.statusLabel'),
        dataIndex: 'status',
        width: 100,
        render: (value: KbSearchEvalStatus) => statusTag(value, t),
      },
      {
        title: t('admin.kbEval.query'),
        dataIndex: 'query_preview',
        ellipsis: true,
      },
      {
        title: t('admin.kbEval.answer'),
        dataIndex: 'answer_preview',
        ellipsis: true,
        width: 260,
      },
      {
        title: t('admin.kbEval.faithfulness'),
        dataIndex: 'faithfulness_score',
        width: 130,
        render: (value: number | null) => (
          <Progress percent={scorePercent(value)} size="small" status={scoreStatus(value)} format={() => pct(value)} />
        ),
      },
      {
        title: t('admin.kbEval.contextPrecision'),
        dataIndex: 'context_precision_score',
        width: 130,
        render: (value: number | null) => (
          <Progress percent={scorePercent(value)} size="small" status={scoreStatus(value)} format={() => pct(value)} />
        ),
      },
      {
        title: t('admin.kbEval.contexts'),
        dataIndex: 'context_count',
        width: 90,
      },
      {
        title: t('admin.kbEval.metric'),
        key: 'metric',
        width: 210,
        render: (_, row) => (
          <Tooltip title={`${row.metric_version ?? '-'}\nmodel=${row.llm_provider ?? '-'} / ${row.llm_model ?? '-'}\nqueue=${row.queue_duration_ms ?? '-'}ms · faithfulness=${row.faithfulness_duration_ms ?? '-'}ms · context_precision=${row.context_precision_duration_ms ?? '-'}ms · budget=${row.context_budget_version ?? '-'}`}>
            <span className="kb-eval-metric">{row.metric_variant}</span>
          </Tooltip>
        ),
      },
      {
        title: t('admin.kbEval.error'),
        key: 'error',
        width: 220,
        ellipsis: true,
        render: (_, row) => row.error_code ? `${row.failure_stage ?? '-'} · ${row.error_code}: ${row.error_message ?? ''}` : '-',
      },
    ],
    [t],
  )

  return (
    <div className="admin-root">
      <div className="admin-panel kb-eval-panel">
        <div className="admin-header">
          <div className="ah-title-group">
            <h2 className="ah-title">{t('admin.kbEval.title')}</h2>
            <p className="ah-sub">{t('admin.kbEval.subtitle')}</p>
          </div>
          <div className="ah-toolbar">
            <Space wrap>
              <Select
                value={days}
                style={{ width: 118 }}
                options={DAY_OPTIONS.map((value) => ({ value, label: t('admin.kbEval.days', { count: value }) }))}
                onChange={(value) => { setDays(value); setPage(1) }}
              />
              <Select
                allowClear
                value={status}
                placeholder={t('admin.kbEval.allStatuses')}
                style={{ width: 150 }}
                options={STATUS_OPTIONS.map((value) => ({ value, label: t(`admin.kbEval.status.${value}`) }))}
                onChange={(value) => { setStatus(value); setPage(1) }}
              />
              <InputNumber
                min={1}
                value={workspaceId}
                placeholder={t('admin.kbEval.workspaceId')}
                style={{ width: 140 }}
                onChange={(value) => { setWorkspaceId(value ?? null); setPage(1) }}
              />
              <InputNumber
                min={1}
                value={userId}
                placeholder={t('admin.kbEval.userId')}
                style={{ width: 140 }}
                onChange={(value) => { setUserId(value ?? null); setPage(1) }}
              />
              <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
                {t('admin.kbEval.refresh')}
              </Button>
            </Space>
          </div>
        </div>

        <div className="kb-eval-body">
          <div className="kb-eval-top">
            <Row gutter={[12, 12]}>
              <Col xs={12} md={6}>
                <Card size="small">
                  <Statistic title={t('admin.kbEval.total')} value={summary?.total_count ?? 0} />
                </Card>
              </Col>
              <Col xs={12} md={6}>
                <Card size="small">
                  <Statistic title={t('admin.kbEval.avgFaithfulness')} value={pct(summary?.avg_faithfulness)} />
                </Card>
              </Col>
              <Col xs={12} md={6}>
                <Card size="small">
                  <Statistic title={t('admin.kbEval.avgContextPrecision')} value={pct(summary?.avg_context_precision)} />
                </Card>
              </Col>
              <Col xs={12} md={6}>
                <Card size="small">
                  <Statistic title={t('admin.kbEval.failureRate')} value={pct(summary?.failure_rate)} />
                </Card>
              </Col>
            </Row>

            <div className="kb-eval-runtime">
              <Tag color={summary?.enabled ? 'processing' : 'default'}>
                {summary?.enabled ? t('admin.kbEval.enabled') : t('admin.kbEval.disabled')}
              </Tag>
              <span>{t('admin.kbEval.sampleRate', { value: pct(summary?.sample_rate) })}</span>
              <span>{t('admin.kbEval.timeout', { value: summary?.timeout_seconds ?? '-' })}</span>
              <span>{t('admin.kbEval.countBreakdown', {
                succeeded: summary?.succeeded_count ?? 0,
                failed: summary?.failed_count ?? 0,
                skipped: summary?.skipped_count ?? 0,
              })}</span>
            </div>

            <Card size="small" title={t('admin.kbEval.trendTitle')} className="kb-eval-chart-card">
              {trend.length > 0 ? <EvalTrendChart option={trendOption} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />}
            </Card>

            <div className="kb-eval-section-head">
              <Typography.Text strong>{t('admin.kbEval.samplesTitle')}</Typography.Text>
              <Typography.Text type="secondary">{t('admin.kbEval.samplesHint')}</Typography.Text>
            </div>
          </div>

          <div className="admin-table-wrap admin-table-wrap--flex fl-table-shell kb-eval-table-shell">
            <div className="fl-body" ref={bodyRef}>
              <Spin spinning={loading} className="fl-spin">
                <div className="fl-table-host">
                  <Table<KbSearchEvalSample>
                    className="fl-file-table"
                    size="small"
                    rowKey="id"
                    columns={columns}
                    dataSource={samples}
                    pagination={false}
                    scroll={tableScroll}
                    locale={{
                      emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('admin.kbEval.noSamples')} />,
                    }}
                  />
                </div>
              </Spin>
            </div>
            {!loading && total > 0 && (
              <div className="fl-pager">
                <Pagination
                  current={page}
                  defaultCurrent={1}
                  pageSize={pageSize}
                  total={total}
                  showSizeChanger
                  pageSizeOptions={['10', '20', '50', '100']}
                  onChange={(p, ps) => {
                    setPage(p)
                    if (ps !== pageSize) {
                      setPageSize(ps)
                      setPage(1)
                    }
                  }}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
