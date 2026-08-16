import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { App, Button, Descriptions, Input, Modal, Switch, Table, Typography, type TableProps } from "antd"
import { CopyOutlined } from "@ant-design/icons"
import type { FileItem } from "@/api/files"
import { copyToClipboard } from '@/utils/copyToClipboard'
import {
  listKnowledgeBaseFileChunks,
  patchKnowledgeBaseChunk,
  type KbChunkDetail,
  type KbChunkListResponse,
} from "@/api/knowledgeBase"
import { buildKbChunkPatchPayload } from "@/lib/kbChunkPatchPayload"
import "./KbVectorChunksModal.css"

const PAGE_SIZE = 20
/** 表格正文滚动区高度（摘要固定于上方，列头由 Table sticky 固定） */
const TABLE_SCROLL_Y = 440

function sourceLabel(t: (k: string) => string, source: string): string {
  if (source === "sidecar_md") return t("kbVectors.sourceSidecar")
  if (source === "main_md") return t("kbVectors.sourceMain")
  return source
}

function formatHead(head: number[]): string {
  return head.map((v) => v.toFixed(4)).join(", ")
}

type Props = {
  open: boolean
  file: FileItem | null
  onClose: () => void
}

export default function KbVectorChunksModal({ open, file, onClose }: Props) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [payload, setPayload] = useState<KbChunkListResponse | null>(null)
  const [detail, setDetail] = useState<KbChunkDetail | null>(null)
  const [showFullVector, setShowFullVector] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [editText, setEditText] = useState("")
  const [editBoost, setEditBoost] = useState("")
  const [savingChunk, setSavingChunk] = useState(false)

  const loadPage = useCallback(
    async (p: number) => {
      if (!file) return
      setLoading(true)
      try {
        const res = await listKnowledgeBaseFileChunks(file.id, { page: p, page_size: PAGE_SIZE })
        setPayload(res)
      } catch {
        setPayload(null)
        message.error(t("kbVectors.loadFailed"))
      } finally {
        setLoading(false)
      }
    },
    [file, message, t],
  )

  useEffect(() => {
    if (!open || !file) {
      setPayload(null)
      setDetail(null)
      setPage(1)
      setShowFullVector(false)
      return
    }
    void loadPage(1)
  }, [open, file, loadPage])

  const fetchChunkWithEmbedding = async (chunkId: number, chunkIndex: number) => {
    if (!file) return null
    const pageForChunk = Math.floor(chunkIndex / PAGE_SIZE) + 1
    const res = await listKnowledgeBaseFileChunks(file.id, {
      page: pageForChunk,
      page_size: PAGE_SIZE,
      include_embedding: true,
    })
    return res.items.find((x) => x.id === chunkId) ?? null
  }

  const openDetail = async (row: KbChunkDetail) => {
    setDetail(row)
    setEditText(row.text)
    setEditBoost(row.boost_keywords ?? "")
    setShowFullVector(false)
  }

  const loadFullVector = async () => {
    if (!detail || !file) return
    setDetailLoading(true)
    try {
      const hit = await fetchChunkWithEmbedding(detail.id, detail.chunk_index)
      if (hit) setDetail(hit)
    } catch {
      message.error(t("kbVectors.loadFailed"))
    } finally {
      setDetailLoading(false)
    }
  }

  const saveChunkEdit = async () => {
    if (!detail || !file) return
    const built = buildKbChunkPatchPayload({
      originalText: detail.text,
      editText,
      originalBoost: detail.boost_keywords,
      editBoost,
    })
    if (!built.changed) {
      message.info(t("kbVectors.noChanges"))
      return
    }
    if ("error" in built) {
      message.error(t("kbVectors.textRequired"))
      return
    }
    setSavingChunk(true)
    try {
      await patchKnowledgeBaseChunk(file.id, detail.id, built.patch)
      message.success(t("kbVectors.saveOk"))
      await loadPage(page)
      setDetail(null)
    } catch {
      message.error(t("kbVectors.saveFailed"))
    } finally {
      setSavingChunk(false)
    }
  }

  const copyVector = async (chunk: KbChunkDetail) => {
    let vec = chunk.embedding
    if (!vec?.length && file) {
      try {
        const hit = await fetchChunkWithEmbedding(chunk.id, chunk.chunk_index)
        vec = hit?.embedding
      } catch {
        message.error(t("kbVectors.copyFailed"))
        return
      }
    }
    if (!vec?.length) {
      message.warning(t("kbVectors.noFullVector"))
      return
    }
    try {
      await copyToClipboard(JSON.stringify(vec))
      message.success(t("kbVectors.copied"))
    } catch {
      message.error(t("kbVectors.copyFailed"))
    }
  }

  const columns: TableProps<KbChunkDetail>["columns"] = useMemo(
    () => [
      {
        title: t("kbVectors.colIndex"),
        dataIndex: "chunk_index",
        width: 56,
        align: "right",
      },
      {
        title: t("kbVectors.colRange"),
        key: "range",
        width: 108,
        render: (_: unknown, row) => `${row.char_start}–${row.char_end}`,
      },
      {
        title: t("kbVectors.colText"),
        dataIndex: "text",
        ellipsis: true,
        render: (text: string) => (
          <span className="kbv-text-snippet" title={text}>
            {text.replace(/\s+/g, " ").trim().slice(0, 120)}
            {text.length > 120 ? "…" : ""}
          </span>
        ),
      },
      {
        title: t("kbVectors.colVector"),
        key: "vector",
        width: 200,
        render: (_: unknown, row) => (
          <code className="kbv-vector-head" title={t("kbVectors.vectorHeadTitle")}>
            [{formatHead(row.embedding_preview.head)}…]
          </code>
        ),
      },
    ],
    [t],
  )

  const title = file ? t("kbVectors.title", { name: file.original_name }) : t("kbVectors.titleFallback")
  const modelName = payload?.items[0]?.embedding_model ?? "—"

  return (
    <>
      <Modal
        open={open}
        title={title}
        onCancel={onClose}
        footer={null}
        width={920}
        destroyOnClose
        maskClosable={false}
        rootClassName="kbv-modal"
      >
        <div className="kbv-layout">
          <div className="kbv-head-sticky">
            {payload ? (
              <div className="kbv-summary">
                <Typography.Text type="secondary">
                  {t("kbVectors.summary", {
                    status: payload.index_status,
                    count: payload.chunk_count,
                    dim: payload.embedding_dim,
                    model: modelName,
                  })}
                </Typography.Text>
              </div>
            ) : null}
          </div>
          <div className="kbv-table-scroll">
            <Table<KbChunkDetail>
              className="kbv-table"
              rowKey="id"
              size="small"
              loading={loading}
              sticky
              scroll={{ y: TABLE_SCROLL_Y }}
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
              locale={{ emptyText: t("kbVectors.empty") }}
              onRow={(record) => ({
                onClick: () => void openDetail(record),
                className: "kbv-row",
              })}
            />
          </div>
          <p className="kbv-hint">{t("kbVectors.rowHint")}</p>
        </div>
      </Modal>

      <Modal
        open={detail != null}
        title={detail != null ? t("kbVectors.detailTitle", { index: detail.chunk_index }) : ""}
        onCancel={() => {
          setDetail(null)
          setShowFullVector(false)
        }}
        footer={null}
        width={720}
        destroyOnClose
        maskClosable={false}
        rootClassName="kbv-detail-modal"
      >
        {detail ? (
          <>
            <Descriptions size="small" column={1} bordered className="kbv-detail-desc">
              <Descriptions.Item label={t("kbVectors.colSource")}>
                {sourceLabel(t, detail.source)}
              </Descriptions.Item>
              <Descriptions.Item label={t("kbVectors.colRange")}>
                {detail.char_start}–{detail.char_end}
              </Descriptions.Item>
              <Descriptions.Item label={t("kbVectors.embeddingModel")}>
                {detail.embedding_model}
              </Descriptions.Item>
              <Descriptions.Item label={t("kbVectors.embeddingDim")}>
                {detail.embedding_dim}
              </Descriptions.Item>
              <Descriptions.Item label={t("kbVectors.embeddingNorm")}>
                {detail.embedding_preview.norm}
              </Descriptions.Item>
              <Descriptions.Item label={t("kbVectors.colText")}>
                <Input.TextArea
                  rows={6}
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                />
              </Descriptions.Item>
              <Descriptions.Item label={t("kbVectors.boostKeywords")}>
                <Input
                  value={editBoost}
                  onChange={(e) => setEditBoost(e.target.value)}
                  placeholder={t("kbVectors.boostKeywordsHint")}
                />
              </Descriptions.Item>
            </Descriptions>
            <div className="kbv-detail-actions">
              <Button type="primary" loading={savingChunk} onClick={() => void saveChunkEdit()}>
                {t("kbVectors.saveChunk")}
              </Button>
            </div>
            <div className="kbv-detail-vector-toolbar">
              <Switch
                size="small"
                checked={showFullVector}
                loading={detailLoading}
                onChange={(checked) => {
                  setShowFullVector(checked)
                  if (checked && !detail.embedding?.length) void loadFullVector()
                }}
              />
              <span>{t("kbVectors.showFullVector")}</span>
              <Button
                type="link"
                size="small"
                icon={<CopyOutlined />}
                onClick={() => void copyVector(detail)}
              >
                {t("kbVectors.copyVector")}
              </Button>
            </div>
            <pre className="kbv-detail-vector">
              {showFullVector && detail.embedding?.length
                ? JSON.stringify(detail.embedding)
                : `[${formatHead(detail.embedding_preview.head)}, …] (${detail.embedding_dim} ${t("kbVectors.dims")})`}
            </pre>
          </>
        ) : null}
      </Modal>
    </>
  )
}