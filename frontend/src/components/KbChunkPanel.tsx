import { useCallback, useEffect, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { QuestionCircleOutlined } from "@ant-design/icons"
import { App, Button, Drawer, Empty, Input, Space, Spin, Table, Tabs, Tag, Typography, type TableProps } from "antd"
import type { FileItem } from "@/api/files"
import {
  getKnowledgeBaseChunkSagEvent,
  listKnowledgeBaseFileChunks,
  listKnowledgeBaseFileSagEvents,
  patchKnowledgeBaseChunk,
  type KbChunkDetail,
  type KbChunkListResponse,
  type KbSagEventItem,
  type KbSagEventListResponse,
} from "@/api/knowledgeBase"
import { buildKbChunkPatchPayload } from "@/lib/kbChunkPatchPayload"
import { formatBlockTypeLabel } from "@/lib/kbChunkBlockTypeDisplay"
import { kbChunkDrawerFieldState } from "@/lib/kbChunkPanelAccess"
import {
  formatMultimodalMetaSummary,
  isMultimodalReadOnlyKind,
  multimodalKindI18nKey,
  multimodalKindTagColor,
} from "@/lib/kbChunkMultimodalDisplay"
import KbChunkInterventionNotice from "./KbChunkInterventionNotice"
import KbChunksHelpModal from "./KbChunksHelpModal"
import { useKbChunkReindex } from "@/hooks/useKbChunkReindex"
import { openKbEvalTrialSearch } from "@/lib/kbEvalTrialSearch"
import "./KbChunkPanel.css"

const PAGE_SIZE = 20
const TABLE_SCROLL_Y = 420

type PanelSubTab = "chunks" | "sagEvents"

function SagEventReadonlyBody({
  event,
  t,
}: {
  event: KbSagEventItem
  t: (key: string, opts?: Record<string, unknown>) => string
}) {
  return (
    <div className="kbc-sag-body">
      <Typography.Text className="kbc-sag-title">{event.title}</Typography.Text>
      {event.summary ? (
        <Typography.Paragraph type="secondary" className="kbc-sag-summary">
          {event.summary}
        </Typography.Paragraph>
      ) : null}
      {event.entities.length > 0 ? (
        <div className="kbc-sag-entities">
          <Typography.Text type="secondary">{t("kbChunks.sagEntities")}</Typography.Text>
          <Space size={[4, 4]} wrap className="kbc-sag-entity-tags">
            {event.entities.map((ent) => (
              <Tag key={`${ent.entity_name}:${ent.entity_type}`}>
                {ent.entity_name}
                <span className="kbc-sag-entity-type"> · {ent.entity_type}</span>
              </Tag>
            ))}
          </Space>
        </div>
      ) : null}
      <Typography.Text type="secondary" className="kbc-sag-layer">
        {t("kbChunks.sagExtractLayer", { layer: event.extract_layer })}
      </Typography.Text>
    </div>
  )
}

function sourceLabel(t: (k: string) => string, source: string): string {
  if (source === "sidecar_md") return t("kbChunks.sourceSidecar")
  if (source === "main_md") return t("kbChunks.sourceMain")
  return source
}

function emptyStatusMessage(t: (key: string) => string, status: string | undefined): string {
  switch (status) {
    case "pending":
      return t("kbChunks.emptyStatusPending")
    case "indexing":
      return t("kbChunks.emptyStatusIndexing")
    case "failed":
      return t("kbChunks.emptyStatusFailed")
    case "ready":
      return t("kbChunks.empty")
    default:
      return t("kbChunks.empty")
  }
}

export type KbChunkPanelProps = {
  file: FileItem
  canEdit?: boolean
  /** 仅文件 owner 可触发 reindex API */
  canReindex?: boolean
  embedded?: boolean
  active?: boolean
  className?: string
  onIndexStatusChange?: (status: string) => void
}

export default function KbChunkPanel({
  file,
  canEdit = false,
  canReindex = false,
  embedded = false,
  active = true,
  className,
  onIndexStatusChange,
}: KbChunkPanelProps) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [payload, setPayload] = useState<KbChunkListResponse | null>(null)
  const [detail, setDetail] = useState<KbChunkDetail | null>(null)
  const [editText, setEditText] = useState("")
  const [editBoost, setEditBoost] = useState("")
  const [savingChunk, setSavingChunk] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const [trialSearchLoading, setTrialSearchLoading] = useState(false)
  const [sagEvent, setSagEvent] = useState<KbSagEventItem | null>(null)
  const [sagLoading, setSagLoading] = useState(false)
  const [subTab, setSubTab] = useState<PanelSubTab>("chunks")
  const [sagPage, setSagPage] = useState(1)
  const [sagPayload, setSagPayload] = useState<KbSagEventListResponse | null>(null)
  const [sagListLoading, setSagListLoading] = useState(false)
  const [sagDetail, setSagDetail] = useState<KbSagEventItem | null>(null)

  const loadPage = useCallback(
    async (p: number) => {
      setLoading(true)
      try {
        const res = await listKnowledgeBaseFileChunks(file.id, { page: p, page_size: PAGE_SIZE })
        setPayload(res)
      } catch {
        setPayload(null)
        message.error(t("kbChunks.loadFailed"))
      } finally {
        setLoading(false)
      }
    },
    [file.id, message, t],
  )

  const loadSagPage = useCallback(
    async (p: number) => {
      setSagListLoading(true)
      try {
        const res = await listKnowledgeBaseFileSagEvents(file.id, { page: p, page_size: PAGE_SIZE })
        setSagPayload(res)
      } catch {
        setSagPayload(null)
        message.error(t("kbChunks.sagListLoadFailed"))
      } finally {
        setSagListLoading(false)
      }
    },
    [file.id, message, t],
  )

  const { reindexNormal, confirmForceReindex, reindexLoading, forceReindexLoading } = useKbChunkReindex(
    file.id,
    {
      onQueued: (status, force) => {
        onIndexStatusChange?.(status)
        void loadPage(page)
        if (subTab === "sagEvents") {
          void loadSagPage(sagPage)
        }
        if (force) {
          setDetail(null)
          setSagDetail(null)
        }
      },
    },
  )

  useEffect(() => {
    if (!active) return
    setPayload(null)
    setDetail(null)
    setSagDetail(null)
    setSubTab("chunks")
    setPage(1)
    setSagPage(1)
    void loadPage(1)
  }, [active, file.id, loadPage])

  useEffect(() => {
    if (!active || subTab !== "sagEvents") return
    setSagPayload(null)
    setSagDetail(null)
    setSagPage(1)
    void loadSagPage(1)
  }, [active, file.id, subTab, loadSagPage])


  const runTrialSearch = async () => {
    if (!detail) return
    setTrialSearchLoading(true)
    try {
      await openKbEvalTrialSearch(
        navigate,
        { message, t },
        {
          boostKeywords: editBoost || detail.boost_keywords,
          text: editText || detail.text,
          workspaceId: file.workspace_id ?? null,
        },
      )
      setDetail(null)
    } finally {
      setTrialSearchLoading(false)
    }
  }

  const openDetail = (row: KbChunkDetail) => {
    setDetail(row)
    setEditText(row.text)
    setEditBoost(row.boost_keywords ?? "")
    setSagEvent(null)
    setSagLoading(true)
    void getKnowledgeBaseChunkSagEvent(file.id, row.id)
      .then((ev) => setSagEvent(ev))
      .catch(() => setSagEvent(null))
      .finally(() => setSagLoading(false))
  }

  const saveChunkEdit = async () => {
    if (!detail) return
    const built = buildKbChunkPatchPayload({
      originalText: detail.text,
      editText,
      originalBoost: detail.boost_keywords,
      editBoost,
    })
    if (!built.changed) {
      message.info(t("kbChunks.noChanges"))
      return
    }
    if ("error" in built) {
      message.error(t("kbChunks.textRequired"))
      return
    }
    setSavingChunk(true)
    try {
      await patchKnowledgeBaseChunk(file.id, detail.id, built.patch)
      message.success(t("kbChunks.saveOk"))
      await loadPage(page)
      setDetail(null)
    } catch {
      message.error(t("kbChunks.saveFailed"))
    } finally {
      setSavingChunk(false)
    }
  }

  const columns: TableProps<KbChunkDetail>["columns"] = useMemo(
    () => [
      {
        title: t("kbChunks.colIndex"),
        dataIndex: "chunk_index",
        width: 52,
        align: "right",
      },
      {
        title: t("kbChunks.colHeading"),
        dataIndex: "heading_path",
        width: 120,
        ellipsis: true,
        render: (v: string | null | undefined) => v || "—",
      },
      {
        title: t("kbChunks.colBlockType"),
        dataIndex: "block_type",
        width: 120,
        ellipsis: true,
        render: (v: string | null | undefined) => formatBlockTypeLabel(v, t),
      },
      {
        title: t("kbChunks.colContentKind"),
        dataIndex: "content_kind",
        width: 96,
        render: (v: string | null | undefined) =>
          v && isMultimodalReadOnlyKind(v) ? (
            <Tag color={multimodalKindTagColor(v)} className="kbc-kind-tag">
              {t(multimodalKindI18nKey(v))}
            </Tag>
          ) : (
            v || "—"
          ),
      },
      {
        title: t("kbChunks.colMeta"),
        key: "meta",
        width: 120,
        ellipsis: true,
        render: (_: unknown, row) => (
          <span className="kbc-meta-summary" title={formatMultimodalMetaSummary(row.content_kind, row.content_meta ?? null)}>
            {formatMultimodalMetaSummary(row.content_kind, row.content_meta ?? null)}
          </span>
        ),
      },
      {
        title: t("kbChunks.colLoc"),
        dataIndex: "loc_label",
        width: 88,
        ellipsis: true,
        render: (v: string | null | undefined) => v || "—",
      },
      {
        title: t("kbChunks.colText"),
        dataIndex: "text",
        ellipsis: true,
        render: (text: string) => (
          <span className="kbc-text-snippet" title={text}>
            {text.replace(/\s+/g, " ").trim().slice(0, 100)}
            {text.length > 100 ? "…" : ""}
          </span>
        ),
      },
      {
        title: t("kbChunks.colBoost"),
        dataIndex: "boost_keywords",
        width: 100,
        ellipsis: true,
        render: (v: string | null | undefined) => v || "—",
      },
    ],
    [t],
  )

  const sagColumns: TableProps<KbSagEventItem>["columns"] = useMemo(
    () => [
      {
        title: t("kbChunks.colIndex"),
        dataIndex: "chunk_index",
        width: 52,
        align: "right",
        render: (v: number | null | undefined) => (v != null ? v : "—"),
      },
      {
        title: t("kbChunks.colSagTitle"),
        dataIndex: "title",
        width: 160,
        ellipsis: true,
      },
      {
        title: t("kbChunks.colSagSummary"),
        dataIndex: "summary",
        ellipsis: true,
        render: (text: string) => (
          <span className="kbc-text-snippet" title={text}>
            {text.replace(/\s+/g, " ").trim().slice(0, 120)}
            {text.length > 120 ? "…" : ""}
          </span>
        ),
      },
      {
        title: t("kbChunks.sagEntities"),
        key: "entities",
        width: 200,
        render: (_: unknown, row) =>
          row.entities.length > 0 ? (
            <Space size={[4, 4]} wrap>
              {row.entities.slice(0, 4).map((ent) => (
                <Tag key={`${ent.entity_name}:${ent.entity_type}`} className="kbc-kind-tag">
                  {ent.entity_name}
                </Tag>
              ))}
              {row.entities.length > 4 ? <Tag>+{row.entities.length - 4}</Tag> : null}
            </Space>
          ) : (
            "—"
          ),
      },
    ],
    [t],
  )

  const modelName = payload?.items[0]?.embedding_model ?? "—"
  const showOverrideTag = payload?.kb_index_manual_override === true
  const drawerFields = detail
    ? kbChunkDrawerFieldState(canEdit, detail.content_kind)
    : { textEditable: false, boostEditable: false }

  if (!active) {
    return (
      <div className={`kbc-panel ${embedded ? "kbc-panel--tab" : ""} ${className ?? ""}`.trim()}>
        <Spin />
      </div>
    )
  }

  return (
    <div className={`kbc-panel ${embedded ? "kbc-panel--tab" : ""} ${className ?? ""}`.trim()}>
      {showOverrideTag && canEdit ? (
        <KbChunkInterventionNotice
          className="kbc-panel-notice"
          showActions={canReindex}
          reindexLoading={reindexLoading}
          forceReindexLoading={forceReindexLoading}
          onReindex={reindexNormal}
          onForceReindex={confirmForceReindex}
        />
      ) : null}
      <div className="kbc-head">
        {subTab === "chunks" && payload ? (
          <Typography.Text type="secondary" className="kbc-summary">
            {t("kbChunks.summary", {
              status: payload.index_status,
              count: payload.chunk_count,
              dim: payload.embedding_dim,
              model: modelName,
            })}
          </Typography.Text>
        ) : null}
        {subTab === "sagEvents" && sagPayload ? (
          <Typography.Text type="secondary" className="kbc-summary">
            {t("kbChunks.sagListSummary", { count: sagPayload.total })}
          </Typography.Text>
        ) : null}
        {showOverrideTag ? <Tag color="orange">{t("kbChunks.overrideTag")}</Tag> : null}
        {canReindex ? (
          <Space size={8} className="kbc-head-actions">
            <Button size="small" loading={reindexLoading} onClick={reindexNormal}>
              {t("kbChunks.reindexBtn")}
            </Button>
            <Button type="link" size="small" loading={forceReindexLoading} onClick={() => confirmForceReindex()}>
              {t("kbChunks.forceReindexBtn")}
            </Button>
          </Space>
        ) : null}
      </div>
      <Tabs
        className="kbc-subtabs"
        size="small"
        activeKey={subTab}
        onChange={(key) => setSubTab(key as PanelSubTab)}
        items={[
          {
            key: "chunks",
            label: t("kbChunks.subTabChunks"),
            children:
              (payload?.total ?? 0) === 0 && !loading ? (
                <div className="kbc-empty">
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={emptyStatusMessage(t, payload?.index_status)}
                  />
                  {canReindex ? (
                    <Space className="kbc-empty-actions">
                      <Button loading={reindexLoading} onClick={reindexNormal}>
                        {t("kbChunks.reindexBtn")}
                      </Button>
                      <Button type="link" loading={forceReindexLoading} onClick={() => confirmForceReindex()}>
                        {t("kbChunks.forceReindexBtn")}
                      </Button>
                    </Space>
                  ) : null}
                </div>
              ) : (
                <div className="kbc-table-wrap">
                  <Table<KbChunkDetail>
                    className="kbc-table"
                    rowKey="id"
                    size="small"
                    loading={loading}
                    sticky
                    scroll={{ x: 960, y: TABLE_SCROLL_Y }}
                    columns={columns}
                    dataSource={payload?.items ?? []}
                    pagination={{
                      current: page,
                      pageSize: PAGE_SIZE,
                      total: payload?.total ?? 0,
                      showSizeChanger: false,
                      hideOnSinglePage: true,
                      onChange: (p) => {
                        setPage(p)
                        void loadPage(p)
                      },
                    }}
                    locale={{ emptyText: t("kbChunks.empty") }}
                    onRow={(record) => ({
                      onClick: () => openDetail(record),
                      className: "kbc-row",
                    })}
                  />
                </div>
              ),
          },
          {
            key: "sagEvents",
            label: t("kbChunks.subTabSagEvents"),
            children:
              (sagPayload?.total ?? 0) === 0 && !sagListLoading ? (
                <div className="kbc-empty">
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("kbChunks.sagListEmpty")} />
                </div>
              ) : (
                <div className="kbc-table-wrap">
                  <Table<KbSagEventItem>
                    className="kbc-table"
                    rowKey="id"
                    size="small"
                    loading={sagListLoading}
                    sticky
                    scroll={{ x: 720, y: TABLE_SCROLL_Y }}
                    columns={sagColumns}
                    dataSource={sagPayload?.items ?? []}
                    pagination={{
                      current: sagPage,
                      pageSize: PAGE_SIZE,
                      total: sagPayload?.total ?? 0,
                      showSizeChanger: false,
                      hideOnSinglePage: true,
                      onChange: (p) => {
                        setSagPage(p)
                        void loadSagPage(p)
                      },
                    }}
                    locale={{ emptyText: t("kbChunks.sagListEmpty") }}
                    onRow={(record) => ({
                      onClick: () => setSagDetail(record),
                      className: "kbc-row",
                    })}
                  />
                </div>
              ),
          },
        ]}
      />
      <div className="kbc-hint-row">
        <p className="kbc-hint">
          {subTab === "sagEvents"
            ? t("kbChunks.sagRowHintReadOnly")
            : canEdit
              ? t("kbChunks.rowHintEditable")
              : t("kbChunks.rowHintReadOnly")}
        </p>
        <Button
          type="default"
          size="small"
          icon={<QuestionCircleOutlined />}
          onClick={() => setHelpOpen(true)}
          aria-label={t("kbChunks.help.button")}
        >
          {t("kbChunks.help.button")}
        </Button>
      </div>
      <KbChunksHelpModal open={helpOpen} onClose={() => setHelpOpen(false)} />

      <Drawer
        open={detail != null}
        title={detail != null ? t("kbChunks.detailTitle", { index: detail.chunk_index }) : ""}
        width={640}
        destroyOnClose
        onClose={() => setDetail(null)}
      >
        {detail ? (
          <>
            {canEdit ? (
              <KbChunkInterventionNotice
                className="kbc-drawer-notice"
                showActions={canReindex}
                reindexLoading={reindexLoading}
                forceReindexLoading={forceReindexLoading}
                onReindex={reindexNormal}
                onForceReindex={confirmForceReindex}
              />
            ) : null}
            <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
              {sourceLabel(t, detail.source)}
              {detail.loc_label ? ` · ${detail.loc_label}` : ""}
              {detail.heading_path ? ` · ${detail.heading_path}` : ""}
            </Typography.Paragraph>
            {isMultimodalReadOnlyKind(detail.content_kind) ? (
              <div className="kbc-multimodal-readonly">
                <Tag color={multimodalKindTagColor(detail.content_kind!)}>
                  {t(multimodalKindI18nKey(detail.content_kind!))}
                </Tag>
                <Typography.Paragraph type="secondary" className="kbc-multimodal-meta">
                  {formatMultimodalMetaSummary(detail.content_kind, detail.content_meta ?? null)}
                </Typography.Paragraph>
                <Typography.Text type="secondary">{t("kbChunks.multimodalReadOnlyHint")}</Typography.Text>
              </div>
            ) : null}
            <div className="kbc-sag-section">
              <Typography.Text strong>{t("kbChunks.sagSectionTitle")}</Typography.Text>
              {sagLoading ? (
                <div className="kbc-sag-loading">
                  <Spin size="small" />
                </div>
              ) : sagEvent ? (
                <SagEventReadonlyBody event={sagEvent} t={t} />
              ) : (
                <Typography.Text type="secondary" className="kbc-sag-empty">
                  {t("kbChunks.sagEmpty")}
                </Typography.Text>
              )}
            </div>
            <Typography.Text>{t("kbChunks.colText")}</Typography.Text>
            <Input.TextArea
              rows={8}
              value={editText}
              disabled={!drawerFields.textEditable}
              readOnly={!drawerFields.textEditable}
              onChange={(e) => setEditText(e.target.value)}
              style={{ marginTop: 6, marginBottom: 12 }}
            />
            <Typography.Text>{t("kbChunks.boostKeywords")}</Typography.Text>
            <Input
              value={editBoost}
              disabled={!drawerFields.boostEditable}
              onChange={(e) => setEditBoost(e.target.value)}
              placeholder={t("kbChunks.boostKeywordsHint")}
              style={{ marginTop: 6 }}
            />
            <div className="kbc-drawer-actions">
              <Button loading={trialSearchLoading} onClick={() => void runTrialSearch()}>
                {t("kbChunks.trialSearch")}
              </Button>
              {canEdit ? (
                <>
                  <Button onClick={() => setDetail(null)}>{t("common.cancel")}</Button>
                  <Button type="primary" loading={savingChunk} onClick={() => void saveChunkEdit()}>
                    {t("kbChunks.saveChunk")}
                  </Button>
                </>
              ) : (
                <Button onClick={() => setDetail(null)}>{t("common.close")}</Button>
              )}
            </div>
          </>
        ) : null}
      </Drawer>

      <Drawer
        open={sagDetail != null}
        title={
          sagDetail != null
            ? t("kbChunks.sagDetailTitle", { index: sagDetail.chunk_index ?? "—" })
            : ""
        }
        width={560}
        destroyOnClose
        onClose={() => setSagDetail(null)}
      >
        {sagDetail ? (
          <>
            <div className="kbc-sag-section kbc-sag-section--drawer">
              <SagEventReadonlyBody event={sagDetail} t={t} />
            </div>
            <Typography.Paragraph className="kbc-sag-content">{sagDetail.content}</Typography.Paragraph>
            <div className="kbc-drawer-actions">
              <Button onClick={() => setSagDetail(null)}>{t("common.close")}</Button>
            </div>
          </>
        ) : null}
      </Drawer>
    </div>
  )
}
