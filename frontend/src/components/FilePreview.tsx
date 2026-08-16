import { useCallback, useEffect, useMemo, useState, useRef } from "react"
import { useTranslation } from "react-i18next"
import { NodeIndexOutlined } from "@ant-design/icons"
import { App, Modal, Tabs, Tooltip } from "antd"
import {
  getPreviewUrl,
  getDownloadUrl,
  downloadAuthenticatedFile,
  getFileMd,
  getFileWikiLinks,
  type FileItem,
  type WikiLinkOutItem,
  type WikiLinksResponse,
} from "@/api/files"
import { getAdminFileMd } from "@/api/adminWorkspaces"
import { formatFileSize, formatDate } from "@/utils"
import { openWikiOutlinkTarget } from "@/utils/openWikiOutlinkTarget"
import { bindWikiLinkClick, isWikiThemePage, renderNotePreviewHtml } from '@/utils/mdNotePreview'
import { markdownToSafeHtml } from '@/utils/markdownPreview'
import { useExtractAssetHydration } from '@/utils/useExtractAssetHydration'
import { getWikiPages } from "@/api/knowledgeBase"
import { dispatchWikiLinkNavigate } from "@/lib/wikiLinkEvents"
import "react-photo-view/dist/react-photo-view.css"
import MdNoteViewModal, { MD_NOTE_VIEW_MODAL_Z_INDEX } from "./MdNoteViewModal"
import {
  BacklinkHeaderTrigger,
  OutlinkHeaderTrigger,
  uniqueBacklinkBySource,
  uniqueOutlinkByTarget,
} from "./WikiLinkHeaderTriggers"
import WikiLinksListModal, { type WikiLinkListKind } from "./WikiLinksListModal"
import { FilePreviewBody } from "./filePreview/FilePreviewBody"
import KbChunkPanel from "./KbChunkPanel"
import KbFilePipelineTrace from "./KbFilePipelineTrace"
import { resolveKbChunkPanelAccess } from "@/lib/kbChunkPanelAccess"
import { useAuthStore } from "@/stores/authStore"
import { useFilesStore } from "@/stores/filesStore"
import {
  isDocxLike,
  isExcelLike,
  isEmlLike,
  isHtmlLike,
  isMarkdownSourceFile,
  isPdfLike,
  isPptxLike,
  type ExcelPreviewTab,
} from "./filePreview/filePreviewMime"
import { useFilePreviewOfficeRender } from "./filePreview/useFilePreviewOfficeRender"
import "./MdNoteViewModal.css"
import "./FilePreview.css"

/** 文件预览 Modal 与资料 Markdown 附注 Modal 的层级（附注须在上层） */
const PREVIEW_MODAL_Z_INDEX = 1000

type PptxPreviewer = {
  destroy: () => void
  preview: (file: ArrayBuffer) => Promise<unknown>
}

function bindWikiLinkClickForPreview(root: HTMLElement, onActivate: (el: HTMLAnchorElement) => void) {
  return bindWikiLinkClick(root, onActivate)
}

type Props = {
  open: boolean
  file: FileItem | null
  onClose: () => void
  /** 打开预览后滚到该 id（锚点位于资料 Markdown 笔记内） */
  scrollToAnchorId?: string | null
  /** 打开时直接进入资料笔记预览（无锚点） */
  openMdNote?: boolean
  /** 管理端：跨用户读 MD 笔记 */
  adminMdApi?: boolean
}

export function resolveMdPreviewHydrationState(args: {
  open: boolean
  fileId?: number
  mdHtml: string
  mdFileLoading: boolean
}): { enabled: boolean; contentKey: string } {
  const { open, fileId, mdHtml, mdFileLoading } = args
  return {
    enabled: Boolean(mdHtml && fileId && open && !mdFileLoading),
    contentKey: `${fileId ?? 'none'}:${mdFileLoading ? 'loading' : 'ready'}:${mdHtml}`,
  }
}

export async function loadPreviewMarkdown(file: FileItem, adminMdApi = false): Promise<string> {
  if (isEmlLike(file)) {
    const res = adminMdApi ? await getAdminFileMd(file.id) : await getFileMd(file.id)
    return String(res.data ?? '')
  }
  const res = await fetch(getPreviewUrl(file.id))
  return res.text()
}

export default function FilePreview({ open, file, onClose, scrollToAnchorId, openMdNote = false, adminMdApi = false }: Props) {
  const { t } = useTranslation()
  const { message: appMessage } = App.useApp()
  const currentUser = useAuthStore((s) => s.user)
  const patchFileIndex = useFilesStore((s) => s.patchFileIndex)
  const [previewTab, setPreviewTab] = useState<"preview" | "chunks">("preview")
  const [mdHtml, setMdHtml] = useState("")
  const [mdFileSource, setMdFileSource] = useState("")
  const [mdFileLoading, setMdFileLoading] = useState(false)
  const [txtContent, setTxtContent] = useState("")
  const mdContainerRef = useRef<HTMLDivElement>(null)
  const [mdNoteOpen, setMdNoteOpen] = useState(false)
  const [wikiLinks, setWikiLinks] = useState<WikiLinksResponse | null>(null)
  const [listModalKind, setListModalKind] = useState<WikiLinkListKind | null>(null)
  const [pipelineTraceOpen, setPipelineTraceOpen] = useState(false)
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null)
  const [pdfLoadError, setPdfLoadError] = useState(false)
  const [htmlBlobUrl, setHtmlBlobUrl] = useState<string | null>(null)
  const [htmlLoadError, setHtmlLoadError] = useState(false)
  const [officeLoading, setOfficeLoading] = useState(false)
  const [officeError, setOfficeError] = useState(false)
  const docxBodyRef = useRef<HTMLDivElement>(null)
  const pptxWrapperRef = useRef<HTMLDivElement>(null)
  const pptxPreviewerRef = useRef<PptxPreviewer | null>(null)
  const [excelTabs, setExcelTabs] = useState<ExcelPreviewTab[]>([])

  const previewUrl = file ? getPreviewUrl(file.id) : ""

  const mdNoteOnlyPreview = Boolean(open && file && openMdNote && file.has_md && !scrollToAnchorId)
  const hideMainFilePreview = mdNoteOnlyPreview
  const mdEditorOpen = mdNoteOpen || mdNoteOnlyPreview

  useEffect(() => {
    if (!open || !file?.id) {
      setWikiLinks(null)
      return
    }
    if (!file.has_md && !isMarkdownSourceFile(file)) {
      setWikiLinks(null)
      return
    }
    let cancelled = false
    void getFileWikiLinks(file.id)
      .then((res) => {
        if (!cancelled) setWikiLinks(res.data)
      })
      .catch(() => {
        if (!cancelled) setWikiLinks(null)
      })
    return () => {
      cancelled = true
    }
  }, [open, file?.id, file?.has_md])

  useEffect(() => {
    if (!open) {
      setOfficeLoading(false)
      setOfficeError(false)
    }
  }, [open])

  useEffect(() => {
    if (!file) return
    if (!isDocxLike(file) && !isPptxLike(file) && !isExcelLike(file)) {
      setOfficeLoading(false)
      setOfficeError(false)
    }
  }, [file?.id, file?.mime_type, file?.original_name, file?.preview_mime_type])

  useEffect(() => {
    if (!file || !open) return
    const run = async () => {
      if (file.mime_type === "text/markdown" || isEmlLike(file)) {
        if (isWikiThemePage(file) && file.has_md) {
          setMdFileLoading(true)
          try {
            const res = await getFileMd(file.id)
            const text = String(res.data ?? "")
            setMdFileSource(text)
            setMdHtml(renderNotePreviewHtml(text, file.tag_anchors ?? [], [], file.id))
          } catch {
            setMdFileSource("")
            setMdHtml("")
          } finally {
            setMdFileLoading(false)
          }
          return
        }
        if (file.has_md && scrollToAnchorId && !isEmlLike(file)) {
          setMdFileSource("")
          setMdHtml("")
          setMdFileLoading(false)
          return
        }
        setMdFileLoading(true)
        try {
          const text = await loadPreviewMarkdown(file, adminMdApi)
          setMdFileSource(text)
          setMdHtml(markdownToSafeHtml(text, { fileId: file.id }))
        } catch {
          setMdFileSource("")
          setMdHtml("")
        } finally {
          setMdFileLoading(false)
        }
      } else if (file.mime_type === "text/plain") {
        try {
          const res = await fetch(getPreviewUrl(file.id))
          setTxtContent(await res.text())
        } catch {
          setTxtContent("")
        }
      }
    }
    void run()
  }, [
    open,
    file?.id,
    file?.mime_type,
    file?.has_md,
    file?.page_kind,
    file?.tag_anchors,
    scrollToAnchorId,
    adminMdApi,
  ])

  useEffect(() => {
    if (!open) {
      setMdNoteOpen(false)
      return
    }
    if (!file?.id) return
    if (scrollToAnchorId) {
      if (!file.has_md) {
        setMdNoteOpen(false)
        appMessage.warning(t("filePreview.anchorNeedsNote"))
      } else {
        setMdNoteOpen(true)
      }
    } else if (openMdNote) {
      if (!file.has_md || !file.md_has_content) {
        setMdNoteOpen(false)
        appMessage.warning(t(file.has_md ? "fileList.mdNoteNotReady" : "filePreview.noMdNote"))
      } else {
        setMdNoteOpen(true)
      }
    } else {
      setMdNoteOpen(false)
    }
  }, [open, file?.id, file?.page_kind, scrollToAnchorId, openMdNote, file?.has_md, appMessage, t])

  useEffect(() => {
    if (!open) {
      setHtmlBlobUrl(null)
      setHtmlLoadError(false)
      return
    }
    if (!file || !isHtmlLike(file)) {
      setHtmlBlobUrl(null)
      setHtmlLoadError(false)
      return
    }
    setHtmlBlobUrl(null)
    setHtmlLoadError(false)
    let cancelled = false
    let objectUrl: string | null = null
    void (async () => {
      try {
        const res = await fetch(getPreviewUrl(file.id))
        if (!res.ok) throw new Error(String(res.status))
        const buf = await res.arrayBuffer()
        const blob = new Blob([buf], { type: "text/html" })
        objectUrl = URL.createObjectURL(blob)
        if (cancelled) {
          URL.revokeObjectURL(objectUrl)
          return
        }
        setHtmlBlobUrl(objectUrl)
      } catch {
        if (!cancelled) setHtmlLoadError(true)
      }
    })()
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [open, file?.id, file?.mime_type, file?.original_name, file?.preview_mime_type])

  useEffect(() => {
    if (!open) {
      setPdfBlobUrl(null)
      setPdfLoadError(false)
      return
    }
    if (!file || !isPdfLike(file)) {
      setPdfBlobUrl(null)
      setPdfLoadError(false)
      return
    }
    setPdfBlobUrl(null)
    setPdfLoadError(false)
    let cancelled = false
    let objectUrl: string | null = null
    void (async () => {
      try {
        const res = await fetch(getPreviewUrl(file.id))
        if (!res.ok) throw new Error(String(res.status))
        const buf = await res.arrayBuffer()
        const blob = new Blob([buf], { type: "application/pdf" })
        objectUrl = URL.createObjectURL(blob)
        if (cancelled) {
          URL.revokeObjectURL(objectUrl)
          return
        }
        setPdfBlobUrl(objectUrl)
      } catch {
        if (!cancelled) setPdfLoadError(true)
      }
    })()
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [open, file?.id, file?.mime_type, file?.original_name, file?.preview_mime_type])

  useFilePreviewOfficeRender({
    open,
    file,
    docxBodyRef,
    pptxWrapperRef,
    pptxPreviewerRef,
    setOfficeLoading,
    setOfficeError,
    setExcelTabs,
  })

  const dismissMdNote = useCallback(() => {
    setMdNoteOpen(false)
    if (file && file.has_md && !scrollToAnchorId && openMdNote) {
      onClose()
    }
  }, [file, scrollToAnchorId, openMdNote, onClose])

  const activateWikiLink = useCallback(
    (anchor: HTMLAnchorElement) => {
      const fileIdRaw = anchor.getAttribute("data-wiki-file-id")
      const slug = anchor.getAttribute("data-wiki-slug")
      if (fileIdRaw) {
        const fileId = Number(fileIdRaw)
        if (Number.isFinite(fileId) && fileId > 0) {
          dispatchWikiLinkNavigate({ fileId })
          return
        }
      }
      if (slug) {
        void getWikiPages()
          .then((res) => {
            const hit = res.items.find((p) => p.wiki_slug === slug)
            if (hit) dispatchWikiLinkNavigate({ fileId: hit.file_id })
            else appMessage.warning(t("filePreview.wikiLinkBroken"))
          })
          .catch(() => appMessage.warning(t("filePreview.wikiLinkBroken")))
      }
    },
    [appMessage, t],
  )

  useEffect(() => {
    const root = mdContainerRef.current
    if (!root || !mdHtml || mdFileLoading) return
    return bindWikiLinkClickForPreview(root, activateWikiLink)
  }, [mdHtml, mdFileLoading, activateWikiLink])

  const mdPreviewHydration = resolveMdPreviewHydrationState({
    open,
    fileId: file?.id,
    mdHtml,
    mdFileLoading,
  })

  useExtractAssetHydration(mdContainerRef, {
    fileId: file?.id,
    contentKey: mdPreviewHydration.contentKey,
    enabled: mdPreviewHydration.enabled,
  })

  const openWikiOutlinkFromList = useCallback(
    (ol: WikiLinkOutItem) => {
      setListModalKind(null)
      setMdNoteOpen(false)
      void openWikiOutlinkTarget(ol, () => appMessage.warning(t("filePreview.wikiLinkBroken")))
    },
    [appMessage, t],
  )

  const uniqueOutlinks = wikiLinks ? uniqueOutlinkByTarget(wikiLinks.outlinks) : []
  const uniqueBacklinks = wikiLinks ? uniqueBacklinkBySource(wikiLinks.backlinks) : []

  const outlinkCountLabel =
    wikiLinks != null ? t("filePreview.outlinkCount", { count: uniqueOutlinks.length }) : null

  const backlinkCountLabel =
    wikiLinks != null ? t("filePreview.backlinkCount", { count: uniqueBacklinks.length }) : null

  const downloadFile = useCallback(async () => {
    if (!file) return
    try {
      await downloadAuthenticatedFile(getDownloadUrl(file.id), file.original_name)
    } catch {
      appMessage.error(t("messages.downloadFailed"))
    }
  }, [file, appMessage, t])

  useEffect(() => {
    if (open) setPreviewTab("preview")
  }, [open, file?.id])

  const { canEdit: canEditChunks, canReindex: canReindexChunks } = useMemo(
    () =>
      resolveKbChunkPanelAccess({
        fileOwnerId: file?.user_id,
        currentUserId: currentUser?.id,
        isAdmin: currentUser?.is_admin,
      }),
    [file, currentUser],
  )

  if (!file) return null
  const activeFile = file

  const previewBody = (
    <FilePreviewBody
      file={activeFile}
      previewUrl={previewUrl}
      scrollToAnchorId={scrollToAnchorId}
      pdfBlobUrl={pdfBlobUrl}
      pdfLoadError={pdfLoadError}
      htmlBlobUrl={htmlBlobUrl}
      htmlLoadError={htmlLoadError}
      officeLoading={officeLoading}
      officeError={officeError}
      excelTabs={excelTabs}
      docxBodyRef={docxBodyRef}
      pptxWrapperRef={pptxWrapperRef}
      mdFileSource={mdFileSource}
      mdHtml={mdHtml}
      mdFileLoading={mdFileLoading}
      mdContainerRef={mdContainerRef}
      txtContent={txtContent}
      onDownload={() => void downloadFile()}
      t={t}
    />
  )
  return (
    <>
      <Modal
        open={open && !hideMainFilePreview}
        onCancel={onClose}
        title={
          <div className="pv-header-title">
            <span className="pv-header-title-name" title={activeFile.original_name}>
              {activeFile.original_name}
            </span>
            <div className="pv-header-links">
              <button
                type="button"
                className="pv-header-link-stat pv-header-link-stat-btn pv-header-pipeline-trace"
                onClick={() => setPipelineTraceOpen(true)}
              >
                <NodeIndexOutlined className="pv-header-pipeline-trace__icon" aria-hidden />
                {t("kbPipeline.traceAction")}
              </button>
              {activeFile.has_md && wikiLinks != null ? (
                <>
                  {outlinkCountLabel != null ? (
                    <OutlinkHeaderTrigger
                      label={outlinkCountLabel}
                      count={uniqueOutlinks.length}
                      onOpenList={() => setListModalKind("outlinks")}
                    />
                  ) : null}
                  {backlinkCountLabel != null ? (
                    <BacklinkHeaderTrigger
                      label={backlinkCountLabel}
                      count={uniqueBacklinks.length}
                      onOpenList={() => setListModalKind("backlinks")}
                    />
                  ) : null}
                </>
              ) : null}
            </div>
          </div>
        }
        width="80%"
        style={{ top: "3vh" }}
        footer={null}
        destroyOnClose
        rootClassName="pv-root-modal"
        zIndex={PREVIEW_MODAL_Z_INDEX}
      >
        <div className="pv-body">
          <Tabs
            className="pv-tabs"
            activeKey={previewTab}
            onChange={(key) => setPreviewTab(key as "preview" | "chunks")}
            destroyInactiveTabPane={false}
            items={[
              {
                key: "preview",
                label: t("filePreview.tabPreview"),
                children: previewBody,
              },
              {
                key: "chunks",
                label: t("filePreview.tabIndexChunks"),
                children: (
                  <KbChunkPanel
                    file={activeFile}
                    canEdit={canEditChunks}
                    canReindex={canReindexChunks}
                    embedded
                    active={previewTab === "chunks"}
                    onIndexStatusChange={(status) => {
                      patchFileIndex(activeFile.id, { index_status: status, index_error: null })
                    }}
                  />
                ),
              },
            ]}
          />
        </div>
        <div className="pv-meta">
          <span className="pv-meta-item">{formatFileSize(activeFile.file_size)}</span>
          <span className="pv-meta-sep">·</span>
          <span className="pv-meta-item">{formatDate(activeFile.created_at)}</span>
          {activeFile.has_md ? (
            <>
              <span className="pv-meta-sep">·</span>
              {activeFile.md_has_content ? (
                <button type="button" className="pv-md-link" onClick={() => setMdNoteOpen(true)}>
                  {t("filePreview.viewMd")}
                </button>
              ) : (
                <Tooltip title={t("fileList.mdNoteNotReady")}>
                  <span className="pv-md-link pv-md-link--idle">{t("filePreview.viewMd")}</span>
                </Tooltip>
              )}
              {scrollToAnchorId ? (
                <>
                  <span className="pv-meta-sep">·</span>
                  <span className="pv-meta-item pv-meta-item--sub">{t("filePreview.anchorInNoteOnlyMeta")}</span>
                </>
              ) : null}
            </>
          ) : null}
        </div>
      </Modal>
      <MdNoteViewModal
        open={mdEditorOpen}
        file={file}
        scrollToAnchorId={scrollToAnchorId}
        onClose={dismissMdNote}
        adminMdApi={adminMdApi}
        zIndex={MD_NOTE_VIEW_MODAL_Z_INDEX}
      />

      {listModalKind && wikiLinks != null ? (
        <WikiLinksListModal
          open
          onClose={() => setListModalKind(null)}
          fileId={activeFile.id}
          fileName={activeFile.original_name}
          linkKind={listModalKind}
          initialData={wikiLinks}
          zIndex={MD_NOTE_VIEW_MODAL_Z_INDEX + 100}
          onOpenOutlink={openWikiOutlinkFromList}
          onOpenFile={(targetFileId, meta) => {
            setListModalKind(null)
            setMdNoteOpen(false)
            dispatchWikiLinkNavigate({ fileId: targetFileId, anchorId: meta?.anchorId })
          }}
        />
      ) : null}

      <KbFilePipelineTrace
        open={pipelineTraceOpen}
        fileId={activeFile?.id ?? null}
        filename={activeFile?.original_name}
        onClose={() => setPipelineTraceOpen(false)}
      />
    </>
  )
}
