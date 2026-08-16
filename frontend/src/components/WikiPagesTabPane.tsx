import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { useTranslation } from "react-i18next"
import { App, Badge, Button, Empty, Form, Input, List, Modal, Pagination, Spin, Table, Tag, Tooltip, type TableColumnsType } from "antd"
import { EditOutlined, PlusOutlined } from "@ant-design/icons"
import { DeleteActionIcon } from "@/components/DeleteActionIcon"
import { deleteFile, getFileById, updateFile, type FileItem } from "@/api/files"

import {
  getWikiCandidates,
  getWikiPageLinkedSources,
  getWikiPages,
  patchWikiPageSlug,
  postWikiLint,
  type WikiLinkedSourceItem,
  type WikiPageListItem,
} from "@/api/knowledgeBase"
import WikiPageCreateModal from "@/components/WikiPageCreateModal"
import { FlTableMarqueeText } from "@/components/FileListComponents"
import { emitLibraryStatsRefresh } from "@/lib/libraryEvents"
import { normalizeWikiSlug } from "@/utils/wikiSlug"
import { useWorkspaceStore } from "@/stores/workspaceStore"
import { useFlexTableBodyScrollY } from "@/hooks/useFlexTableBodyScrollY"
import "@/components/FileList.css"
import "./WikiPagesTabPane.css"

function wikiPageRowToFileItem(row: WikiPageListItem): FileItem {
  return {
    id: row.file_id,
    filename: row.title,
    original_name: row.title,
    file_size: 0,
    mime_type: "text/markdown",
    folder_id: null,
    workspace_id: row.workspace_id,
    user_id: 0,
    created_at: "",
    has_md: row.has_md,
    page_kind: row.page_kind,
    wiki_slug: row.wiki_slug,
  }
}

const WIKI_PAGE_KINDS = new Set(["entity", "concept", "synthesis"])

function normalizeWikiPageTitle(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) return ""
  return trimmed.toLowerCase().endsWith(".md") ? trimmed : `${trimmed}.md`
}

export type WikiPagesTabPaneHandle = { refresh: () => void }

export type WikiPagesTabPaneProps = {
  onPreview?: (file: FileItem, anchorId?: string) => void
  active?: boolean
  /** 大厅 Drawer：将操作按钮注册到顶栏，不在内容区展示 */
  onHeaderActionsChange?: (actions: ReactNode | null) => void
}

const WikiPagesTabPane = forwardRef<WikiPagesTabPaneHandle, WikiPagesTabPaneProps>(function WikiPagesTabPane(
  { onPreview, active = true, onHeaderActionsChange },
  ref,
) {
  const { t } = useTranslation()
  const { modal, message } = App.useApp()
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const [loading, setLoading] = useState(true)
  const [lintLoading, setLintLoading] = useState(false)
  const [rows, setRows] = useState<WikiPageListItem[]>([])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const bodyRef = useRef<HTMLDivElement>(null)
  const [pendingCount, setPendingCount] = useState(0)
  const [createOpen, setCreateOpen] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [linkedModal, setLinkedModal] = useState<{ slug: string; title: string } | null>(null)
  const [linkedItems, setLinkedItems] = useState<WikiLinkedSourceItem[]>([])
  const [linkedLoading, setLinkedLoading] = useState(false)
  const [slugEditRow, setSlugEditRow] = useState<WikiPageListItem | null>(null)
  const [slugSaving, setSlugSaving] = useState(false)
  const [slugEditForm] = Form.useForm<{ wiki_slug: string }>()
  const [titleEditRow, setTitleEditRow] = useState<WikiPageListItem | null>(null)
  const [titleSaving, setTitleSaving] = useState(false)
  const [titleEditForm] = Form.useForm<{ title: string }>()
  const previewRequestRef = useRef(0)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [pagesRes, pending] = await Promise.all([
        getWikiPages({ page, page_size: pageSize }),
        getWikiCandidates(),
      ])
      setRows(pagesRes.items)
      setTotal(pagesRes.total)
      setPendingCount(pending.length)
    } catch {
      setRows([])
      setTotal(0)
      setPendingCount(0)
      message.error(t("wikiPages.loadFailed"))
    } finally {
      setLoading(false)
    }
  }, [message, page, pageSize, t, activeWorkspaceId])

  useImperativeHandle(ref, () => ({ refresh: () => void load() }))

  useEffect(() => {
    setPage(1)
  }, [activeWorkspaceId])

  useEffect(() => {
    if (active) void load()
  }, [load, active])

  const openFilePreview = useCallback(
    (fileId: number) => {
      const seq = ++previewRequestRef.current
      void getFileById(fileId)
        .then((res) => {
          if (seq !== previewRequestRef.current) return
          onPreview?.(res.data)
        })
        .catch(() => {
          if (seq !== previewRequestRef.current) return
          message.error(t("wikiLinks.previewFailed"))
        })
    },
    [message, onPreview, t],
  )

  const openThemePagePreview = useCallback(
    (row: WikiPageListItem) => {
      const seq = ++previewRequestRef.current
      onPreview?.(wikiPageRowToFileItem(row))
      void getFileById(row.file_id)
        .then((res) => {
          if (seq !== previewRequestRef.current) return
          onPreview?.(res.data)
        })
        .catch(() => {
          if (seq !== previewRequestRef.current) return
          message.error(t("wikiLinks.previewFailed"))
        })
    },
    [message, onPreview, t],
  )

  const runLint = useCallback(async () => {
    setLintLoading(true)
    try {
      await postWikiLint()
      message.success(t("wikiPages.lintOk"))
      await load()
    } catch {
      message.error(t("wikiPages.lintFailed"))
    } finally {
      setLintLoading(false)
    }
  }, [load, message, t])


  const handleDelete = useCallback(
    (row: WikiPageListItem) => {
      window.setTimeout(() => {
        modal.confirm({
          title: t("wikiPages.deleteConfirmTitle"),
          content: t("wikiPages.deleteConfirm", { slug: row.wiki_slug, title: row.title }),
          okType: "danger",
          okText: t("wikiPages.delete"),
          onOk: async () => {
            setDeletingId(row.file_id)
            try {
              await deleteFile(row.file_id)
              message.success(t("wikiPages.deleteOk"))
              emitLibraryStatsRefresh()
              await load()
            } catch {
              message.error(t("wikiPages.deleteFailed"))
            } finally {
              setDeletingId(null)
            }
          },
        })
      }, 0)
    },
    [load, message, modal, t],
  )


  const openLinkedSources = useCallback(
    (row: WikiPageListItem) => {
      if (row.linked_source_count <= 0) return
      setLinkedModal({ slug: row.wiki_slug, title: row.title })
      setLinkedItems([])
      setLinkedLoading(true)
      void getWikiPageLinkedSources(row.wiki_slug)
        .then((items) => setLinkedItems(items))
        .catch(() => message.error(t("wikiPages.linkedSourcesLoadFailed")))
        .finally(() => setLinkedLoading(false))
    },
    [message, t],
  )

  const openSlugEdit = useCallback(
    (row: WikiPageListItem) => {
      setSlugEditRow(row)
      slugEditForm.setFieldsValue({ wiki_slug: row.wiki_slug })
    },
    [slugEditForm],
  )

  const submitSlugEdit = useCallback(async () => {
    if (!slugEditRow) return
    const values = await slugEditForm.validateFields()
    const nextSlug = normalizeWikiSlug(values.wiki_slug)
    if (!nextSlug) {
      slugEditForm.setFields([{ name: "wiki_slug", errors: [t("wikiPages.editSlugInvalid")] }])
      return
    }
    if (nextSlug === slugEditRow.wiki_slug) {
      setSlugEditRow(null)
      return
    }
    setSlugSaving(true)
    try {
      const res = await patchWikiPageSlug(slugEditRow.file_id, nextSlug)
      message.success(
        res.notes_updated > 0
          ? t("wikiPages.editSlugOkWithNotes", { count: res.notes_updated })
          : t("wikiPages.editSlugOk"),
      )
      setSlugEditRow(null)
      emitLibraryStatsRefresh()
      await load()
    } catch {
      /* axios 拦截器已提示 */
    } finally {
      setSlugSaving(false)
    }
  }, [load, message, slugEditForm, slugEditRow, t])

  const openTitleEdit = useCallback(
    (row: WikiPageListItem) => {
      setTitleEditRow(row)
      titleEditForm.setFieldsValue({ title: row.title })
    },
    [titleEditForm],
  )

  const submitTitleEdit = useCallback(async () => {
    if (!titleEditRow) return
    const values = await titleEditForm.validateFields()
    const nextTitle = normalizeWikiPageTitle(values.title)
    if (!nextTitle) {
      titleEditForm.setFields([{ name: "title", errors: [t("wikiPages.editTitleRequired")] }])
      return
    }
    if (nextTitle === titleEditRow.title) {
      setTitleEditRow(null)
      return
    }
    setTitleSaving(true)
    try {
      await updateFile(titleEditRow.file_id, { filename: nextTitle })
      message.success(t("wikiPages.editTitleOk"))
      setTitleEditRow(null)
      emitLibraryStatsRefresh()
      await load()
    } catch {
      /* axios 拦截器已提示 */
    } finally {
      setTitleSaving(false)
    }
  }, [load, message, titleEditForm, titleEditRow, t])

  const scrollY = useFlexTableBodyScrollY([loading, rows.length, page, pageSize], {
    bodyRef,
  })

  const tableScroll = rows.length > 0 && scrollY > 0 ? { y: scrollY } : undefined

  const headerToolbar = useMemo(
    () => (
      <div className="wiki-pages-head-actions">
        {pendingCount > 0 ? (
          <Tooltip title={t("wikiCompile.pendingTooltip", { count: pendingCount })}>
            <span className="wiki-pages-pending-badge">
              <Badge count={pendingCount} overflowCount={99} color="var(--accent, #2997ff)">
                <span className="wiki-pages-pending-label">{t("wikiPages.pending")}</span>
              </Badge>
            </span>
          </Tooltip>
        ) : null}
        <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          {t("wikiCompile.createTopic")}
        </Button>
        <Button size="small" loading={lintLoading} onClick={() => void runLint()}>
          {t("wikiPages.lint")}
        </Button>
      </div>
    ),
    [lintLoading, pendingCount, t],
  )

  useEffect(() => {
    if (!onHeaderActionsChange) return
    onHeaderActionsChange(headerToolbar)
    return () => onHeaderActionsChange(null)
  }, [headerToolbar, onHeaderActionsChange])

  const columns: TableColumnsType<WikiPageListItem> = useMemo(
    () => [
      {
        title: t("wikiPages.columnTopic"),
        dataIndex: "wiki_slug",
        key: "wiki_slug",
        width: 200,
        ellipsis: true,
        render: (slug: string, row) => (
          <div className="wiki-pages-topic-cell">
            <span className="wiki-pages-topic-slug" title={slug}>
              {slug}
            </span>
            <Tooltip title={t("wikiPages.editSlug")}>
              <Button
                type="text"
                size="small"
                className="wiki-pages-slug-edit-btn"
                icon={<EditOutlined />}
                aria-label={t("wikiPages.editSlug")}
                onClick={() => openSlugEdit(row)}
              />
            </Tooltip>
          </div>
        ),
      },
      {
        title: t("knowledgeIndex.wikiColumns.page_kind"),
        dataIndex: "page_kind",
        key: "page_kind",
        width: 96,
        render: (kind: string) =>
          WIKI_PAGE_KINDS.has(kind) ? (
            <Tag className="kb-wiki-index-kind">{t(`knowledgeIndex.wikiPageKind.${kind}`)}</Tag>
          ) : (
            kind || "—"
          ),
      },
      {
        title: t("knowledgeIndex.wikiColumns.original_name"),
        dataIndex: "title",
        key: "title",
        ellipsis: true,
        render: (title: string, row) => (
          <div className="wiki-pages-topic-cell">
            <Button
              type="link"
              className="wiki-pages-title-link"
              title={title}
              onClick={() => openThemePagePreview(row)}
            >
              {title}
            </Button>
            <Tooltip title={t("wikiPages.editTitle")}>
              <Button
                type="text"
                size="small"
                className="wiki-pages-slug-edit-btn"
                icon={<EditOutlined />}
                aria-label={t("wikiPages.editTitle")}
                onClick={() => openTitleEdit(row)}
              />
            </Tooltip>
          </div>
        ),
      },
      {
        title: t("wikiPages.columnLinkedSources"),
        dataIndex: "linked_source_count",
        key: "linked_source_count",
        width: 96,
        align: "center" as const,
        render: (count: number, row) =>
          count > 0 ? (
            <Button type="link" className="wiki-pages-linked-count" onClick={() => openLinkedSources(row)}>
              {count}
            </Button>
          ) : (
            count
          ),
      },
      {
        title: t("wikiPages.columnActions"),
        key: "actions",
        width: 80,
        align: "center" as const,
        render: (_: unknown, row) => (
          <Tooltip title={t("wikiPages.delete")}>
            <Button
              type="text"
              size="small"
              danger
              className="wiki-pages-delete-btn"
              loading={deletingId === row.file_id}
              disabled={deletingId != null && deletingId !== row.file_id}
              icon={<DeleteActionIcon />}
              aria-label={t("wikiPages.delete")}
              onClick={() => handleDelete(row)}
            />
          </Tooltip>
        ),
      },
    ],
    [deletingId, handleDelete, openLinkedSources, openSlugEdit, openTitleEdit, openThemePagePreview, t],
  )

  return (
    <section className="wiki-pages-pane glass-panel" aria-label={t("wikiPages.title")}>
      {!onHeaderActionsChange ? <div className="wiki-pages-inline-toolbar">{headerToolbar}</div> : null}
      <Modal
        open={linkedModal != null}
        onCancel={() => setLinkedModal(null)}
        footer={null}
        width={520}
        title={t("wikiPages.linkedSourcesTitle", { slug: linkedModal?.slug ?? "" })}
      >
        <p className="wiki-pages-linked-hint">{t("wikiPages.linkedSourcesHint", { slug: linkedModal?.slug ?? "" })}</p>
        <Spin spinning={linkedLoading}>
          {!linkedLoading && linkedItems.length === 0 ? (
            <Empty description={t("wikiPages.linkedSourcesEmpty")} />
          ) : (
            <List
              className="wiki-pages-linked-list"
              dataSource={linkedItems}
              renderItem={(item) => (
                <List.Item className="wiki-pages-linked-list-item">
                  <div
                    role="button"
                    tabIndex={0}
                    className="wiki-pages-linked-item"
                    onClick={() => {
                      setLinkedModal(null)
                      openFilePreview(item.file_id)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault()
                        setLinkedModal(null)
                        openFilePreview(item.file_id)
                      }
                    }}
                  >
                    <FlTableMarqueeText
                      text={item.source_name}
                      className="wiki-pages-linked-item-marquee"
                    />
                  </div>
                </List.Item>
              )}
            />
          )}
        </Spin>
      </Modal>
      <WikiPageCreateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => void load()}
      />
      <Modal
        open={slugEditRow != null}
        title={t("wikiPages.editSlugTitle")}
        okText={t("common.confirm")}
        cancelText={t("common.cancel")}
        confirmLoading={slugSaving}
        destroyOnClose
        onCancel={() => setSlugEditRow(null)}
        onOk={() => void submitSlugEdit()}
      >
        <p className="wiki-pages-slug-edit-hint">{t("wikiPages.editSlugHint")}</p>
        <Form form={slugEditForm} layout="vertical">
          <Form.Item
            name="wiki_slug"
            label={t("wikiCompile.fieldSlug")}
            extra={t("wikiCompile.fieldSlugHint")}
            rules={[{ required: true, message: t("wikiPages.editSlugRequired") }]}
          >
            <Input maxLength={128} placeholder={slugEditRow?.wiki_slug} />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        open={titleEditRow != null}
        title={t("wikiPages.editTitleTitle")}
        okText={t("common.confirm")}
        cancelText={t("common.cancel")}
        confirmLoading={titleSaving}
        destroyOnClose
        onCancel={() => setTitleEditRow(null)}
        onOk={() => void submitTitleEdit()}
      >
        <p className="wiki-pages-slug-edit-hint">{t("wikiPages.editTitleHint")}</p>
        <Form form={titleEditForm} layout="vertical">
          <Form.Item
            name="title"
            label={t("knowledgeIndex.wikiColumns.original_name")}
            rules={[{ required: true, message: t("wikiPages.editTitleRequired") }]}
          >
            <Input maxLength={500} placeholder={titleEditRow?.title} />
          </Form.Item>
        </Form>
      </Modal>
      <div className="wiki-pages-table-shell fl-table-shell">
        <div className="fl-body" ref={bodyRef}>
          <Spin spinning={loading} className="fl-spin">
            <div className="fl-table-host">
              <Table<WikiPageListItem>
                className="wiki-pages-table fl-file-table"
                rowKey="file_id"
                size="small"
                tableLayout="fixed"
                columns={columns}
                dataSource={rows}
                pagination={false}
                scroll={tableScroll}
                locale={{
                  emptyText: <Empty className="wiki-pages-empty" description={t("wikiPages.empty")} />,
                }}
              />
            </div>
          </Spin>
        </div>
        <div className="fl-pager">
          <Pagination
            current={page}
            pageSize={pageSize}
            total={total}
            showSizeChanger
            pageSizeOptions={["10", "20", "50", "100"]}
            onChange={(p, ps) => {
              setPage(p)
              setPageSize(ps)
            }}
          />
        </div>
      </div>
    </section>
  )
})

export default WikiPagesTabPane
