import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { useNavigate } from 'react-router-dom'
import { Spin } from 'antd'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { getFileStats, type FileStatsPayload, type FileTypeStatItem } from '@/api/files'
import { LIBRARY_STATS_REFRESH } from '@/lib/libraryEvents'
import { echartsTooltipChrome } from '@/lib/chartTooltipStyle'
import { useThemeStore } from '@/stores/themeStore'
import './SidebarStats.css'

const TYPE_BAR_COLORS: Record<string, string> = {
  pdf: '#2d7a52',
  img: '#3d9468',
  docx: '#4a9f72',
  md: '#5aad82',
  pptx: '#6bc195',
  xlsx: '#7ec49e',
  html: '#8fd4ad',
  txt: '#9eddb8',
  other: '#a8d4ba',
}

function formatCount(n: number): string {
  return n.toLocaleString()
}

function chartThemeColors() {
  const root = document.documentElement
  const cs = getComputedStyle(root)
  return {
    isDark: root.getAttribute('data-theme') === 'dark',
    ink: cs.getPropertyValue('--text-primary').trim() || '#1d1d1f',
    muted: cs.getPropertyValue('--text-muted').trim() || '#6e6e73',
  }
}

function buildFileTypeDonutOption(
  fileTypes: FileTypeStatItem[],
  totalFiles: number,
  t: TFunction,
): EChartsOption {
  const { isDark, ink, muted } = chartThemeColors()
  const reducedMotion =
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

  return {
    animation: !reducedMotion,
    animationDuration: reducedMotion ? 0 : 280,
    tooltip: {
      trigger: 'item',
      ...echartsTooltipChrome(isDark),
      formatter: (params) => {
        const p = params as { name: string; value: number; percent?: number }
        const pct = p.percent != null ? p.percent.toFixed(1) : '0'
        return `${p.name}<br/>${formatCount(p.value)} · ${pct}%`
      },
    },
    series: [
      {
        type: 'pie',
        radius: ['54%', '78%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        label: { show: false },
        labelLine: { show: false },
        itemStyle: {
          borderRadius: 2,
          borderColor: isDark ? 'rgba(0,0,0,0.35)' : 'rgba(255,255,255,0.85)',
          borderWidth: 1,
        },
        emphasis: {
          scale: true,
          scaleSize: 4,
        },
        data: fileTypes.map((ft) => ({
          name: t(`sidebarStats.type.${ft.key}`),
          value: ft.count,
          itemStyle: {
            color: TYPE_BAR_COLORS[ft.key] ?? TYPE_BAR_COLORS.other,
          },
        })),
      },
    ],
    graphic: [
      {
        type: 'text',
        left: 'center',
        top: '42%',
        style: {
          text: formatCount(totalFiles),
          fill: ink,
          fontSize: 18,
          fontWeight: 600,
          fontFamily: 'system-ui, -apple-system, sans-serif',
          align: 'center',
        },
      },
      {
        type: 'text',
        left: 'center',
        top: '56%',
        style: {
          text: t('sidebarStats.chartCenterLabel'),
          fill: muted,
          fontSize: 10,
          fontWeight: 500,
          fontFamily: 'system-ui, -apple-system, sans-serif',
          align: 'center',
        },
      },
    ],
  }
}

export default function SidebarStats() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const resolvedMode = useThemeStore((s) => s.resolvedMode)
  const [stats, setStats] = useState<FileStatsPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const chartRef = useRef<HTMLDivElement | null>(null)
  const chartInstanceRef = useRef<echarts.ECharts | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getFileStats()
      setStats(res.data)
    } catch {
      setStats(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    const onRefresh = () => void load()
    window.addEventListener(LIBRARY_STATS_REFRESH, onRefresh)
    return () => window.removeEventListener(LIBRARY_STATS_REFRESH, onRefresh)
  }, [load])

  const fileTypes = useMemo(() => stats?.file_types ?? [], [stats])
  const totalFiles = stats?.total_files ?? 0

  useEffect(() => {
    const el = chartRef.current
    if (!el || fileTypes.length === 0) {
      chartInstanceRef.current?.dispose()
      chartInstanceRef.current = null
      return
    }

    const existing = echarts.getInstanceByDom(el)
    if (existing) existing.dispose()
    chartInstanceRef.current?.dispose()

    const chart = echarts.init(el, undefined, { renderer: 'canvas' })
    chartInstanceRef.current = chart
    chart.setOption(buildFileTypeDonutOption(fileTypes, totalFiles, t))

    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(el)

    return () => {
      ro.disconnect()
      chart.dispose()
      chartInstanceRef.current = null
    }
  }, [fileTypes, totalFiles, resolvedMode, t])

  return (
    <div className="sidebar-panel-section sidebar-stats-section">
      <div className="sidebar-panel-card sidebar-stats-card double-bezel-shell">
        {loading && !stats ? (
          <div className="sidebar-stats-loading">
            <Spin size="small" />
          </div>
        ) : (
          <>
            <div className="sidebar-stats-rows">
              <button
                type="button"
                className="sidebar-stats-row sidebar-stats-row--link"
                title={t('sidebarStats.goToFiles')}
                onClick={() => navigate('/')}
              >
                <span className="sidebar-stats-label">{t('sidebarStats.totalFiles')}</span>
                <span className="sidebar-stats-badge sidebar-stats-badge--accent">
                  {formatCount(stats?.total_files ?? 0)}
                </span>
              </button>
              <div className="sidebar-stats-row">
                <span className="sidebar-stats-label">{t('sidebarStats.totalCharacters')}</span>
                <span className="sidebar-stats-badge">{formatCount(stats?.total_characters ?? 0)}</span>
              </div>
            </div>

            {fileTypes.length > 0 ? (
              <div className="sidebar-stats-types">
                <div
                  className="sidebar-stats-chart-wrap"
                  role="group"
                  aria-label={t('sidebarStats.typeDistribution')}
                >
                  <div ref={chartRef} className="sidebar-stats-chart" />
                </div>
                <table className="sidebar-stats-a11y-table">
                  <caption>{t('sidebarStats.typeDistribution')}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{t('sidebarStats.a11yType')}</th>
                      <th scope="col">{t('sidebarStats.a11yCount')}</th>
                      <th scope="col">{t('sidebarStats.a11yPercent')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fileTypes.map((ft) => (
                      <tr key={ft.key}>
                        <td>{t(`sidebarStats.type.${ft.key}`)}</td>
                        <td>{formatCount(ft.count)}</td>
                        <td>{ft.percent}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <ul className="sidebar-stats-legend" aria-hidden="true">
                  {fileTypes.map((ft) => (
                    <li key={ft.key}>
                      <span className="sidebar-stats-legend-label">
                        <span
                          className="sidebar-stats-legend-dot"
                          style={{ background: TYPE_BAR_COLORS[ft.key] ?? TYPE_BAR_COLORS.other }}
                        />
                        <span className="sidebar-stats-legend-text">{t(`sidebarStats.type.${ft.key}`)}</span>
                      </span>
                      <span className="sidebar-stats-legend-pct">{ft.percent}%</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div className="sidebar-stats-rows sidebar-stats-rows--tail">
              <div className="sidebar-stats-row">
                <span className="sidebar-stats-label">{t('sidebarStats.tags')}</span>
                <span className="sidebar-stats-badge">{formatCount(stats?.tag_count ?? 0)}</span>
              </div>
              <div className="sidebar-stats-row">
                <span className="sidebar-stats-label">{t('sidebarStats.indexedCount')}</span>
                <span className="sidebar-stats-badge">{formatCount(stats?.indexed_count ?? 0)}</span>
              </div>
              <div className="sidebar-stats-row">
                <span className="sidebar-stats-label">{t('sidebarStats.documentTypes')}</span>
                <span className="sidebar-stats-badge">{formatCount(stats?.document_type_count ?? 0)}</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
