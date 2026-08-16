import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type Key,
  type MouseEvent,
} from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router-dom"
import { App, Button, Checkbox, Dropdown, Input, Modal, Pagination, Radio, Select, Space, Spin, Table, Tag, Tooltip } from "antd"
import type { MenuProps } from "antd"
import {
  CaretDownOutlined,
  CaretUpOutlined,
  DownloadOutlined,
  EditOutlined,
  FileTextOutlined,
  EyeOutlined,
  RobotFilled,
  TagsOutlined,
  FileSearchOutlined,
  FolderOutlined,
  EllipsisOutlined,
  ClusterOutlined,
  NodeIndexOutlined,
  ApartmentOutlined,
} from "@ant-design/icons"
import { DeleteActionIcon } from "@/components/DeleteActionIcon"
import { buildForceReindexConfirmContent } from "@/lib/kbForceReindexConfirm"
import { runFileBatchDelete } from "@/lib/fileBatchDelete"
import { isLikelyLargeDocByChunkCount } from "@/lib/kbLargeDocHeuristic"
import { FlKbIndexCell, FlGridCardTags, FlTableMarqueeText, TableHeadAiBreak, canReextract, isExtractBusy, fileExt, indexStatusLabelKey, extractStatusLabelKey } from "./FileListComponents"
import { useFilesStore } from "@/stores/filesStore"
import { useAuthStore } from "@/stores/authStore"
import { rebuildKnowledgeBaseIndex, reextractKnowledgeBaseFile, reindexKnowledgeBaseFile } from "@/api/knowledgeBase"
import {
  deleteFile,
  updateFile,
  downloadAuthenticatedFile,
  getDownloadUrl,
  getThumbnailUrl,
  listMyTags,
  replaceFileTags,
  getFileById,
  type FileItem,
} from "@/api/files"
import { createShare } from "@/api/share"
import { useKbForceRaptor } from "@/hooks/useKbForceRaptor"
import { useSystemSettingsStore } from "@/stores/systemSettingsStore"
import { copyToClipboard, formatFileSize, formatDate } from "@/utils"
import { fileTypeIcon } from "@/utils/fileIcons"
import MdNoteViewModal from "./MdNoteViewModal"
import KbVectorChunksModal from "./KbVectorChunksModal"
import MoveToFolderModal, { type MoveToFolderValue } from "./MoveToFolderModal"
import ReextractModal, { resolveReextractDefaultProvider, type ReextractProvider } from "./ReextractModal"
import KbFilePipelineTrace from "./KbFilePipelineTrace"
import { useFoldersStore } from "@/stores/foldersStore"
import { useWorkspaceStore } from "@/stores/workspaceStore"
import { folderDisplayNameForFile } from "@/lib/folderTree"
import { emitLibraryStatsRefresh } from "@/lib/libraryEvents"
import { useFlexTableBodyScrollY } from "@/hooks/useFlexTableBodyScrollY"
import "./FileList.css"

export type FileListHandle = { refresh: () => void }

type Props = {
  onPreview: (file: FileItem, anchorId?: string) => void
}

export function qualityWorkbenchPath(fileId: number): string {
  return `/admin/knowledge-base/quality-workbench?file_id=${fileId}`
}

const FileList = forwardRef<FileListHandle, Props>(function FileList({ onPreview }, ref) {
  const { modal, message: appMessage } = App.useApp()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const isAdmin = useAuthStore((s) => s.user?.is_admin === true)
  const files = useFilesStore((s) => s.files)
  const total = useFilesStore((s) => s.total)
  const page = useFilesStore((s) => s.page)
  const pageSize = useFilesStore((s) => s.pageSize)
  const loading = useFilesStore((s) => s.loading)
  const loadFiles = useFilesStore((s) => s.loadFiles)
  const patchFileIndex = useFilesStore((s) => s.patchFileIndex)
  const setPagination = useFilesStore((s) => s.setPagination)
  const timeSortOrder = useFilesStore((s) => s.timeSortOrder)
  const nameSortOrder = useFilesStore((s) => s.nameSortOrder)
  const listSortBy = useFilesStore((s) => s.listSortBy)
  const toggleTimeSort = useFilesStore((s) => s.toggleTimeSort)
  const toggleNameSort = useFilesStore((s) => s.toggleNameSort)
  const tagFilter = useFilesStore((s) => s.tagFilter)
  const tagFilter2 = useFilesStore((s) => s.tagFilter2)
  const clearTagFilters = useFilesStore((s) => s.clearTagFilters)
  const searchKeyword = useFilesStore((s) => s.searchKeyword)

  const clipboardPrefix = useSystemSettingsStore((s) => s.clipboard_prefix)
  const clipboardSuffix = useSystemSettingsStore((s) => s.clipboard_suffix)
  const loadSystemSettings = useSystemSettingsStore((s) => s.load)

  const [viewMode, setViewMode] = useState<"list" | "grid">("list")
  const [mdOpen, setMdOpen] = useState(false)
  const [mdFile, setMdFile] = useState<FileItem | null>(null)
  const [mdReadOnly, setMdReadOnly] = useState(false)
  const [renameOpen, setRenameOpen] = useState(false)
  const [renameText, setRenameText] = useState("")
  const [renameTarget, setRenameTarget] = useState<FileItem | null>(null)
  const [allTags, setAllTags] = useState<string[]>([])
  const [tagsModalOpen, setTagsModalOpen] = useState(false)
  const [tagsModalTarget, setTagsModalTarget] = useState<FileItem | null>(null)
  const [tagsDraft, setTagsDraft] = useState<string[]>([])
  /** tags 模式下未按回车确认的输入，需与 tagsDraft 合并后再提交 */
  const [tagInput, setTagInput] = useState("")
  /** 列表模式 Table.scroll.y：由 fl-body / 表格宿主实测高度计算，适配 flex 布局（如资料库 Tab） */
  const listBodyRef = useRef<HTMLDivElement | null>(null)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [vectorModalOpen, setVectorModalOpen] = useState(false)
  const [vectorModalFile, setVectorModalFile] = useState<FileItem | null>(null)
  const [moveModalOpen, setMoveModalOpen] = useState(false)
  const [moveTarget, setMoveTarget] = useState<FileItem | null>(null)
  const [moveSaving, setMoveSaving] = useState(false)
  const [reextractOpen, setReextractOpen] = useState(false)
  const [reextractTarget, setReextractTarget] = useState<FileItem | null>(null)
  const [reextractSaving, setReextractSaving] = useState(false)
  const [reextractEffectiveProvider, setReextractEffectiveProvider] = useState<ReextractProvider>("legacy")
  const [reindexingFileId, setReindexingFileId] = useState<number | null>(null)
  const [pipelineTraceOpen, setPipelineTraceOpen] = useState(false)
  const [pipelineTraceFile, setPipelineTraceFile] = useState<FileItem | null>(null)
  const folders = useFoldersStore((s) => s.folders)
  const fetchFolders = useFoldersStore((s) => s.fetchFolders)
  const refreshFolderFileCounts = useFoldersStore((s) => s.refreshFolderFileCounts)
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)

  useEffect(() => {
    if (activeWorkspaceId == null) return
    void fetchFolders()
  }, [fetchFolders, activeWorkspaceId])

  const pageFileIds = useMemo(() => files.map((f) => f.id), [files])
  const pageAllSelected =
    pageFileIds.length > 0 && pageFileIds.every((id) => selectedIds.includes(id))

  useEffect(() => {
    setSelectedIds([])
  }, [tagFilter, tagFilter2, searchKeyword, timeSortOrder, nameSortOrder, listSortBy, pageSize])

  const openVectorModal = useCallback((row: FileItem) => {
    setVectorModalFile(row)
    setVectorModalOpen(true)
  }, [])

  const clearSelection = useCallback(() => setSelectedIds([]), [])

  const toggleSelect = useCallback((id: number, checked: boolean) => {
    setSelectedIds((prev) => {
      if (checked) return prev.includes(id) ? prev : [...prev, id]
      return prev.filter((x) => x !== id)
    })
  }, [])

  const toggleSelectAllPage = useCallback(() => {
    setSelectedIds((prev) => {
      if (pageAllSelected) return prev.filter((id) => !pageFileIds.includes(id))
      return [...new Set([...prev, ...pageFileIds])]
    })
  }, [pageAllSelected, pageFileIds])

  async function refreshTagOptions() {
    try {
      const res = await listMyTags()
      setAllTags(res.data)
    } catch {
      /* interceptor */
    }
  }

  useEffect(() => {
    void loadFiles()
  }, [loadFiles])

  useEffect(() => {
    void refreshTagOptions()
  }, [])

  useEffect(() => {
    void loadSystemSettings()
  }, [loadSystemSettings])

  const refreshList = useCallback(() => {
    void loadFiles()
    void refreshTagOptions()
  }, [loadFiles, refreshTagOptions])

  useImperativeHandle(ref, () => ({
    refresh: refreshList,
  }))

  const listScrollY = useFlexTableBodyScrollY([loading, files.length, page, pageSize], {
    bodyRef: listBodyRef,
    enabled: viewMode === "list",
  })

  function renderFileTimeTooltip(row: FileItem) {
    return (
      <div>
        <div>
          {t("fileList.createdAtLabel")}: {formatDate(row.created_at)}
        </div>
        <div>
          {t("fileList.updatedAtLabel")}: {row.updated_at ? formatDate(row.updated_at) : "—"}
        </div>
      </div>
    )
  }

  function formatLastUpdatedCell(row: FileItem) {
    return row.updated_at ? formatDate(row.updated_at) : "—"
  }

  function toggleTimeSortHeader() {
    toggleTimeSort()
  }

  function toggleNameSortHeader() {
    toggleNameSort()
  }

  async function handleDownload(f: FileItem) {
    try {
      await downloadAuthenticatedFile(getDownloadUrl(f.id), f.original_name)
    } catch {
      appMessage.error(t("messages.downloadFailed"))
    }
  }

  async function copyShareLink(f: FileItem) {
    try {
      const res = await createShare({ file_id: f.id }, { skipErrorToast: true })
      const url = new URL(res.data.url, window.location.origin).href
      const text = `${clipboardPrefix}${url}${clipboardSuffix}`
      await copyToClipboard(text)
      appMessage.success(t("messages.copiedToClipboard"))
    } catch {
      appMessage.error(t("messages.shareLinkFailed"))
    }
  }

  function showRename(f: FileItem) {
    setRenameTarget(f)
    setRenameText(f.original_name)
    setRenameOpen(true)
  }


  const openReextractModal = useCallback(
    async (f: FileItem) => {
      await loadSystemSettings()
      const sysProvider = useSystemSettingsStore.getState().kb_extract_provider
      setReextractEffectiveProvider(resolveReextractDefaultProvider(sysProvider))
      setReextractTarget(f)
      setReextractOpen(true)
    },
    [loadSystemSettings],
  )

  const handleReextract = useCallback(
    async (f: FileItem, options: { force: boolean; provider: ReextractProvider | null }) => {
      setReextractSaving(true)
      try {
        const res = await reextractKnowledgeBaseFile(f.id, {
          force: options.force,
          ...(options.provider ? { provider: options.provider } : {}),
        })
        patchFileIndex(f.id, {
          extract_status: res.extract_status ?? "pending",
          extract_error: null,
          ...(options.force
            ? {
                has_md: false,
                md_has_content: false,
                extracted_at: null,
                extract_engine: null,
              }
            : {}),
        })
        appMessage.success(t("kbIndex.reextractOk"))
        setReextractOpen(false)
        setReextractTarget(null)
      } catch {
        appMessage.error(t("kbIndex.reextractFailed"))
      } finally {
        setReextractSaving(false)
      }
    },
    [appMessage, patchFileIndex, t],
  )

  const handleForceReindex = useCallback(
    (f: FileItem) => {
      const largeDocHint = isLikelyLargeDocByChunkCount(f.chunk_count)
      modal.confirm({
        title: t("kbChunks.forceReindexConfirmTitle"),
        content: buildForceReindexConfirmContent(t, {
          largeDocHint,
          chunkCount: f.chunk_count,
        }),
        okText: t("kbChunks.forceReindexBtn"),
        okButtonProps: { danger: true },
        onOk: async () => {
          setReindexingFileId(f.id)
          try {
            const res = await reindexKnowledgeBaseFile(f.id, { force: true })
            patchFileIndex(f.id, { index_status: res.index_status ?? "pending", index_error: null })
            appMessage.success(t("kbChunks.forceReindexOk"))
          } catch {
            appMessage.error(t("kbChunks.forceReindexFailed"))
          } finally {
            setReindexingFileId(null)
          }
        },
      })
    },
    [modal, appMessage, patchFileIndex, t],
  )

  const { confirmForceRaptor, forceRaptorLoadingFileId } = useKbForceRaptor({
    onQueued: (fileId, status) => {
      patchFileIndex(fileId, { kb_post_status: status, kb_post_error: null })
    },
  })

  const forceRaptorDisabledTip = useCallback(
    (row: FileItem): string | undefined => {
      const postStatus = row.kb_post_status
      if (
        (row.index_status ?? "") === "ready" &&
        (postStatus === "queued" || postStatus === "running")
      ) {
        return t("fileList.forceRaptorDisabledPostBusy")
      }
      if ((row.chunk_count ?? 0) < 2) {
        return t("fileList.forceRaptorDisabledFewChunks")
      }
      return undefined
    },
    [t],
  )

  function openMd(f: FileItem, readOnly = false) {
    if (!f.md_has_content) return
    setMdReadOnly(readOnly)
    void getFileById(f.id)
      .then((res) => {
        if (!res.data.md_has_content) {
          patchFileIndex(f.id, {
            has_md: res.data.has_md,
            md_has_content: false,
            extract_status: res.data.extract_status,
            extract_engine: res.data.extract_engine,
            extracted_at: res.data.extracted_at,
            extract_error: res.data.extract_error,
          })
          return
        }
        patchFileIndex(f.id, {
          has_md: res.data.has_md,
          md_has_content: res.data.md_has_content,
          extract_status: res.data.extract_status,
          extract_engine: res.data.extract_engine,
          extracted_at: res.data.extracted_at,
          extract_error: res.data.extract_error,
        })
        setMdFile(res.data)
        setMdOpen(true)
      })
      .catch(() => {
        if (!f.md_has_content) return
        setMdFile(f)
        setMdOpen(true)
      })
  }

  function mdActionTitle(row: FileItem, readOnly: boolean): string {
    if (readOnly) return t("filePreview.viewMd")
    return t("fileList.editMd")
  }

  function mdNoteTooltip(row: FileItem, readOnly: boolean): string {
    if (isExtractBusy(row.extract_status)) return t("fileList.mdNoteGenerating")
    if (row.md_has_content) return mdActionTitle(row, readOnly)
    return t("fileList.mdNoteNotReady")
  }

  function openTagsModal(f: FileItem) {
    setTagsModalTarget(f)
    setTagsDraft([...(f.tags ?? [])])
    setTagInput("")
    setTagsModalOpen(true)
  }

  function mergeTagDraft(draft: string[], pendingSearch: string): string[] {
    const p = pendingSearch.trim().toLowerCase()
    if (!p) return draft
    const next = [...draft]
    if (!next.some((x) => x.toLowerCase() === p)) next.push(p)
    return next
  }

  async function saveTagsModal() {
    if (!tagsModalTarget) return
    const merged = mergeTagDraft(tagsDraft, tagInput)
    await replaceFileTags(tagsModalTarget.id, merged)
    appMessage.success(t("fileList.tagsSaved"))
    setTagInput("")
    setTagsModalOpen(false)
    void refreshTagOptions()
    void loadFiles()
  }


  function openMoveModal(f: FileItem) {
    void fetchFolders()
    setMoveTarget(f)
    setMoveModalOpen(true)
  }

  async function confirmMove(value: MoveToFolderValue) {
    if (!moveTarget) return
    setMoveSaving(true)
    try {
      const folder_id = value === "uncategorized" ? null : value
      await updateFile(moveTarget.id, { folder_id })
      appMessage.success(t("messages.relocated"))
      setMoveModalOpen(false)
      setMoveTarget(null)
      void loadFiles()
      void refreshFolderFileCounts()
    } finally {
      setMoveSaving(false)
    }
  }

  async function doRename() {
    if (!renameTarget || !renameText.trim()) return
    await updateFile(renameTarget.id, { filename: renameText.trim() })
    setRenameOpen(false)
    void loadFiles()
  }

  function handleDelete(f: FileItem) {
    // 延后到下一宏任务：避免 Dropdown 未卸载时打开静态 Modal 导致确认框不显示或 onOk 不触发
    window.setTimeout(() => {
      modal.confirm({
        title: t("fileList.confirmPurge"),
        content: t("fileList.deleteConfirm", { name: f.original_name }),
        okType: "danger",
        onOk: async () => {
          await deleteFile(f.id)
          appMessage.success(t("messages.objectPurged"))
          setSelectedIds((prev) => prev.filter((id) => id !== f.id))
          emitLibraryStatsRefresh()
          void loadFiles()
          void refreshFolderFileCounts()
        },
      })
    }, 0)
  }

  function handleBatchDelete() {
    if (selectedIds.length === 0) return
    const count = selectedIds.length
    window.setTimeout(() => {
      modal.confirm({
        title: t("fileList.confirmPurge"),
        content: t("fileList.batchDeleteConfirm", { count }),
        okType: "danger",
        onOk: async () => {
          const { ok, fail, rebuildFailed } = await runFileBatchDelete({
            selectedIds,
            deleteFile,
            rebuildKnowledgeBaseIndex,
          })
          clearSelection()
          emitLibraryStatsRefresh()
          void loadFiles()
          void refreshFolderFileCounts()
          if (fail === 0) {
            appMessage.success(t("fileList.batchDeleteSuccess", { count: ok }))
          } else if (ok === 0) {
            appMessage.error(t("fileList.batchDeletePartial", { ok: 0, fail }))
          } else {
            appMessage.warning(t("fileList.batchDeletePartial", { ok, fail }))
          }
          if (rebuildFailed) {
            appMessage.error(t("knowledgeIndex.rebuildFailed"))
          }
        },
      })
    }, 0)
  }

  const rowSelection = useMemo(
    () => ({
      selectedRowKeys: selectedIds as Key[],
      onChange: (keys: Key[]) => setSelectedIds(keys as number[]),
    }),
    [selectedIds],
  )

  const renderListIcon = (f: FileItem) => {
    const icon = fileTypeIcon(f.mime_type, f.original_name)
    if (!f.has_thumbnail) {
      return <span className="fl-name-ico">{icon}</span>
    }
    return (
      <span className="fl-thumb-wrap fl-thumb-wrap--list">
        <img
          className="fl-thumb-img"
          src={getThumbnailUrl(f.id)}
          alt=""
          loading="lazy"
          decoding="async"
          onError={(e) => {
            e.currentTarget.classList.add("fl-thumb-img--hide")
            const fb = e.currentTarget.nextElementSibling as HTMLElement | null
            if (fb) fb.classList.remove("fl-thumb-fallback--hide")
          }}
        />
        <span className="fl-name-ico fl-thumb-fallback fl-thumb-fallback--hide">{icon}</span>
      </span>
    )
  }

  const renderGridIcon = (f: FileItem) => {
    const icon = fileTypeIcon(f.mime_type, f.original_name)
    if (!f.has_thumbnail) {
      return <div className="fl-card-icon">{icon}</div>
    }
    return (
      <div className="fl-thumb-wrap fl-thumb-wrap--grid">
        <img
          className="fl-thumb-img"
          src={getThumbnailUrl(f.id)}
          alt=""
          loading="lazy"
          decoding="async"
          onError={(e) => {
            e.currentTarget.classList.add("fl-thumb-img--hide")
            const fb = e.currentTarget.nextElementSibling as HTMLElement | null
            if (fb) fb.classList.remove("fl-thumb-fallback--hide")
          }}
        />
        <div className="fl-card-icon fl-thumb-fallback fl-thumb-fallback--hide">{icon}</div>
      </div>
    )
  }


  const renderFileOps = useCallback(
    (row: FileItem) => {
      const canWrite = row.can_write !== false
      const canManage = row.can_manage === true
      const moreMenuItems: MenuProps["items"] = [
        { key: "view", label: t("fileList.view"), icon: <EyeOutlined /> },
        { key: "pipelineTrace", label: t("kbPipeline.traceAction"), icon: <NodeIndexOutlined /> },
        ...(isAdmin
          ? [
              {
                key: "qualityWorkbench",
                label: t("knowledgeIndex.qualityWorkbench"),
                icon: <FileSearchOutlined />,
              },
            ]
          : []),
        { key: "download", label: t("fileList.download"), icon: <DownloadOutlined /> },
        ...(canWrite
          ? [
              { key: "rename", label: t("fileList.rename"), icon: <EditOutlined /> },
              { key: "move", label: t("folders.moveTo"), icon: <FolderOutlined /> },
            ]
          : []),
        ...(canWrite && canReextract(row)
          ? [
              {
                key: "reextract",
                label: t("kbIndex.reextract"),
                icon: <FileSearchOutlined />,
                disabled: isExtractBusy(row.extract_status),
                title: isExtractBusy(row.extract_status) ? t("kbIndex.reextractBusyTip") : undefined,
              },
            ]
          : []),
        ...(canWrite && row.has_md
          ? [
              {
                key: "reindex",
                label: t("knowledgeIndex.reindexRowAction"),
                icon: <ClusterOutlined />,
                disabled: reindexingFileId === row.id,
              },
            ]
          : []),
        ...(canWrite && row.has_md && (row.index_status ?? "") === "ready"
          ? [
              {
                key: "forceRaptor",
                label: t("fileList.forceRaptorAction"),
                icon: <ApartmentOutlined />,
                disabled:
                  Boolean(forceRaptorDisabledTip(row)) || forceRaptorLoadingFileId === row.id,
                title: forceRaptorDisabledTip(row),
              },
            ]
          : []),
        ...(canManage
          ? [
              {
                key: "delete",
                label: t("fileList.delete"),
                icon: <DeleteActionIcon />,
                danger: true,
              },
            ]
          : []),
        { type: "divider" as const },
        { key: "ai", label: t("fileList.aiProcessCommand"), icon: <RobotFilled /> },
      ]
      const onMoreMenuClick: MenuProps["onClick"] = ({ key, domEvent }) => {
        domEvent.stopPropagation()
        switch (key) {
          case "view":
            onPreview(row)
            break
          case "pipelineTrace":
            setPipelineTraceFile(row)
            setPipelineTraceOpen(true)
            break
          case "qualityWorkbench":
            navigate(qualityWorkbenchPath(row.id))
            break
          case "download":
            void handleDownload(row)
            break
          case "rename":
            showRename(row)
            break
          case "move":
            openMoveModal(row)
            break
          case "reextract":
            void openReextractModal(row)
            break
          case "reindex":
            handleForceReindex(row)
            break
          case "forceRaptor":
            confirmForceRaptor(row.id)
            break
          case "delete":
            handleDelete(row)
            break
          case "ai":
            void copyShareLink(row)
            break
          default:
            break
        }
      }
      return (
        <div className="fl-ops-cell" onClick={(e) => e.stopPropagation()}>
          <Space size={0} className="fl-ops-row fl-ops-row--primary" wrap={false}>
            {canWrite ? (
              <Button
                type="text"
                size="small"
                className={(row.tags?.length ?? 0) > 0 ? "fl-ops-tags-filled" : undefined}
                icon={<TagsOutlined />}
                title={t("fileList.editTags")}
                onClick={() => openTagsModal(row)}
              />
            ) : null}
            {canWrite || row.has_md ? (
              <Tooltip title={mdNoteTooltip(row, !canWrite && Boolean(row.has_md))}>
                <Button
                  type="text"
                  size="small"
                  disabled={!row.md_has_content}
                  className={[
                    "fl-ops-md-btn",
                    row.md_has_content ? "fl-ops-md-filled" : "fl-ops-md-btn--idle",
                    isExtractBusy(row.extract_status) ? "fl-ops-md-btn--busy" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  icon={<FileTextOutlined />}
                  aria-label={mdNoteTooltip(row, !canWrite && Boolean(row.has_md))}
                  onClick={() => openMd(row, !canWrite && Boolean(row.has_md))}
                />
              </Tooltip>
            ) : null}
            <Dropdown
              menu={{ items: moreMenuItems, onClick: onMoreMenuClick }}
              trigger={["click"]}
              placement="bottomRight"
            >
              <Button
                type="text"
                size="small"
                icon={<EllipsisOutlined />}
                title={t("fileList.moreOps")}
                onClick={(e) => e.stopPropagation()}
              />
            </Dropdown>
          </Space>
        </div>
      )
    },
    [
      t,
      isAdmin,
      navigate,
      onPreview,
      handleDownload,
      showRename,
      openMoveModal,
      openReextractModal,
      copyShareLink,
      openTagsModal,
      openMd,
      handleDelete,
      handleForceReindex,
      confirmForceRaptor,
      forceRaptorDisabledTip,
      forceRaptorLoadingFileId,
      reindexingFileId,
    ],
  )

  const columns = [
    {
      title: t("fileList.id"),
      key: "id",
      width: 72,
      align: "right" as const,
      className: "fl-id-col",
      render: (_: unknown, row: FileItem) => <span className="fl-id-cell">{row.id}</span>,
    },
    {
      title: (
        <button
          type="button"
          className="fl-time-sort-th fl-name-sort-th"
          title={t("fileList.sortNameTooltip")}
          aria-label={t("fileList.sortNameTooltip")}
          onClick={() => toggleNameSortHeader()}
        >
          <span className="fl-time-sort-th__label">{t("fileList.object")}</span>
          <span className="fl-time-sort-th__icons" aria-hidden>
            <CaretUpOutlined
              className={
                listSortBy === "name" && nameSortOrder === "asc"
                  ? "fl-time-sort-th__ico--on"
                  : "fl-time-sort-th__ico--off"
              }
            />
            <CaretDownOutlined
              className={
                listSortBy === "name" && nameSortOrder === "desc"
                  ? "fl-time-sort-th__ico--on"
                  : "fl-time-sort-th__ico--off"
              }
            />
          </span>
        </button>
      ),
      key: "name",
      className: "fl-name-col",
      ellipsis: true,
      render: (_: unknown, row: FileItem) => (
        <div className="fl-name">
          {renderListIcon(row)}
          <Tooltip title={row.original_name} placement="topLeft">
            <span className="fl-name-tooltip-trigger">
              <button
                type="button"
                className="fl-name-text fl-name-open"
                onClick={() => onPreview(row)}
              >
                {row.original_name}
              </button>
            </span>
          </Tooltip>
          {row.has_md ? (
            row.md_has_content ? (
              <button
                type="button"
                className={[
                  "fl-md-badge fl-md-badge--filled fl-md-badge--btn",
                  isExtractBusy(row.extract_status) ? "fl-md-badge--generating" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                title={mdNoteTooltip(row, row.can_write === false)}
                aria-label={mdNoteTooltip(row, row.can_write === false)}
                onClick={(e) => {
                  e.stopPropagation()
                  openMd(row, row.can_write === false)
                }}
              >
                MD
              </button>
            ) : isExtractBusy(row.extract_status) ? (
              <Tooltip title={t("fileList.mdNoteGenerating")}>
                <span className="fl-md-badge fl-md-badge--busy">MD</span>
              </Tooltip>
            ) : (
              <Tooltip title={t("fileList.mdNoteNotReady")}>
                <span className="fl-md-badge fl-md-badge--idle">MD</span>
              </Tooltip>
            )
          ) : null}
        </div>
      ),
    },
    {
      title: t("fileList.size"),
      width: 88,
      render: (_: unknown, row: FileItem) => (
        <span className="fl-size-cell">{formatFileSize(row.file_size)}</span>
      ),
    },
    {
      title: t("fileList.folder"),
      key: "folder",
      width: 132,
      ellipsis: true,
      className: "fl-folder-col",
      render: (_: unknown, row: FileItem) => (
        <FlTableMarqueeText
          text={folderDisplayNameForFile(row.folder_id, folders, t)}
          className="fl-folder-cell-text"
        />
      ),
    },
    {
      title: t("fileList.tags"),
      key: "tags",
      width: 52,
      align: "center" as const,
      render: (_: unknown, row: FileItem) => {
        const tags = row.tags ?? []
        const n = tags.length
        const countEl = (
          <span className={n > 0 ? "fl-tags-count fl-tags-count--has" : "fl-tags-count"}>{n}</span>
        )
        return (
          <Tooltip
            placement="topLeft"
            overlayClassName="fl-tags-tooltip-overlay"
            title={
              n === 0 ? (
                t("fileList.tagCountEmpty")
              ) : (
                <div className="fl-tags-tooltip-lines">
                  {tags.map((tg) => (
                    <div key={tg} className="fl-tags-tooltip-line">
                      {tg}
                    </div>
                  ))}
                </div>
              )
            }
          >
            <span className="fl-tags-cell fl-tags-cell--numeric">{countEl}</span>
          </Tooltip>
        )
      },
    },
    {
      title: <TableHeadAiBreak line2={t("kbIndex.indexStatusAfterAi")} />,
      key: "kb_index",
      width: 64,
      align: "center" as const,
      render: (_: unknown, row: FileItem) => <FlKbIndexCell row={row} onViewVectors={openVectorModal} />,
    },
    {
      key: "time",
      title: (
        <button
          type="button"
          className="fl-time-sort-th"
          title={t("fileList.sortTimeTooltip")}
          aria-label={t("fileList.sortTimeTooltip")}
          onClick={() => toggleTimeSortHeader()}
        >
          <span className="fl-time-sort-th__label">{t("fileList.lastUpdatedAt")}</span>
          <span className="fl-time-sort-th__icons" aria-hidden>
            <CaretUpOutlined
              className={
                listSortBy === "time" && timeSortOrder === "asc"
                  ? "fl-time-sort-th__ico--on"
                  : "fl-time-sort-th__ico--off"
              }
            />
            <CaretDownOutlined
              className={
                listSortBy === "time" && timeSortOrder === "desc"
                  ? "fl-time-sort-th__ico--on"
                  : "fl-time-sort-th__ico--off"
              }
            />
          </span>
        </button>
      ),
      width: 168,
      align: "right" as const,
      render: (_: unknown, row: FileItem) => (
        <Tooltip title={renderFileTimeTooltip(row)}>
          <span className="fl-time-cell">{formatLastUpdatedCell(row)}</span>
        </Tooltip>
      ),
    },
    {
      title: <TableHeadAiBreak line2={t("fileList.aiCommandAfterAi")} />,
      key: "aiCommand",
      width: 52,
      align: "center" as const,
      className: "fl-ai-command-col",
      render: (_: unknown, row: FileItem) => (
        <Tooltip title={t("fileList.aiProcessCommand")}>
          <Button
            type="text"
            size="small"
            className="fl-ai-command-btn"
            icon={<RobotFilled />}
            aria-label={t("fileList.aiProcessCommand")}
            onClick={() => void copyShareLink(row)}
          />
        </Tooltip>
      ),
    },
    {
      title: t("fileList.ops"),
      key: "ops",
      width: 100,
      className: "fl-ops-col",
      align: "center" as const,
      render: (_: unknown, row: FileItem) => renderFileOps(row),
    },
  ]

  /** flex 布局下列表区高度固定；始终启用 scroll.y，避免「未开滚动但被父级 overflow 裁切」 */
  const listTableScroll =
    viewMode === "list" && files.length > 0 && listScrollY > 0 ? { y: listScrollY } : undefined

  return (
    <div className="fl-panel-shell double-bezel-shell"><div className="fl-panel fl-panel--table-unified double-bezel-inner">
      <div className="fl-toolbar">
        <div className="fl-toolbar-l">
          <Radio.Group value={viewMode} onChange={(e) => setViewMode(e.target.value)} size="small" buttonStyle="solid">
            <Radio.Button value="list">{t("fileList.list")}</Radio.Button>
            <Radio.Button value="grid">{t("fileList.grid")}</Radio.Button>
          </Radio.Group>
          {tagFilter ? (
            <div className="fl-tag-filter-bar" aria-live="polite">
              <Tag color="processing" className="fl-tag-filter-tag">
                {tagFilter2
                  ? t("fileList.tagFilterAnd", { tag: tagFilter, tag2: tagFilter2 })
                  : t("fileList.tagFilterSingle", { tag: tagFilter })}
              </Tag>
              <Button type="link" size="small" className="fl-tag-filter-clear" onClick={() => clearTagFilters()}>
                {t("fileList.clearTagFilter")}
              </Button>
            </div>
          ) : null}
          {files.length > 0 ? (
            <div className="fl-toolbar-selection">
              <Button type="link" size="small" className="fl-toolbar-selection-link" onClick={toggleSelectAllPage}>
                {t("fileList.selectAllPage")}
              </Button>
              {selectedIds.length > 0 ? (
                <>
                  <span className="fl-toolbar-selection-count">
                    {t("fileList.selectedCount", { count: selectedIds.length })}
                  </span>
                  {selectedIds.every((id) => files.find((f) => f.id === id)?.can_manage === true) ? (
                    <Button
                      type="primary"
                      size="small"
                      danger
                      icon={<DeleteActionIcon />}
                      onClick={() => handleBatchDelete()}
                    >
                      {t("fileList.batchDelete")}
                    </Button>
                  ) : null}
                  <Button type="text" size="small" onClick={clearSelection}>
                    {t("fileList.clearSelection")}
                  </Button>
                </>
              ) : null}
            </div>
          ) : null}
        </div>
        <span className="fl-count">{t("fileList.objects", { count: total })}</span>
      </div>

      <div className="fl-table-shell">
      <div ref={listBodyRef} className="fl-body">
      {viewMode === "grid" ? (
        <div className="fl-grid">
          {files.map((f) => {
            const selected = selectedIds.includes(f.id)
            const cardClass = [
              "fl-card",
              (f.tags?.length ?? 0) > 0 ? "fl-card--with-tags" : "",
              selected ? "fl-card--selected" : "",
            ]
              .filter(Boolean)
              .join(" ")
            return (
            <div key={f.id} className={cardClass}>
              <Checkbox
                className="fl-card-select"
                checked={selected}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => toggleSelect(f.id, e.target.checked)}
              />
              <div className="fl-card-main">
                <div className="fl-card-icon-col" aria-hidden>
                  {renderGridIcon(f)}
                </div>
                <div className="fl-card-meta-col">
                  <div className="fl-card-name-row">
                    <Tooltip title={f.original_name} placement="topLeft">
                      <button
                        type="button"
                        className="fl-card-name fl-name-open"
                        onClick={() => onPreview(f)}
                      >
                        {f.original_name}
                      </button>
                    </Tooltip>
                    {f.has_md ? (
                      <span
                        className={[
                          "fl-md-badge-grid",
                          f.md_has_content ? "fl-md-badge-grid--filled" : "",
                          isExtractBusy(f.extract_status)
                            ? f.md_has_content
                              ? "fl-md-badge-grid--generating"
                              : "fl-md-badge-grid--busy"
                            : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                      >
                        MD
                      </span>
                    ) : null}
                  </div>
                  <div className="fl-card-id" title={`id: ${f.id}`}>
                    {t("fileList.id")} {f.id}
                  </div>
                  <div className="fl-card-folder" title={folderDisplayNameForFile(f.folder_id, folders, t)}>
                    <FlTableMarqueeText
                      text={folderDisplayNameForFile(f.folder_id, folders, t)}
                      className="fl-card-folder-text"
                    />
                  </div>
                  <div className="fl-card-size">{formatFileSize(f.file_size)}</div>
                  <Tooltip title={renderFileTimeTooltip(f)}>
                    <div className="fl-card-time">{formatLastUpdatedCell(f)}</div>
                  </Tooltip>
                  {(f.tags?.length ?? 0) > 0 ? <FlGridCardTags tags={f.tags!} /> : null}
                  <div className="fl-card-index"><FlKbIndexCell row={f} compact onViewVectors={openVectorModal} /></div>
                </div>
              </div>
              <div className="fl-card-actions" onClick={(e) => e.stopPropagation()}>
                {renderFileOps(f)}
              </div>
            </div>
            )
          })}
        </div>
      ) : (
        <Spin spinning={loading} className="fl-spin">
          <div className="fl-table-host">
            <Table<FileItem>
              className="fl-file-table"
              rowKey="id"
              dataSource={files}
              columns={columns}
              rowSelection={rowSelection}
              pagination={false}
              size="small"
              tableLayout="fixed"
              scroll={listTableScroll}
            />
          </div>
        </Spin>
      )}
      </div>

      <div className="fl-pager">
        <Pagination
          current={page}
          pageSize={pageSize}
          total={total}
          showSizeChanger
          pageSizeOptions={["10", "20", "50", "100"]}
          onChange={(p, ps) => setPagination(p, ps)}
        />
      </div>
      </div>

      <MdNoteViewModal
        open={mdOpen}
        file={mdFile}
        readOnly={mdReadOnly}
        onClose={() => setMdOpen(false)}
        onSaved={() => void loadFiles()}
      />

      <Modal
        open={renameOpen}
        title={t("fileList.renameTitle")}
        onOk={() => void doRename()}
        onCancel={() => setRenameOpen(false)}
        okText={t("common.confirm")}
        cancelText={t("common.cancel")}
      >
        <Input value={renameText} onChange={(e) => setRenameText(e.target.value)} placeholder={t("fileList.newDesignation")} size="large" />
      </Modal>

      <Modal
        open={tagsModalOpen}
        title={t("fileList.tagsModalTitle")}
        onOk={() => saveTagsModal()}
        onCancel={() => {
          setTagInput("")
          setTagsModalOpen(false)
        }}
        okText={t("common.confirm")}
        cancelText={t("common.cancel")}
        destroyOnClose
      >
        <div className="fl-tags-modal-toolbar">
          <Button
            type="link"
            size="small"
            disabled={tagsDraft.length === 0 && !tagInput.trim()}
            onClick={() => {
              setTagsDraft([])
              setTagInput("")
            }}
          >
            {t("fileList.clearAllTags")}
          </Button>
        </div>
        <Select
          mode="tags"
          style={{ width: "100%" }}
          placeholder={t("fileList.tagsPlaceholder")}
          value={tagsDraft}
          searchValue={tagInput}
          onSearch={setTagInput}
          onChange={(v) => {
            setTagsDraft(v)
            setTagInput("")
          }}
          tokenSeparators={[",", " ", ";"]}
          options={allTags.map((x) => ({ label: x, value: x }))}
        />
      </Modal>


      <MoveToFolderModal
        open={moveModalOpen}
        folders={folders}
        initialFolderId={moveTarget?.folder_id ?? null}
        confirming={moveSaving}
        onCancel={() => {
          setMoveModalOpen(false)
          setMoveTarget(null)
        }}
        onConfirm={confirmMove}
      />

      <ReextractModal
        open={reextractOpen}
        file={reextractTarget}
        effectiveProvider={reextractEffectiveProvider}
        insavloReady={useSystemSettingsStore.getState().kb_extract_insavlo_ready}
        confirming={reextractSaving}
        onCancel={() => {
          setReextractOpen(false)
          setReextractTarget(null)
        }}
        onConfirm={(provider, force) => {
          if (!reextractTarget) return
          void handleReextract(reextractTarget, { force, provider })
        }}
      />

      <KbVectorChunksModal
        open={vectorModalOpen}
        file={vectorModalFile}
        onClose={() => {
          setVectorModalOpen(false)
          setVectorModalFile(null)
        }}
      />

      <KbFilePipelineTrace
        open={pipelineTraceOpen}
        fileId={pipelineTraceFile?.id ?? null}
        filename={pipelineTraceFile?.original_name}
        onClose={() => {
          setPipelineTraceOpen(false)
          setPipelineTraceFile(null)
        }}
      />
    </div>
    </div>
  )
})

export default FileList
