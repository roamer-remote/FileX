import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useTranslation } from 'react-i18next'
import { App, Button, Card, Col, Empty, List, Modal, Row, Spin, Statistic, Table, Tag, Tooltip } from 'antd'
import { FileTextOutlined, ReloadOutlined } from '@ant-design/icons'
import StatLabelWithHelp from '@/components/StatLabelWithHelp'
import LibraryGovernanceDetailModal, {
  type LibraryGovernanceDetailKind,
} from '@/components/LibraryGovernanceDetailModal'
import WikiLinksListModal, { type WikiLinkListKind } from '@/components/WikiLinksListModal'
import { FlTableMarqueeText } from '@/components/FileListComponents'
import { getFileById, type FileItem } from '@/api/files'
import {
  getLibraryReport,
  getWikiPageLinkedSources,
  refreshLibraryReport,
  type LibraryReportPayload,
  type LibraryReportResponse,
  type WikiLinkedSourceItem,
} from '@/api/knowledgeBase'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import '@/components/FileList.css'
import './LibraryMapTab.css'

export type LibraryMapTabHandle = { refresh: () => void }

export type LibraryMapTabProps = {
  active?: boolean
  onPreview?: (file: FileItem, anchorId?: string, options?: { mdNote?: boolean }) => void
  /** 大厅 Drawer：将「刷新报告」注册到顶栏 extra */
  onDrawerExtraChange?: (extra: ReactNode | null) => void
}

const WIKI_TOPIC_PAGE_KINDS = new Set(['entity', 'concept', 'synthesis'])
const WIKI_GRAPH_EDGE_TYPES = new Set(['file_direct', 'wiki_coref', 'wiki_topic'])
const PROVENANCE_KINDS = new Set(['extracted', 'inferred', 'ambiguous'])

function renderFolderPath(text: string) {
  if (!text) return '—'
  return <FlTableMarqueeText text={text} className="library-map-tab__folder-marquee" />
}

function renderWikiPageKind(kind: string, t: (key: string) => string) {
  if (!kind) return '—'
  if (WIKI_TOPIC_PAGE_KINDS.has(kind)) {
    return <Tag className="kb-wiki-index-kind">{t(`knowledgeIndex.wikiPageKind.${kind}`)}</Tag>
  }
  return kind
}

function renderWikiEdgeType(edgeType: string, t: (key: string) => string) {
  if (!edgeType) return '—'
  if (WIKI_GRAPH_EDGE_TYPES.has(edgeType)) {
    return t(`wikiLinks.graph.edgeType.${edgeType}`)
  }
  return edgeType
}

function renderProvenance(provenance: string, t: (key: string) => string) {
  if (!provenance) return '—'
  if (PROVENANCE_KINDS.has(provenance)) {
    return t(`libraryMap.provenanceKind.${provenance}`)
  }
  return provenance
}

function FileLinkButton({
  fileId,
  label,
  onOpen,
}: {
  fileId: number
  label: string
  onOpen: (fileId: number, options?: { mdNote?: boolean }) => void
}) {
  if (!fileId) return <span>{label || '—'}</span>
  return (
    <button
      type="button"
      className="library-map-tab__file-link"
      title={label}
      onClick={() => onOpen(fileId)}
    >
      {label}
    </button>
  )
}

type HubFileRow = LibraryReportPayload['hub_files'][number]

type HubLinkModalState = {
  fileId: number
  fileName: string
  kind: WikiLinkListKind
} | null

type HubSlugLinkedModalState = {
  slug: string
} | null

type HubWikiSlugRow = LibraryReportPayload['hub_wiki_slugs'][number]

function renderHubFileScoreTooltip(row: HubFileRow, t: (key: string, opts?: Record<string, unknown>) => string) {
  return (
    <div className="library-map-tab__score-tooltip">
      <div className="library-map-tab__score-tooltip-title">{t('libraryMap.scoreBreakdownTitle')}</div>
      <div>{t('libraryMap.scoreBreakdownOut', { count: row.out_degree })}</div>
      <div>{t('libraryMap.scoreBreakdownIn', { count: row.in_degree })}</div>
      <div className="library-map-tab__score-tooltip-total">
        {t('libraryMap.scoreBreakdownTotal', { count: row.score })}
      </div>
    </div>
  )
}

function renderClickableStatValue(
  value: number,
  onClick: () => void,
  ariaLabel: string,
) {
  if (value <= 0) return value
  return (
    <button
      type="button"
      className="library-map-tab__stat-value-btn"
      aria-label={ariaLabel}
      onClick={onClick}
    >
      {value}
    </button>
  )
}

function buildFileNameMap(payload: LibraryReportPayload): Map<number, string> {
  const map = new Map<number, string>()
  for (const file of payload.hub_files) {
    map.set(file.file_id, file.original_name)
  }
  for (const link of payload.surprising_links) {
    if (link.source_file_id && link.source_name) {
      map.set(link.source_file_id, link.source_name)
    }
    if (link.target_file_id && link.target_name) {
      map.set(link.target_file_id, link.target_name)
    }
  }
  return map
}

const LibraryMapTab = forwardRef<LibraryMapTabHandle, LibraryMapTabProps>(function LibraryMapTab(
  { active = true, onPreview, onDrawerExtraChange },
  ref,
) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const workspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const [refreshing, setRefreshing] = useState(false)
  const [report, setReport] = useState<LibraryReportResponse | null>(null)
  const [detailKind, setDetailKind] = useState<LibraryGovernanceDetailKind | null>(null)
  const [hubLinkModal, setHubLinkModal] = useState<HubLinkModalState>(null)
  const [slugLinkedModal, setSlugLinkedModal] = useState<HubSlugLinkedModalState>(null)
  const [slugLinkedItems, setSlugLinkedItems] = useState<WikiLinkedSourceItem[]>([])
  const [slugLinkedLoading, setSlugLinkedLoading] = useState(false)

  const pollPendingReport = useCallback(async (silent = false) => {
    const maxAttempts = 5
    const intervalMs = 2000
    for (let i = 0; i < maxAttempts; i += 1) {
      await new Promise((r) => setTimeout(r, intervalMs))
      const again = await getLibraryReport()
      setReport(again)
      if (again.status === 'ready' && again.payload) {
        if (!silent) message.success(t('libraryMap.refreshed'))
        return
      }
      if (again.status !== 'pending') {
        return
      }
    }
    if (!silent) message.info(t('libraryMap.pending'))
  }, [t, message])

  const doRefresh = useCallback(
    async (options?: { silent?: boolean }) => {
      const silent = options?.silent ?? false
      if (!workspaceId) {
        if (!silent) {
          setReport({ status: 'unavailable', message: t('libraryMap.noWorkspace') })
        }
        return
      }
      setRefreshing(true)
      try {
        const data = await refreshLibraryReport()
        if (data.status === 'pending') {
          if (!silent) message.info(t('libraryMap.pending'))
          setReport(data)
          await pollPendingReport(silent)
        } else {
          setReport(data)
          if (!silent) message.success(t('libraryMap.refreshed'))
        }
      } catch {
        message.error(t('libraryMap.refreshFailed'))
      } finally {
        setRefreshing(false)
      }
    },
    [workspaceId, t, message, pollPendingReport],
  )

  useImperativeHandle(ref, () => ({ refresh: () => { void doRefresh() } }), [doRefresh])

  useEffect(() => {
    if (active) void doRefresh({ silent: true })
  }, [active, workspaceId, doRefresh])

  useEffect(() => {
    if (!onDrawerExtraChange) return undefined
    onDrawerExtraChange(
      <Button
        type="default"
        size="small"
        icon={<ReloadOutlined />}
        loading={refreshing}
        onClick={() => void doRefresh()}
      >
        {t('libraryMap.refreshReport')}
      </Button>,
    )
    return () => onDrawerExtraChange(null)
  }, [onDrawerExtraChange, refreshing, doRefresh, t])

  const openFile = useCallback(
    async (fileId: number, options?: { mdNote?: boolean }) => {
      if (!onPreview) return
      try {
        const res = await getFileById(fileId)
        onPreview(res.data, undefined, options)
      } catch {
        message.error(t('libraryMap.previewFailed'))
      }
    },
    [onPreview, message, t],
  )

  const payload: LibraryReportPayload | undefined = report?.payload ?? undefined
  const pending = report?.status === 'pending'
  const fileNameById = useMemo(
    () => (payload ? buildFileNameMap(payload) : new Map<number, string>()),
    [payload],
  )

  const openGovernanceDetail = useCallback((kind: LibraryGovernanceDetailKind) => {
    setDetailKind(kind)
  }, [])

  const closeGovernanceDetail = useCallback(() => {
    setDetailKind(null)
  }, [])

  const openSlugLinkedSources = useCallback(
    (row: HubWikiSlugRow) => {
      if (row.inbound_topic_edges <= 0) return
      setSlugLinkedModal({ slug: row.slug })
      setSlugLinkedItems([])
      setSlugLinkedLoading(true)
      void getWikiPageLinkedSources(row.slug)
        .then((items) => setSlugLinkedItems(items))
        .catch(() => message.error(t('wikiPages.linkedSourcesLoadFailed')))
        .finally(() => setSlugLinkedLoading(false))
    },
    [message, t],
  )

  const closeSlugLinkedModal = useCallback(() => {
    setSlugLinkedModal(null)
  }, [])

  return (
    <div className="library-map-tab">
      <div className="library-map-tab__body">
        <Spin spinning={refreshing}>
          {pending && !payload ? (
          <Empty description={t('libraryMap.pending')} />
        ) : !payload ? (
          <Empty description={report?.message || t('libraryMap.empty')} />
        ) : (
          <>
            <Row gutter={[16, 16]} className="library-map-tab__stats">
              <Col xs={12} sm={6}>
                <Card size="small">
                  <Statistic
                    title={
                      <StatLabelWithHelp
                        label={t('libraryMap.fileCount')}
                        help={t('libraryMap.fileCountHelp')}
                      />
                    }
                    value={payload.meta.file_count}
                  />
                </Card>
              </Col>
              <Col xs={12} sm={6}>
                <Card size="small">
                  <Statistic
                    title={
                      <StatLabelWithHelp
                        label={t('libraryMap.edgeCount')}
                        help={t('libraryMap.edgeCountHelp')}
                      />
                    }
                    value={payload.meta.edge_count}
                  />
                </Card>
              </Col>
              <Col xs={12} sm={6}>
                <Card size="small">
                  <Statistic
                    title={
                      <StatLabelWithHelp
                        label={t('libraryMap.brokenLinks')}
                        help={t('libraryMap.brokenLinksHelp')}
                      />
                    }
                    value={payload.governance.broken_link_count}
                    formatter={(val) =>
                      renderClickableStatValue(
                        Number(val),
                        () => openGovernanceDetail('broken'),
                        t('libraryMap.brokenLinksDetailTitle'),
                      )
                    }
                  />
                </Card>
              </Col>
              <Col xs={12} sm={6}>
                <Card size="small">
                  <Statistic
                    title={
                      <StatLabelWithHelp
                        label={t('libraryMap.pendingConcepts')}
                        help={t('libraryMap.pendingConceptsHelp')}
                      />
                    }
                    value={payload.governance.pending_concept_count}
                    formatter={(val) =>
                      renderClickableStatValue(
                        Number(val),
                        () => openGovernanceDetail('pending'),
                        t('libraryMap.pendingConceptsDetailTitle'),
                      )
                    }
                  />
                </Card>
              </Col>
            </Row>

            <Card
              title={
                <StatLabelWithHelp
                  label={t('libraryMap.hubFiles')}
                  help={t('libraryMap.hubFilesHelp')}
                />
              }
              size="small"
              className="library-map-tab__card"
            >
              <Table
                size="small"
                pagination={false}
                rowKey="file_id"
                dataSource={payload.hub_files}
                columns={[
                  {
                    title: t('libraryMap.name'),
                    dataIndex: 'original_name',
                    ellipsis: true,
                    render: (name: string, row) => (
                      <FileLinkButton fileId={row.file_id} label={name} onOpen={(id, opts) => void openFile(id, opts)} />
                    ),
                  },
                  {
                    title: t('libraryMap.mdNote'),
                    key: 'md_note',
                    width: 56,
                    align: 'center' as const,
                    render: (_, row) =>
                      row.has_md ? (
                        <Tooltip title={t('libraryMap.viewNoteContent')}>
                          <Button
                            type="text"
                            size="small"
                            className="library-map-tab__note-btn"
                            icon={<FileTextOutlined aria-hidden />}
                            aria-label={t('libraryMap.viewNoteContent')}
                            onClick={() => void openFile(row.file_id, { mdNote: true })}
                          />
                        </Tooltip>
                      ) : (
                        <span className="library-map-tab__no-note" aria-hidden="true">—</span>
                      ),
                  },
                  {
                    title: (
                      <StatLabelWithHelp
                        label={t('libraryMap.score')}
                        help={t('libraryMap.scoreHelp')}
                      />
                    ),
                    dataIndex: 'score',
                    width: 88,
                    render: (score: number, row: HubFileRow) => (
                      <Tooltip title={renderHubFileScoreTooltip(row, t)} placement="top">
                        <span className="library-map-tab__score-value">{score}</span>
                      </Tooltip>
                    ),
                  },
                  {
                    title: (
                      <StatLabelWithHelp
                        label={t('libraryMap.outDegree')}
                        help={t('libraryMap.outDegreeHelp')}
                      />
                    ),
                    dataIndex: 'out_degree',
                    width: 88,
                    render: (value: number, row: HubFileRow) =>
                      renderClickableStatValue(
                        value,
                        () =>
                          setHubLinkModal({
                            fileId: row.file_id,
                            fileName: row.original_name,
                            kind: 'outlinks',
                          }),
                        t('libraryMap.outDegreeDetailTitle'),
                      ),
                  },
                  {
                    title: (
                      <StatLabelWithHelp
                        label={t('libraryMap.inDegree')}
                        help={t('libraryMap.inDegreeHelp')}
                      />
                    ),
                    dataIndex: 'in_degree',
                    width: 88,
                    render: (value: number, row: HubFileRow) =>
                      renderClickableStatValue(
                        value,
                        () =>
                          setHubLinkModal({
                            fileId: row.file_id,
                            fileName: row.original_name,
                            kind: 'backlinks',
                          }),
                        t('libraryMap.inDegreeDetailTitle'),
                      ),
                  },
                ]}
              />
            </Card>

            <Row gutter={[16, 16]}>
              <Col xs={24} md={12}>
                <Card
                  title={
                    <StatLabelWithHelp
                      label={t('libraryMap.hubTags')}
                      help={t('libraryMap.hubTagsHelp')}
                    />
                  }
                  size="small"
                  className="library-map-tab__card"
                >
                  {payload.hub_tags.length === 0 ? (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  ) : (
                    payload.hub_tags.map((row) => (
                      <Tag key={row.tag} className="library-map-tab__tag">
                        {row.tag} ({row.file_count})
                      </Tag>
                    ))
                  )}
                </Card>
              </Col>
              <Col xs={24} md={12}>
                <Card
                  title={
                    <StatLabelWithHelp
                      label={t('libraryMap.hubSlugs')}
                      help={t('libraryMap.hubSlugsHelp')}
                    />
                  }
                  size="small"
                  className="library-map-tab__card"
                >
                  <Table
                    size="small"
                    pagination={false}
                    rowKey="slug"
                    dataSource={payload.hub_wiki_slugs}
                    columns={[
                      {
                        title: (
                          <StatLabelWithHelp
                            label={t('libraryMap.slug')}
                            help={t('libraryMap.slugHelp')}
                          />
                        ),
                        dataIndex: 'slug',
                        ellipsis: true,
                        render: (slug: string, row) =>
                          row.file_id ? (
                            <FileLinkButton
                              fileId={row.file_id}
                              label={slug}
                              onOpen={(id) => void openFile(id)}
                            />
                          ) : (
                            <span title={slug}>{slug}</span>
                          ),
                      },
                      {
                        title: (
                          <StatLabelWithHelp
                            label={t('libraryMap.pageKind')}
                            help={t('libraryMap.pageKindHelp')}
                          />
                        ),
                        dataIndex: 'page_kind',
                        width: 100,
                        render: (kind: string) => renderWikiPageKind(kind, t),
                      },
                      {
                        title: (
                          <StatLabelWithHelp
                            label={t('libraryMap.inbound')}
                            help={t('libraryMap.inboundHelp')}
                          />
                        ),
                        dataIndex: 'inbound_topic_edges',
                        width: 88,
                        render: (value: number, row: HubWikiSlugRow) =>
                          renderClickableStatValue(
                            value,
                            () => openSlugLinkedSources(row),
                            t('libraryMap.inboundDetailTitle'),
                          ),
                      },
                    ]}
                  />
                </Card>
              </Col>
            </Row>

            <Card
              title={
                <StatLabelWithHelp
                  label={t('libraryMap.surprising')}
                  help={t('libraryMap.surprisingHelp')}
                />
              }
              size="small"
              className="library-map-tab__card"
            >
              <Table
                size="small"
                pagination={{ pageSize: 10, hideOnSinglePage: true }}
                rowKey={(r) => `${r.source_file_id}-${r.target_file_id}-${r.edge_type}`}
                dataSource={payload.surprising_links}
                columns={[
                  {
                    title: (
                      <StatLabelWithHelp
                        label={t('libraryMap.source')}
                        help={t('libraryMap.sourceHelp')}
                      />
                    ),
                    key: 'source',
                    ellipsis: true,
                    render: (_, row) => (
                      <FileLinkButton
                        fileId={row.source_file_id}
                        label={row.source_name || String(row.source_file_id)}
                        onOpen={(id) => void openFile(id)}
                      />
                    ),
                  },
                  {
                    title: (
                      <StatLabelWithHelp
                        label={t('libraryMap.target')}
                        help={t('libraryMap.targetHelp')}
                      />
                    ),
                    key: 'target',
                    ellipsis: true,
                    render: (_, row) => (
                      <FileLinkButton
                        fileId={row.target_file_id}
                        label={row.target_name || String(row.target_file_id)}
                        onOpen={(id) => void openFile(id)}
                      />
                    ),
                  },
                  {
                    title: (
                      <StatLabelWithHelp
                        label={t('libraryMap.edgeType')}
                        help={t('libraryMap.edgeTypeHelp')}
                      />
                    ),
                    dataIndex: 'edge_type',
                    width: 112,
                    render: (edgeType: string) => renderWikiEdgeType(edgeType, t),
                  },
                  {
                    title: (
                      <StatLabelWithHelp
                        label={t('libraryMap.folderA')}
                        help={t('libraryMap.folderAHelp')}
                      />
                    ),
                    key: 'source_folder_path',
                    width: 160,
                    render: (_, row) =>
                      renderFolderPath(
                        row.source_folder_path ||
                          (row.top_folder_a > 0 ? String(row.top_folder_a) : ''),
                      ),
                  },
                  {
                    title: (
                      <StatLabelWithHelp
                        label={t('libraryMap.folderB')}
                        help={t('libraryMap.folderBHelp')}
                      />
                    ),
                    key: 'target_folder_path',
                    width: 160,
                    render: (_, row) =>
                      renderFolderPath(
                        row.target_folder_path ||
                          (row.top_folder_b > 0 ? String(row.top_folder_b) : ''),
                      ),
                  },
                  {
                    title: (
                      <StatLabelWithHelp
                        label={t('libraryMap.provenance')}
                        help={t('libraryMap.provenanceHelp')}
                      />
                    ),
                    dataIndex: 'provenance',
                    width: 108,
                    render: (provenance: string) => renderProvenance(provenance, t),
                  },
                ]}
              />
            </Card>

            {payload.suggested_questions.length > 0 ? (
              <Card
                title={
                  <StatLabelWithHelp
                    label={t('libraryMap.suggestions')}
                    help={t('libraryMap.suggestionsHelp')}
                  />
                }
                size="small"
                className="library-map-tab__card"
              >
                <ul className="library-map-tab__suggestions">
                  {payload.suggested_questions.map((q, i) => (
                    <li key={`${q.template_id}-${i}`}>
                      <span>{q.text}</span>
                      {q.related_file_ids && q.related_file_ids.length > 0 ? (
                        <span className="library-map-tab__related-files">
                          {q.related_file_ids.map((fileId) => (
                            <FileLinkButton
                              key={fileId}
                              fileId={fileId}
                              label={fileNameById.get(fileId) ?? `#${fileId}`}
                              onOpen={(id) => void openFile(id)}
                            />
                          ))}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </Card>
            ) : null}
          </>
          )}
        </Spin>
      </div>
      <LibraryGovernanceDetailModal
        open={detailKind != null}
        kind={detailKind ?? 'broken'}
        knownFileNames={fileNameById}
        onClose={closeGovernanceDetail}
        onOpenFile={(fileId, options) => void openFile(fileId, options)}
      />
      <WikiLinksListModal
        open={hubLinkModal != null}
        onClose={() => setHubLinkModal(null)}
        fileId={hubLinkModal?.fileId ?? 0}
        fileName={hubLinkModal?.fileName ?? ''}
        linkKind={hubLinkModal?.kind ?? 'outlinks'}
        onOpenFile={(fileId) => void openFile(fileId)}
        sourceFileDirectOnly
      />
      <Modal
        open={slugLinkedModal != null}
        title={t('wikiPages.linkedSourcesTitle', { slug: slugLinkedModal?.slug ?? '' })}
        footer={null}
        width={560}
        onCancel={closeSlugLinkedModal}
        destroyOnClose
      >
        <p className="library-map-tab__slug-linked-hint">
          {t('wikiPages.linkedSourcesHint', { slug: slugLinkedModal?.slug ?? '' })}
        </p>
        <Spin spinning={slugLinkedLoading}>
          {!slugLinkedLoading && slugLinkedItems.length === 0 ? (
            <Empty description={t('wikiPages.linkedSourcesEmpty')} />
          ) : (
            <List
              className="library-map-tab__slug-linked-list"
              dataSource={slugLinkedItems}
              renderItem={(item) => (
                <List.Item className="library-map-tab__slug-linked-list-item">
                  <button
                    type="button"
                    className="library-map-tab__file-link library-map-tab__slug-linked-item"
                    title={item.source_name}
                    onClick={() => {
                      closeSlugLinkedModal()
                      void openFile(item.file_id)
                    }}
                  >
                    <FlTableMarqueeText text={item.source_name} />
                  </button>
                </List.Item>
              )}
            />
          )}
        </Spin>
      </Modal>
    </div>
  )
})

export default LibraryMapTab
