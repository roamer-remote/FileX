import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useTranslation } from 'react-i18next'
import { App, Badge, Button, Checkbox, Empty, Input, Spin, Tooltip } from 'antd'
import { PlusOutlined, QuestionCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { DataSet } from 'vis-data'
import { Network } from 'vis-network/standalone'
import 'vis-network/styles/vis-network.min.css'
import WikiLinksHelpModal from '@/components/WikiLinksHelpModal'
import { getFileById, type FileItem } from '@/api/files'
import { getWikiCandidates, getWikiLinkGraph, type WikiLinkGraphResponse } from '@/api/knowledgeBase'
import WikiPageCreateModal from '@/components/WikiPageCreateModal'
import {
  applyEdgeTypeFilter,
  buildVisWikiGraph,
  fitWikiLinkNetwork,
  type VisWikiEdgeMeta,
  type VisWikiNodeMeta,
  type WikiEdgeType,
  wikiLinkNetworkOptions,
} from '@/lib/wikiLinkVisGraph'
import { useSystemSettingsStore } from '@/stores/systemSettingsStore'
import { useThemeStore } from '@/stores/themeStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import './WikiLinkGraph.css'
import './TagRelationCharts.css'

const ALL_EDGE_TYPES: WikiEdgeType[] = ['file_direct', 'wiki_coref', 'wiki_topic']

function themeAccent(): { accent: string; isDark: boolean } {
  const root = document.documentElement
  const cs = getComputedStyle(root)
  const accent = cs.getPropertyValue('--accent').trim() || '#2997ff'
  const isDark = root.getAttribute('data-theme') === 'dark'
  return { accent, isDark }
}

export type WikiLinkGraphHandle = { refresh: () => void }

export type WikiLinkGraphProps = {
  onPreview?: (file: FileItem, anchorId?: string) => void
  active?: boolean
  onDrawerExtraChange?: (extra: ReactNode | null) => void
}

const WikiLinkGraph = forwardRef<WikiLinkGraphHandle, WikiLinkGraphProps>(function WikiLinkGraph(
  { onPreview, active = true, onDrawerExtraChange },
  ref,
) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const resolvedMode = useThemeStore((s) => s.resolvedMode)
  const singleBase = useSystemSettingsStore((s) => {
    const n = Number(s.tag_graph_single_node_symbol_size)
    return Number.isFinite(n) && n >= 8 && n <= 160 ? n : 48
  })
  const nodeDisplayRatio = useSystemSettingsStore((s) => {
    const n = Number(s.tag_graph_node_display_ratio)
    return Number.isFinite(n) && n >= 0.1 && n <= 5 ? Math.round(n * 100) / 100 : 1
  })
  const edgeLineWidth = useSystemSettingsStore((s) => {
    const n = Number(s.tag_graph_edge_line_width)
    return Number.isFinite(n) && n >= 1 && n <= 12 ? Math.round(n) : 1
  })
  const settingsRevision = useSystemSettingsStore((s) => s.revision)
  const graphSizing = useMemo(
    () => ({ singleBase, displayRatio: nodeDisplayRatio, edgeLineWidth }),
    [singleBase, nodeDisplayRatio, edgeLineWidth],
  )

  const canvasRef = useRef<HTMLDivElement>(null)
  const networkRef = useRef<Network | null>(null)
  const nodesDSRef = useRef<DataSet<{ id: string; hidden?: boolean }> | null>(null)
  const edgesDSRef = useRef<DataSet<{ id: number; hidden?: boolean }> | null>(null)
  const nodeMetaRef = useRef<Map<string, VisWikiNodeMeta>>(new Map())
  const edgeMetaRef = useRef<Map<number, VisWikiEdgeMeta>>(new Map())
  const onPreviewRef = useRef(onPreview)
  onPreviewRef.current = onPreview

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [payload, setPayload] = useState<WikiLinkGraphResponse | null>(null)
  const [helpOpen, setHelpOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [pendingCount, setPendingCount] = useState(0)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedNode, setSelectedNode] = useState<VisWikiNodeMeta | null>(null)
  const [neighborIds, setNeighborIds] = useState<string[]>([])
  const [hiddenEdgeTypes, setHiddenEdgeTypes] = useState<Set<WikiEdgeType>>(new Set())

  const edgeFilterState = useMemo(
    () => ({
      file_direct: !hiddenEdgeTypes.has('file_direct'),
      wiki_coref: !hiddenEdgeTypes.has('wiki_coref'),
      wiki_topic: !hiddenEdgeTypes.has('wiki_topic'),
    }),
    [hiddenEdgeTypes],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(false)
    try {
      // 全空间互链：不跟随资料列表侧栏目录筛选，避免选中无关目录时关系图为空
      const data = await getWikiLinkGraph('all')
      setPayload(data)
      setSelectedNode(null)
      setNeighborIds([])
      try {
        const pending = await getWikiCandidates()
        setPendingCount(pending.length)
      } catch {
        setPendingCount(0)
      }
    } catch {
      setLoadError(true)
      setPayload(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useImperativeHandle(ref, () => ({ refresh: () => void load() }))

  useEffect(() => {
    void load()
  }, [load, activeWorkspaceId])

  const openPreview = useCallback(
    (fileId: number) => {
      void getFileById(fileId)
        .then((res) => onPreviewRef.current?.(res.data))
        .catch(() => message.error(t('wikiLinks.previewFailed')))
    },
    [message, t],
  )

  const focusNode = useCallback((nodeId: string) => {
    const network = networkRef.current
    const meta = nodeMetaRef.current.get(nodeId)
    if (!network || !meta) return
    network.focus(nodeId, { scale: 1.35, animation: { duration: 400, easingFunction: 'easeInOutQuad' } })
    network.selectNodes([nodeId])
    setSelectedNode(meta)
    setNeighborIds(network.getConnectedNodes(nodeId).map(String))
  }, [])

  const syncEdgeVisibility = useCallback((hidden: Set<WikiEdgeType>) => {
    const edgesDS = edgesDSRef.current
    if (!edgesDS) return
    const edgeIds = edgesDS.getIds() as number[]
    const updates = applyEdgeTypeFilter(edgeIds, edgeMetaRef.current, hidden)
    edgesDS.update(updates.map(({ edgeId, hidden: h }) => ({ id: edgeId, hidden: h })))
  }, [])

  useEffect(() => {
    syncEdgeVisibility(hiddenEdgeTypes)
    const network = networkRef.current
    const el = canvasRef.current
    if (network && el && el.clientHeight > 0) fitWikiLinkNetwork(network, el, false)
  }, [hiddenEdgeTypes, syncEdgeVisibility])

  useEffect(() => {
    if (!active || !payload?.nodes.length) {
      networkRef.current?.destroy()
      networkRef.current = null
      nodesDSRef.current = null
      edgesDSRef.current = null
      return
    }

    let disposed = false
    let network: Network | null = null
    let ro: ResizeObserver | null = null
    let sizeObserver: ResizeObserver | null = null
    let layoutTimerClear: (() => void) | null = null
    let hoveredNodeId: string | null = null
    let initAttempts = 0

    const mountNetwork = (el: HTMLDivElement) => {
      networkRef.current?.destroy()

      const finishLayout = (animate: boolean) => {
        if (!network || disposed) return
        network.setOptions({ physics: { enabled: false } })
        fitWikiLinkNetwork(network, el, animate)
      }

      const { accent, isDark } = themeAccent()
      const built = buildVisWikiGraph(payload, isDark, accent, graphSizing)
      nodeMetaRef.current = built.nodeMeta
      edgeMetaRef.current = built.edgeMeta

      const nodesDS = new DataSet(built.visNodes)
      const edgesDS = new DataSet(built.visEdges)
      nodesDSRef.current = nodesDS
      edgesDSRef.current = edgesDS

      network = new Network(el, { nodes: nodesDS, edges: edgesDS }, wikiLinkNetworkOptions())
      networkRef.current = network

      network.once('stabilizationIterationsDone', () => finishLayout(true))
      network.once('stabilized', () => finishLayout(false))
      const layoutTimer = window.setTimeout(() => finishLayout(false), 900)

      network.on('click', (params) => {
        if (params.nodes.length > 0) {
          focusNode(String(params.nodes[0]))
        } else if (!hoveredNodeId) {
          setSelectedNode(null)
          setNeighborIds([])
        }
      })

      network.on('doubleClick', (params) => {
        if (params.nodes.length === 0) return
        const meta = nodeMetaRef.current.get(String(params.nodes[0]))
        if (meta) openPreview(meta.fileId)
      })

      network.on('hoverNode', () => {
        el.style.cursor = 'pointer'
      })
      network.on('blurNode', () => {
        hoveredNodeId = null
        el.style.cursor = 'default'
      })

      syncEdgeVisibility(hiddenEdgeTypes)
      requestAnimationFrame(() => {
        if (network && !disposed) fitWikiLinkNetwork(network, el, false)
      })

      ro = new ResizeObserver(() => {
        if (!network || !canvasRef.current) return
        fitWikiLinkNetwork(network, canvasRef.current, false)
      })
      ro.observe(el)

      return () => window.clearTimeout(layoutTimer)
    }

    const tryInit = () => {
      if (disposed) return
      const el = canvasRef.current
      if (!el) return
      initAttempts += 1
      if (el.clientWidth >= 1 && el.clientHeight >= 1) {
        sizeObserver?.disconnect()
        sizeObserver = null
        layoutTimerClear = mountNetwork(el) ?? null
        return
      }
      if (initAttempts < 120) {
        requestAnimationFrame(tryInit)
      }
    }

    const frame = requestAnimationFrame(tryInit)
    sizeObserver = new ResizeObserver(() => tryInit())
    const layoutEl = canvasRef.current?.parentElement
    if (layoutEl) sizeObserver.observe(layoutEl)

    return () => {
      disposed = true
      cancelAnimationFrame(frame)
      layoutTimerClear?.()
      ro?.disconnect()
      sizeObserver?.disconnect()
      network?.destroy()
      networkRef.current = null
      nodesDSRef.current = null
      edgesDSRef.current = null
    }
  }, [active, payload, resolvedMode, graphSizing, settingsRevision, focusNode, openPreview, syncEdgeVisibility])

  useEffect(() => () => networkRef.current?.destroy(), [])

  const searchMatches = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q || !payload) return []
    return payload.nodes.filter((n) => n.name.toLowerCase().includes(q)).slice(0, 20)
  }, [searchQuery, payload])

  const toggleEdgeType = (edgeType: WikiEdgeType, checked: boolean) => {
    setHiddenEdgeTypes((prev) => {
      const next = new Set(prev)
      if (checked) next.delete(edgeType)
      else next.add(edgeType)
      return next
    })
  }

  const showEmpty = !loading && !loadError && payload && !payload.nodes.length
  const showFailed = !loading && loadError
  const showChart = !loadError && Boolean(payload?.nodes.length)

  const toolbarActions = useMemo(
    () => (
      <div className="wlg-toolbar-actions">
        {pendingCount > 0 ? (
          <Tooltip title={t('wikiCompile.pendingTooltip', { count: pendingCount })}>
            <span className="wlg-pending-badge">
              <Badge count={pendingCount} overflowCount={99} color="var(--accent, #2997ff)">
                <span className="wlg-pending-label">{t('wikiCompile.pendingLabel')}</span>
              </Badge>
            </span>
          </Tooltip>
        ) : null}
        <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          {t('wikiCompile.createTopic')}
        </Button>
        <Button
          type="default"
          size="small"
          icon={<QuestionCircleOutlined />}
          onClick={() => setHelpOpen(true)}
          aria-label={t('wikiLinks.help.button')}
        >
          {t('wikiLinks.help.button')}
        </Button>
        <Button
          type="default"
          size="small"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={() => void load()}
        >
          {t('wikiLinks.reload')}
        </Button>
      </div>
    ),
    [pendingCount, loading, load, t],
  )

  useEffect(() => {
    if (!onDrawerExtraChange) return undefined
    onDrawerExtraChange(toolbarActions)
    return () => onDrawerExtraChange(null)
  }, [onDrawerExtraChange, toolbarActions])

  return (
    <section
      className="tg-page glass-panel tg-page--embedded"
      aria-label={t('wikiLinks.title')}
    >
      <div className="wlg-toolbar">
        <div className="wlg-legend" aria-hidden="true">
          <span className="wlg-legend-item wlg-legend-item--direct">{t('wikiLinks.graph.edgeDirect')}</span>
          <span className="wlg-legend-item wlg-legend-item--coref">{t('wikiLinks.graph.edgeCoref')}</span>
          <span className="wlg-legend-item wlg-legend-item--topic">{t('wikiLinks.graph.edgeTopic')}</span>
          <span className="wlg-legend-item wlg-legend-item--hub">{t('wikiLinks.graph.hubNode')}</span>
        </div>
        <div className="wlg-toolbar-text">
          {payload?.truncated ? (
            <p className="wlg-hint">{t('wikiLinks.truncatedHint', { total: payload.total_files_with_links })}</p>
          ) : null}
        </div>
        {!onDrawerExtraChange ? toolbarActions : null}
      </div>
      <WikiLinksHelpModal open={helpOpen} onClose={() => setHelpOpen(false)} />
      <WikiPageCreateModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={() => void load()} />
      <Spin spinning={loading} wrapperClassName="tg-spin">
        <div className="tg-body">
          {showFailed ? (
            <div className="tg-placeholder">
              <Empty description={t('wikiLinks.loadFailed')} />
            </div>
          ) : showEmpty ? (
            <div className="tg-placeholder">
              <Empty description={t('wikiLinks.empty')} />
            </div>
          ) : active && showChart ? (
            <div className="wlg-graph-layout">
              <div className="wlg-graph-canvas tg-chart-host" ref={canvasRef} aria-label={t('wikiLinks.title')} />
              <aside className="wlg-graph-sidebar" aria-label={t('wikiLinks.graph.sidebar')}>
                <div className="wlg-sidebar-search">
                  <Input
                    allowClear
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder={t('wikiLinks.graph.searchPlaceholder')}
                  />
                  {searchMatches.length > 0 ? (
                    <div className="wlg-search-results" role="listbox">
                      {searchMatches.map((n) => (
                        <button
                          key={n.id}
                          type="button"
                          className="wlg-search-item"
                          role="option"
                          onClick={() => {
                            focusNode(String(n.id))
                            setSearchQuery('')
                          }}
                        >
                          {n.name}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className="wlg-sidebar-info">
                  <h3 className="wlg-sidebar-heading">{t('wikiLinks.graph.inspector')}</h3>
                  {selectedNode ? (
                    <div className="wlg-info-content">
                      <p className="wlg-info-title">{selectedNode.name}</p>
                      <p className="wlg-info-field">
                        {t('wikiLinks.graph.degree')}: {selectedNode.value}
                      </p>
                      {selectedNode.wikiSlug ? (
                        <p className="wlg-info-field">wiki: {selectedNode.wikiSlug}</p>
                      ) : null}
                      {neighborIds.length > 0 ? (
                        <>
                          <p className="wlg-info-neighbors-label">
                            {t('wikiLinks.graph.neighbors', { count: neighborIds.length })}
                          </p>
                          <div className="wlg-neighbors-list">
                            {neighborIds.map((nid) => {
                              const nb = nodeMetaRef.current.get(nid)
                              return (
                                <button
                                  key={nid}
                                  type="button"
                                  className="wlg-neighbor-link"
                                  onClick={() => focusNode(nid)}
                                >
                                  {nb?.name ?? nid}
                                </button>
                              )
                            })}
                          </div>
                        </>
                      ) : null}
                      <Button
                        type="link"
                        size="small"
                        className="wlg-preview-btn"
                        onClick={() => openPreview(selectedNode.fileId)}
                      >
                        {t('wikiLinks.graph.openPreview')}
                      </Button>
                    </div>
                  ) : (
                    <p className="wlg-info-empty">{t('wikiLinks.graph.clickHint')}</p>
                  )}
                </div>
                <div className="wlg-sidebar-filters">
                  <h3 className="wlg-sidebar-heading">{t('wikiLinks.graph.edgeFilter')}</h3>
                  {ALL_EDGE_TYPES.map((et) => (
                    <label key={et} className="wlg-filter-row">
                      <Checkbox
                        checked={edgeFilterState[et]}
                        onChange={(e) => toggleEdgeType(et, e.target.checked)}
                      />
                      <span>{t(`wikiLinks.graph.edgeType.${et}`)}</span>
                    </label>
                  ))}
                </div>
                {payload ? (
                  <p className="wlg-sidebar-stats">
                    {t('wikiLinks.graph.stats', { nodes: payload.nodes.length, edges: payload.links.length })}
                  </p>
                ) : null}
              </aside>
            </div>
          ) : null}
        </div>
      </Spin>
    </section>
  )
})

export default WikiLinkGraph
