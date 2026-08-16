import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react"
import { useTranslation } from "react-i18next"
import type { TFunction } from "i18next"
import { App, Button, Empty, Input, Modal, Segmented, Spin, Table, type TableProps } from "antd"
import { ReloadOutlined } from "@ant-design/icons"
import * as echarts from "echarts"
import { DataSet } from "vis-data"
import { Network } from "vis-network/standalone"
import "vis-network/styles/vis-network.min.css"
import { getFiles, getTagGraph, getTagHeatmap, type FileItem, type TagGraphResponse, type TagHeatmapResponse } from "@/api/files"
import { formatDate, formatFileSize } from "@/utils"
import { useSystemSettingsStore } from "@/stores/systemSettingsStore"
import { useThemeStore } from "@/stores/themeStore"
import {
  buildVisTagGraph,
  fitTagGraphNetwork,
  tagGraphNetworkOptions,
  type VisTagNodeMeta,
} from "@/lib/tagGraphVisGraph"
import { echartsTooltipChrome } from "@/lib/chartTooltipStyle"
import "./TagRelationCharts.css"
import "./WikiLinkGraph.css"

const TAG_FILES_PAGE_SIZE = 100

function themeColors() {
  const root = document.documentElement
  const cs = getComputedStyle(root)
  const accent = cs.getPropertyValue("--accent").trim() || "#2997ff"
  const muted = cs.getPropertyValue("--text-muted").trim() || "#6e6e73"
  const ink = cs.getPropertyValue("--ink").trim() || "#f5f5f7"
  const isDark = root.getAttribute("data-theme") === "dark"
  return { accent, muted, ink, isDark }
}

function buildHeatmapOption(data: TagHeatmapResponse, t: TFunction): echarts.EChartsOption {
  const { accent, isDark } = themeColors()
  const tags = data.tags
  const cells: [number, number, number][] = []
  let maxVal = 0
  for (let i = 0; i < tags.length; i++) {
    for (let j = 0; j < tags.length; j++) {
      const v = data.matrix[i]?.[j] ?? 0
      if (v > 0) cells.push([j, i, v])
      maxVal = Math.max(maxVal, v)
    }
  }
  const low = isDark ? "rgba(20, 28, 40, 0.35)" : "rgba(240, 245, 252, 0.9)"
  const high = accent.startsWith("#") ? accent : "#2997ff"
  return {
    backgroundColor: "transparent",
    animation: false,
    tooltip: {
      position: "top",
      ...echartsTooltipChrome(isDark),
      formatter: (raw: unknown) => {
        const p = raw as { data?: [number, number, number] }
        const d = p.data
        if (!d || d.length < 3) return ""
        const rowTag = tags[d[1]]
        const colTag = tags[d[0]]
        const count = d[2]
        if (d[0] === d[1]) {
          return t("tagGraph.tooltipHeatmapDiag", { tag: rowTag, count })
        }
        return t("tagGraph.tooltipHeatmap", { row: rowTag, col: colTag, count })
      },
    },
    grid: { left: 108, right: 24, top: 16, bottom: 88 },
    xAxis: {
      type: "category",
      data: tags,
      splitArea: { show: true },
      axisLabel: { color: themeColors().muted, fontSize: 11, rotate: 40, width: 72, overflow: "truncate" },
    },
    yAxis: {
      type: "category",
      data: tags,
      splitArea: { show: true },
      axisLabel: { color: themeColors().muted, fontSize: 11, width: 96, overflow: "truncate" },
    },
    visualMap: {
      min: 0,
      max: Math.max(maxVal, 1),
      calculable: false,
      orient: "horizontal",
      left: "center",
      bottom: 4,
      itemWidth: 12,
      itemHeight: 80,
      textStyle: { color: themeColors().ink, fontSize: 11 },
      inRange: { color: [low, high] },
    },
    series: [
      {
        type: "heatmap",
        data: cells,
        label: { show: maxVal > 0 && tags.length <= 24, fontSize: 11, color: themeColors().ink },
        emphasis: { itemStyle: { shadowBlur: 8, shadowColor: "rgba(0,0,0,0.2)" } },
      },
    ],
  }
}

export type TagRelationChartsHandle = { refresh: () => void }

export type TagRelationChartsProps = {
  onPreview?: (file: FileItem, anchorId?: string) => void
  /** 点边或热力格：筛选文件列表（单 tag 或 tag∩tag2） */
  onTagFilterSelect?: (tag: string, tag2?: string) => void
  /** 父级 Ant Tabs 激活时为 true；隐藏时须 dispose ECharts */
  active?: boolean
}

const TagRelationCharts = forwardRef<TagRelationChartsHandle, TagRelationChartsProps>(function TagRelationCharts(
  { onPreview, onTagFilterSelect, active = true },
  ref,
) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const loadSystemSettings = useSystemSettingsStore((s) => s.load)
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
  const resolvedMode = useThemeStore((s) => s.resolvedMode)
  const graphSizing = useMemo(
    () => ({ singleBase, displayRatio: nodeDisplayRatio, edgeLineWidth }),
    [singleBase, nodeDisplayRatio, edgeLineWidth],
  )

  const canvasRef = useRef<HTMLDivElement>(null)
  const networkRef = useRef<Network | null>(null)
  const nodeMetaRef = useRef<Map<string, VisTagNodeMeta>>(new Map())
  const edgeMetaRef = useRef<Map<number, { source: string; target: string; value: number }>>(new Map())
  const onTagFilterSelectRef = useRef(onTagFilterSelect)
  onTagFilterSelectRef.current = onTagFilterSelect

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [graphPayload, setGraphPayload] = useState<TagGraphResponse | null>(null)
  const graphPayloadRef = useRef(graphPayload)
  graphPayloadRef.current = graphPayload

  const [viewTab, setViewTab] = useState<"graph" | "heatmap">("graph")
  const heatmapHostRef = useRef<HTMLDivElement>(null)
  const heatmapChartRef = useRef<ReturnType<typeof echarts.init> | null>(null)
  const [heatmapPayload, setHeatmapPayload] = useState<TagHeatmapResponse | null>(null)
  const heatmapPayloadRef = useRef(heatmapPayload)
  heatmapPayloadRef.current = heatmapPayload

  const [searchQuery, setSearchQuery] = useState("")
  const [selectedNode, setSelectedNode] = useState<VisTagNodeMeta | null>(null)
  const [neighborIds, setNeighborIds] = useState<string[]>([])

  const [tagFilesModalOpen, setTagFilesModalOpen] = useState(false)
  const [selectedTag, setSelectedTag] = useState<string | null>(null)
  const [tagFilesPage, setTagFilesPage] = useState(1)
  const [tagFilesItems, setTagFilesItems] = useState<FileItem[]>([])
  const [tagFilesTotal, setTagFilesTotal] = useState(0)
  const [tagFilesLoading, setTagFilesLoading] = useState(false)
  const [tagFilesError, setTagFilesError] = useState(false)

  const openTagFilesModal = useCallback((tagName: string) => {
    setSelectedTag(tagName)
    setTagFilesPage(1)
    setTagFilesModalOpen(true)
  }, [])

  const focusNode = useCallback((nodeId: string) => {
    const network = networkRef.current
    const meta = nodeMetaRef.current.get(nodeId)
    if (!network || !meta) return
    network.focus(nodeId, { scale: 1.35, animation: { duration: 400, easingFunction: "easeInOutQuad" } })
    network.selectNodes([nodeId])
    setSelectedNode(meta)
    setNeighborIds(network.getConnectedNodes(nodeId).map(String))
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(false)
    try {
      await loadSystemSettings().catch(() => undefined)
      const [graphRes, heatRes] = await Promise.all([getTagGraph(), getTagHeatmap()])
      setGraphPayload(graphRes.data)
      setHeatmapPayload(heatRes.data)
      setSelectedNode(null)
      setNeighborIds([])
    } catch {
      setLoadError(true)
      setGraphPayload(null)
      setHeatmapPayload(null)
    } finally {
      setLoading(false)
    }
  }, [loadSystemSettings])

  useImperativeHandle(ref, () => ({
    refresh: () => void load(),
  }))

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!tagFilesModalOpen || !selectedTag) return
    let cancelled = false
    setTagFilesLoading(true)
    setTagFilesError(false)
    void getFiles({
      tag: selectedTag,
      page: tagFilesPage,
      page_size: TAG_FILES_PAGE_SIZE,
      sort_time: "desc",
    })
      .then((res) => {
        if (cancelled) return
        setTagFilesItems(res.data.items)
        setTagFilesTotal(res.data.total)
      })
      .catch(() => {
        if (cancelled) return
        setTagFilesError(true)
        setTagFilesItems([])
        setTagFilesTotal(0)
        message.error(t("tagGraph.tagFilesLoadFailed"))
      })
      .finally(() => {
        if (!cancelled) setTagFilesLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [tagFilesModalOpen, selectedTag, tagFilesPage, t, message])

  useEffect(() => {
    if (!active || viewTab !== "graph" || !graphPayload?.nodes.length) {
      networkRef.current?.destroy()
      networkRef.current = null
      return
    }

    let disposed = false
    let network: Network | null = null
    let ro: ResizeObserver | null = null
    let sizeObserver: ResizeObserver | null = null
    let layoutTimerClear: (() => void) | null = null
    let initAttempts = 0

    const mountNetwork = (el: HTMLDivElement) => {
      networkRef.current?.destroy()

      const finishLayout = (animate: boolean) => {
        if (!network || disposed) return
        network.setOptions({ physics: { enabled: false } })
        fitTagGraphNetwork(network, el, animate)
      }

      const { isDark } = themeColors()
      const built = buildVisTagGraph(graphPayload, isDark, graphSizing)
      nodeMetaRef.current = built.nodeMeta
      edgeMetaRef.current = built.edgeMeta

      const nodesDS = new DataSet(built.visNodes)
      const edgesDS = new DataSet(built.visEdges)

      network = new Network(el, { nodes: nodesDS, edges: edgesDS }, tagGraphNetworkOptions())
      networkRef.current = network

      network.once("stabilizationIterationsDone", () => finishLayout(true))
      network.once("stabilized", () => finishLayout(false))
      const layoutTimer = window.setTimeout(() => finishLayout(false), 900)

      network.on("click", (params) => {
        if (params.nodes.length > 0) {
          focusNode(String(params.nodes[0]))
          return
        }
        if (params.edges.length > 0) {
          const edge = edgeMetaRef.current.get(Number(params.edges[0]))
          if (edge) onTagFilterSelectRef.current?.(edge.source, edge.target)
          return
        }
        setSelectedNode(null)
        setNeighborIds([])
      })

      network.on("doubleClick", (params) => {
        if (params.nodes.length === 0) return
        const meta = nodeMetaRef.current.get(String(params.nodes[0]))
        if (meta) openTagFilesModal(meta.name)
      })

      network.on("hoverNode", () => {
        el.style.cursor = "pointer"
      })
      network.on("blurNode", () => {
        el.style.cursor = "default"
      })

      requestAnimationFrame(() => {
        if (network && !disposed) fitTagGraphNetwork(network, el, false)
      })

      ro = new ResizeObserver(() => {
        if (!network || !canvasRef.current) return
        fitTagGraphNetwork(network, canvasRef.current, false)
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
    }
  }, [active, graphPayload, viewTab, resolvedMode, graphSizing, settingsRevision, focusNode, openTagFilesModal])

  useEffect(() => {
    const el = heatmapHostRef.current
    const payload = heatmapPayloadRef.current
    if (!active || viewTab !== "heatmap" || !payload?.tags.length || !el) {
      heatmapChartRef.current?.dispose()
      heatmapChartRef.current = null
      return
    }
    const existing = echarts.getInstanceByDom(el)
    if (existing) existing.dispose()
    heatmapChartRef.current?.dispose()
    const chart = echarts.init(el, undefined, { renderer: "canvas" })
    heatmapChartRef.current = chart
    chart.setOption(buildHeatmapOption(payload, t), true)

    const onHeatmapClick = (raw: unknown) => {
      if (!raw || typeof raw !== "object") return
      const p = raw as { seriesType?: string; data?: [number, number, number] }
      if (p.seriesType !== "heatmap" || !Array.isArray(p.data) || p.data.length < 2) return
      const col = p.data[0]
      const row = p.data[1]
      const tagA = payload.tags[row]
      const tagB = payload.tags[col]
      if (!tagA) return
      if (row === col) {
        onTagFilterSelectRef.current?.(tagA)
      } else if (tagB) {
        onTagFilterSelectRef.current?.(tagA, tagB)
      }
    }
    chart.on("click", onHeatmapClick)

    const ro = new ResizeObserver(() => {
      chart.resize()
    })
    ro.observe(el)
    requestAnimationFrame(() => chart.resize())

    return () => {
      chart.off("click", onHeatmapClick)
      ro.disconnect()
      chart.dispose()
      heatmapChartRef.current = null
    }
  }, [active, heatmapPayload, viewTab, t, resolvedMode])

  useEffect(() => {
    return () => {
      networkRef.current?.destroy()
      networkRef.current = null
      heatmapChartRef.current?.dispose()
      heatmapChartRef.current = null
    }
  }, [])

  const closeTagFilesModal = useCallback(() => {
    setTagFilesModalOpen(false)
    setSelectedTag(null)
    setTagFilesError(false)
    setTagFilesPage(1)
  }, [])

  const searchMatches = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q || !graphPayload) return []
    return graphPayload.nodes.filter((n) => n.name.toLowerCase().includes(q)).slice(0, 20)
  }, [searchQuery, graphPayload])

  const tagFilesColumns: TableProps<FileItem>["columns"] = useMemo(
    () => [
      {
        title: t("tagGraph.colName"),
        dataIndex: "original_name",
        key: "original_name",
        className: "tg-tag-files-col-name",
        onCell: () => ({ className: "tg-tag-files-col-name" }),
      },
      {
        title: t("tagGraph.colSize"),
        key: "file_size",
        width: 112,
        align: "right",
        className: "tg-tag-files-col-size",
        onHeaderCell: () => ({ className: "tg-tag-files-col-size" }),
        onCell: () => ({ className: "tg-tag-files-col-size" }),
        render: (_: unknown, row) => <span>{formatFileSize(row.file_size)}</span>,
      },
      {
        title: t("tagGraph.colTime"),
        key: "created_at",
        width: 176,
        align: "right",
        className: "tg-tag-files-col-time",
        onHeaderCell: () => ({ className: "tg-tag-files-col-time" }),
        onCell: () => ({ className: "tg-tag-files-col-time" }),
        render: (_: unknown, row) => <span>{formatDate(row.created_at)}</span>,
      },
    ],
    [t],
  )

  const hasTags = Boolean(graphPayload?.nodes.length || heatmapPayload?.tags.length)
  const showEmpty = !loading && !loadError && graphPayload && !hasTags
  const showFailed = !loading && loadError
  const showGraphHost = !loadError && hasTags && Boolean(graphPayload?.nodes.length)
  const showHeatmapHost = !loadError && hasTags && Boolean(heatmapPayload?.tags.length)

  const modalTitle = selectedTag ? t("tagGraph.nodeFilesTitle", { tag: selectedTag }) : t("tagGraph.title")

  return (
    <section
      className="tg-page glass-panel tg-page--embedded"
      aria-labelledby="tag-relations-heading"
      aria-describedby="tag-relations-desc"
    >
      <div className="tg-toolbar">
        <div className="panel-title-row ah-title-group tg-toolbar-heading">
          <h2 id="tag-relations-heading" className="tg-title ah-title">
            {t("knowledge.tagRelationsSection")}
          </h2>
          <span className="panel-subtitle tg-sub" id="tag-relations-desc">
            {t("tagGraph.subtitle")}
          </span>
        </div>
        <div className="tg-toolbar-text">
          {graphPayload?.truncated ? (
            <p className="tg-component-hint">
              {t("tagGraph.fileCapHint", { total: graphPayload.total_files_with_tags })}
            </p>
          ) : null}
        </div>
        <div className="tg-toolbar-actions">
          {hasTags && !showFailed ? (
            <Segmented
              className="tg-view-tabs"
              value={viewTab}
              onChange={(v) => setViewTab(v as "graph" | "heatmap")}
              options={[
                { label: t("tagGraph.tabGraph"), value: "graph" },
                { label: t("tagGraph.tabHeatmap"), value: "heatmap" },
              ]}
            />
          ) : null}
          <Button type="default" icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
            {t("tagGraph.reload")}
          </Button>
        </div>
      </div>

      <Spin spinning={loading} indicator={<span className="tg-spin-indicator" aria-hidden />} wrapperClassName="tg-spin">
        <div className="tg-body">
          {showFailed ? (
            <div className="tg-placeholder">
              <Empty
                className="tg-empty"
                description={
                  <span>
                    {t("messages.graphLoadFailed")}
                    <span className="tg-empty-hint">{t("messages.tagRelationsBackendHint")}</span>
                  </span>
                }
              />
            </div>
          ) : showEmpty ? (
            <div className="tg-placeholder">
              <Empty className="tg-empty" description={t("tagGraph.empty")} />
            </div>
          ) : viewTab === "graph" && showGraphHost ? (
            <div className="wlg-graph-layout">
              <div className="wlg-graph-canvas tg-chart-host" ref={canvasRef} aria-label={t("tagGraph.tabGraph")} />
              <aside className="wlg-graph-sidebar" aria-label={t("tagGraph.graph.sidebar")}>
                <div className="wlg-sidebar-search">
                  <Input
                    allowClear
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder={t("tagGraph.graph.searchPlaceholder")}
                  />
                  {searchMatches.length > 0 ? (
                    <div className="wlg-search-results" role="listbox">
                      {searchMatches.map((n) => (
                        <button
                          key={n.id || n.name}
                          type="button"
                          className="wlg-search-item"
                          role="option"
                          onClick={() => {
                            focusNode(n.id || n.name)
                            setSearchQuery("")
                          }}
                        >
                          {n.name}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className="wlg-sidebar-info">
                  <h3 className="wlg-sidebar-heading">{t("tagGraph.graph.inspector")}</h3>
                  {selectedNode ? (
                    <div className="wlg-info-content">
                      <p className="wlg-info-title">{selectedNode.name}</p>
                      <p className="wlg-info-field">
                        {t("tagGraph.graph.fileCount")}: {selectedNode.value}
                      </p>
                      {neighborIds.length > 0 ? (
                        <>
                          <p className="wlg-info-neighbors-label">
                            {t("tagGraph.graph.neighbors", { count: neighborIds.length })}
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
                        onClick={() => openTagFilesModal(selectedNode.name)}
                      >
                        {t("tagGraph.graph.openFiles")}
                      </Button>
                      <Button
                        type="link"
                        size="small"
                        className="wlg-preview-btn"
                        onClick={() => onTagFilterSelectRef.current?.(selectedNode.name)}
                      >
                        {t("tagGraph.graph.filterFiles")}
                      </Button>
                    </div>
                  ) : (
                    <p className="wlg-info-empty">{t("tagGraph.graph.clickHint")}</p>
                  )}
                </div>
                {graphPayload ? (
                  <p className="wlg-sidebar-stats">
                    {t("tagGraph.graph.stats", {
                      nodes: graphPayload.nodes.length,
                      edges: graphPayload.links.length,
                    })}
                  </p>
                ) : null}
              </aside>
            </div>
          ) : viewTab === "heatmap" ? (
            <>
              <p className="tg-heatmap-desc">{t("tagGraph.heatmapSubtitle")}</p>
              <div
                className="tg-chart-host tg-chart-host--heatmap"
                ref={heatmapHostRef}
                style={{ display: showHeatmapHost ? undefined : "none" }}
                role="img"
                aria-label={t("tagGraph.tabHeatmap")}
              />
            </>
          ) : null}
        </div>
      </Spin>

      <Modal
        open={tagFilesModalOpen}
        title={modalTitle}
        onCancel={closeTagFilesModal}
        maskClosable={false}
        footer={null}
        width={720}
        destroyOnClose
        rootClassName="tg-tag-files-modal"
        styles={{ body: { paddingTop: 12 } }}
      >
        {onPreview ? (
          <p style={{ margin: "0 0 12px", fontSize: 13, color: "var(--text-muted)" }}>
            {t("tagGraph.rowPreviewHint")}
          </p>
        ) : null}
        <Table<FileItem>
          className="tg-tag-files-table"
          rowKey="id"
          tableLayout="fixed"
          columns={tagFilesColumns}
          dataSource={tagFilesItems}
          loading={tagFilesLoading}
          pagination={{
            current: tagFilesPage,
            pageSize: TAG_FILES_PAGE_SIZE,
            total: tagFilesTotal,
            showSizeChanger: false,
            hideOnSinglePage: true,
            onChange: (p) => setTagFilesPage(p),
          }}
          locale={{
            emptyText: tagFilesError ? t("tagGraph.tagFilesLoadFailed") : t("tagGraph.tagFilesEmpty"),
          }}
          scroll={{ y: 360 }}
          onRow={(record) => ({
            onClick: () => {
              if (onPreview) {
                onPreview(record)
                closeTagFilesModal()
              }
            },
            className: onPreview ? "tg-tag-files-row" : undefined,
          })}
        />
      </Modal>

      <div className="tg-bottom-gap" aria-hidden />
    </section>
  )
})

export default TagRelationCharts
