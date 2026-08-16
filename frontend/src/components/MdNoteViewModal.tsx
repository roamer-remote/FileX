import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { App, Alert, Button, Modal, Spin, Tabs } from 'antd'
import {
  deleteFileMd,
  getFileById,
  getFileMd,
  getFileOkfMeta,
  getFileOkfRaw,
  getFileWikiLinks,
  putFileOkfMeta,
  uploadFileMd,
  type FileItem,
  type FileTagAnchorItem,
  type WikiLinkOutItem,
  type WikiLinksResponse,
} from '@/api/files'
import { getAdminFileMd } from '@/api/adminWorkspaces'
import { formatApiError } from '@/api/index'
import { getWikiPages } from '@/api/knowledgeBase'
import ExtractEngineFooter from '@/components/ExtractEngineFooter'
import { DeleteActionIcon } from '@/components/DeleteActionIcon'
import MdSplitView from '@/components/MdSplitView'
import {
  BacklinkHeaderTrigger,
  OutlinkHeaderTrigger,
  uniqueBacklinkBySource,
  uniqueOutlinkByTarget,
} from '@/components/WikiLinkHeaderTriggers'
import WikiLinksListModal, { type WikiLinkListKind } from '@/components/WikiLinksListModal'
import { dispatchWikiLinkNavigate } from '@/lib/wikiLinkEvents'
import { useFilesStore } from '@/stores/filesStore'
import {
  anchorBelongsToNote,
  anchorScrollHint,
  bindWikiLinkClick,
  isWikiThemePage,
  renderNotePreviewHtml,
  scrollToAnchorWithRetry,
  waitPaintFrames,
} from '@/utils/mdNotePreview'
import { useExtractAssetHydration } from '@/utils/useExtractAssetHydration'
import { openWikiOutlinkTarget } from '@/utils/openWikiOutlinkTarget'
import OkfMetadataForm from '@/components/OkfMetadataForm'
import {
  buildOkfMetaPutPayload,
  emptyOkfMetadataDraft,
  okfMetadataDraftFromApi,
  okfMetadataDraftsEqual,
  type OkfMetadataDraft,
} from '@/lib/okfMetadata'
import {
  mdNoteContentLoadKey,
  shouldReloadMdOnHasMdReady,
} from '@/lib/mdNoteReload'
import './MdNoteViewModal.css'
import './OkfMetadataForm.css'
import './FilePreview.css'

export const MD_NOTE_VIEW_MODAL_Z_INDEX = 1100

export type MdNoteViewModalProps = {
  open: boolean
  file: FileItem | null
  onClose: () => void
  onSaved?: () => void
  readOnly?: boolean
  /** 管理端跨用户读 MD：走 GET /admin/files/{id}/md 并强制只读 */
  adminMdApi?: boolean
  scrollToAnchorId?: string | null
  zIndex?: number
}

function resolveTitle(
  file: FileItem,
  t: (key: string, opts?: Record<string, unknown>) => string,
  readOnly: boolean,
): string {
  if (isWikiThemePage(file) || readOnly) {
    return t('knowledgeIndex.mdPreviewTitle', { name: file.original_name })
  }
  if (!file.has_md) {
    return t('mdEditor.newNote')
  }
  return t('filePreview.mdNote')
}

function mergeFileKbMeta(base: FileItem, overlay: FileItem): FileItem {
  return {
    ...base,
    extract_status: overlay.extract_status,
    extract_error: overlay.extract_error,
    extracted_at: overlay.extracted_at,
    extract_engine: overlay.extract_engine,
    has_md: overlay.has_md,
    md_has_content: overlay.md_has_content,
    okf_concept_path: overlay.okf_concept_path ?? base.okf_concept_path,
    okf_type: overlay.okf_type ?? base.okf_type,
    okf_metadata: overlay.okf_metadata ?? base.okf_metadata,
    tags: overlay.tags ?? base.tags,
  }
}

type NoteEditorTab = 'body' | 'metadata' | 'raw'

export default function MdNoteViewModal({
  open,
  file,
  onClose,
  onSaved,
  readOnly = false,
  adminMdApi = false,
  scrollToAnchorId = null,
  zIndex = MD_NOTE_VIEW_MODAL_Z_INDEX,
}: MdNoteViewModalProps) {
  const effectiveReadOnly = readOnly || adminMdApi
  const { t } = useTranslation()
  const { message: appMessage } = App.useApp()
  const patchFileIndex = useFilesStore((s) => s.patchFileIndex)
  const fileFromStore = useFilesStore((s) =>
    file?.id != null ? s.files.find((f) => f.id === file.id) : undefined,
  )
  const [liveFile, setLiveFile] = useState<FileItem | null>(null)
  const displayFile = useMemo(() => {
    if (!file) return null
    let merged = file
    if (fileFromStore) merged = mergeFileKbMeta(merged, fileFromStore)
    if (liveFile) merged = mergeFileKbMeta(merged, liveFile)
    return merged
  }, [file, fileFromStore, liveFile])

  const mdNoteRawRef = useRef('')
  const mdNoteAnchorsRef = useRef<FileTagAnchorItem[]>([])
  const mdNoteWikiOutlinksRef = useRef<WikiLinkOutItem[]>([])
  const previewRef = useRef<HTMLDivElement>(null)

  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [source, setSource] = useState('')
  const [savedSource, setSavedSource] = useState('')
  const [previewHtml, setPreviewHtml] = useState('')
  const [wikiLinks, setWikiLinks] = useState<WikiLinksResponse | null>(null)
  const [listModalKind, setListModalKind] = useState<WikiLinkListKind | null>(null)
  const [activeTab, setActiveTab] = useState<NoteEditorTab>('body')
  const [metaDraft, setMetaDraft] = useState<OkfMetadataDraft>(() => emptyOkfMetadataDraft())
  const [savedMetaDraft, setSavedMetaDraft] = useState<OkfMetadataDraft>(() => emptyOkfMetadataDraft())
  const [metaLoading, setMetaLoading] = useState(false)
  const [metaLoadError, setMetaLoadError] = useState<string | null>(null)
  const [metaSaving, setMetaSaving] = useState(false)
  const [okfRaw, setOkfRaw] = useState('')
  const [okfRawLoading, setOkfRawLoading] = useState(false)
  const [okfRawError, setOkfRawError] = useState<string | null>(null)

  const dirty = source !== savedSource
  const metaDirty = !okfMetadataDraftsEqual(metaDraft, savedMetaDraft)
  const dirtyRef = useRef(false)
  dirtyRef.current = dirty

  const fileId = file?.id
  const mergedHasMd = Boolean(
    liveFile?.has_md ?? fileFromStore?.has_md ?? file?.has_md,
  )
  const [mdReloadToken, setMdReloadToken] = useState(0)
  const prevMergedHasMdRef = useRef<boolean | null>(null)
  const mdContentLoadKey = mdNoteContentLoadKey({
    open,
    fileId,
    hasMd: mergedHasMd,
    reloadToken: mdReloadToken,
    scrollToAnchorId,
    adminMdApi,
    effectiveReadOnly,
  })

  useEffect(() => {
    if (!open) setDeleteConfirmOpen(false)
  }, [open])

  useEffect(() => {
    if (!open) {
      setActiveTab('body')
      setMetaDraft(emptyOkfMetadataDraft())
      setSavedMetaDraft(emptyOkfMetadataDraft())
      setMetaLoadError(null)
      setOkfRaw('')
      setOkfRawError(null)
    }
  }, [open])

  const showOkfTabs = mergedHasMd && !adminMdApi

  useEffect(() => {
    if (!open || fileId == null || !showOkfTabs) {
      setMetaLoading(false)
      return
    }
    let cancelled = false
    setMetaLoading(true)
    setMetaLoadError(null)
    void getFileOkfMeta(fileId)
      .then((res) => {
        if (cancelled) return
        const draft = okfMetadataDraftFromApi(res.data, displayFile?.original_name ?? '')
        setMetaDraft(draft)
        setSavedMetaDraft(draft)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setMetaLoadError(formatApiError(err) || t('okfNative.metadataLoadFailed'))
      })
      .finally(() => {
        if (!cancelled) setMetaLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, fileId, showOkfTabs, mdReloadToken, displayFile?.original_name, t])

  useEffect(() => {
    if (!open || fileId == null || activeTab !== 'raw' || !showOkfTabs) return
    let cancelled = false
    setOkfRawLoading(true)
    setOkfRawError(null)
    void getFileOkfRaw(fileId)
      .then((res) => {
        if (cancelled) return
        setOkfRaw(String(res.data ?? ''))
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setOkfRawError(formatApiError(err) || t('okfNative.rawLoadFailed'))
        setOkfRaw('')
      })
      .finally(() => {
        if (!cancelled) setOkfRawLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, fileId, activeTab, showOkfTabs, mdReloadToken, t])

  useEffect(() => {
    if (!open || fileId == null) {
      prevMergedHasMdRef.current = null
      return
    }
    const prev = prevMergedHasMdRef.current
    prevMergedHasMdRef.current = mergedHasMd
    if (shouldReloadMdOnHasMdReady(prev, mergedHasMd, dirtyRef.current)) {
      setMdReloadToken((n) => n + 1)
    }
  }, [open, fileId, mergedHasMd])

  useEffect(() => {
    if (!open || !file?.id) {
      setLiveFile(null)
      return
    }
    let cancelled = false
    void getFileById(file.id)
      .then((res) => {
        if (!cancelled) setLiveFile(res.data)
      })
      .catch(() => {
        if (!cancelled) setLiveFile(null)
      })
    return () => {
      cancelled = true
    }
  }, [open, file?.id])

  useEffect(() => {
    if (!open || !file?.id) return
    const status =
      liveFile?.extract_status ?? fileFromStore?.extract_status ?? file.extract_status
    if (status !== 'pending' && status !== 'extracting') return
    const timer = window.setInterval(() => {
      void getFileById(file.id)
        .then((res) => setLiveFile(res.data))
        .catch(() => undefined)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [open, file?.id, file?.extract_status, fileFromStore?.extract_status, liveFile?.extract_status])

  useEffect(() => {
    if (!open || !file?.id) {
      setWikiLinks(null)
      return
    }
    if (!displayFile?.has_md) {
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
  }, [open, file?.id, displayFile?.has_md])

  useEffect(() => {
    if (!mdContentLoadKey || fileId == null) {
      setSource('')
      setSavedSource('')
      setPreviewHtml('')
      setLoadError(null)
      setLoading(false)
      return
    }

    if (dirtyRef.current) return

    if (!mergedHasMd && !effectiveReadOnly) {
      mdNoteRawRef.current = ''
      mdNoteAnchorsRef.current = file?.tag_anchors ?? []
      mdNoteWikiOutlinksRef.current = []
      setSource('')
      setSavedSource('')
      setPreviewHtml(renderNotePreviewHtml('', mdNoteAnchorsRef.current, mdNoteWikiOutlinksRef.current, fileId))
      setLoadError(null)
      setLoading(false)
      return
    }

    if (!mergedHasMd && effectiveReadOnly) {
      setLoadError(t('filePreview.noMdNote'))
      setSource('')
      setPreviewHtml('')
      setLoading(false)
      return
    }

    let cancelled = false
    setLoading(true)
    setLoadError(null)
    void (async () => {
      let anchors = file?.tag_anchors ?? []
      let wikiOutlinks: WikiLinkOutItem[] = []
      if (scrollToAnchorId) {
        try {
          const fresh = await getFileById(fileId)
          anchors = fresh.data.tag_anchors ?? anchors
        } catch {
          /* 沿用列表中的 tag_anchors */
        }
        if (scrollToAnchorId.startsWith('fwl-')) {
          try {
            const wl = await getFileWikiLinks(fileId)
            wikiOutlinks = wl.data.outlinks
          } catch {
            /* 忽略 */
          }
        }
      }
      try {
        const res = adminMdApi ? await getAdminFileMd(fileId) : await getFileMd(fileId)
        if (cancelled) return
        const raw = String(res.data ?? '')
        if (effectiveReadOnly && !raw.trim()) {
          setLoadError(t('knowledgeIndex.mdPreviewEmpty'))
          setSource('')
          setPreviewHtml('')
          return
        }
        mdNoteRawRef.current = raw
        mdNoteAnchorsRef.current = anchors
        mdNoteWikiOutlinksRef.current = wikiOutlinks
        setSource(raw)
        setSavedSource(raw)
        setPreviewHtml(renderNotePreviewHtml(raw, anchors, wikiOutlinks, fileId))
      } catch (err: unknown) {
        if (cancelled) return
        const msg = formatApiError(err) || t('knowledgeIndex.mdPreviewLoadFailed')
        setLoadError(msg)
        setSource('')
        setPreviewHtml('')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [mdContentLoadKey, t])

  const handleSourceChange = useCallback((value: string) => {
    mdNoteRawRef.current = value
    setSource(value)
    setPreviewHtml(
      renderNotePreviewHtml(value, mdNoteAnchorsRef.current, mdNoteWikiOutlinksRef.current, file?.id),
    )
  }, [file?.id])

  const activateWikiLink = useCallback(
    (anchor: HTMLAnchorElement) => {
      const fileIdRaw = anchor.getAttribute('data-wiki-file-id')
      const slug = anchor.getAttribute('data-wiki-slug')
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
            else appMessage.warning(t('filePreview.wikiLinkBroken'))
          })
          .catch(() => appMessage.warning(t('filePreview.wikiLinkBroken')))
      }
    },
    [appMessage, t],
  )

  useEffect(() => {
    const root = previewRef.current
    if (!root || !previewHtml || loading) return
    return bindWikiLinkClick(root, activateWikiLink)
  }, [previewHtml, loading, activateWikiLink])

  useExtractAssetHydration(previewRef, {
    fileId: file?.id,
    contentKey: previewHtml,
    enabled: Boolean(open && previewHtml && !loading && file?.id),
  })

  useLayoutEffect(() => {
    if (!open || !scrollToAnchorId || loading || !previewHtml) return
    if (!file?.has_md) return
    let cancelled = false
    void (async () => {
      await waitPaintFrames(2)
      if (cancelled) return
      const root = previewRef.current
      if (!root) return
      const hint = anchorScrollHint(
        mdNoteAnchorsRef.current,
        mdNoteWikiOutlinksRef.current,
        scrollToAnchorId,
        mdNoteRawRef.current,
      )
      const ok = await scrollToAnchorWithRetry(root, scrollToAnchorId, hint)
      if (
        !cancelled &&
        !ok &&
        anchorBelongsToNote(scrollToAnchorId, mdNoteAnchorsRef.current, mdNoteWikiOutlinksRef.current)
      ) {
        appMessage.warning(t('filePreview.anchorMissing'))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, scrollToAnchorId, loading, previewHtml, file?.has_md, file?.id, appMessage, t])

  const openWikiOutlinkFromList = useCallback(
    (ol: WikiLinkOutItem) => {
      setListModalKind(null)
      onClose()
      void openWikiOutlinkTarget(ol, () => appMessage.warning(t('filePreview.wikiLinkBroken')))
    },
    [onClose, appMessage, t],
  )

  const uniqueOutlinks = useMemo(
    () => (wikiLinks ? uniqueOutlinkByTarget(wikiLinks.outlinks) : []),
    [wikiLinks],
  )
  const uniqueBacklinks = useMemo(
    () => (wikiLinks ? uniqueBacklinkBySource(wikiLinks.backlinks) : []),
    [wikiLinks],
  )

  const outlinkCountLabel =
    wikiLinks != null ? t('filePreview.outlinkCount', { count: uniqueOutlinks.length }) : null
  const backlinkCountLabel =
    wikiLinks != null ? t('filePreview.backlinkCount', { count: uniqueBacklinks.length }) : null

  async function saveMetadata() {
    if (!file || effectiveReadOnly || adminMdApi) return
    if (!metaDirty) {
      appMessage.info(t('okfNative.metadataUnchanged'))
      return
    }
    setMetaSaving(true)
    try {
      const res = await putFileOkfMeta(file.id, buildOkfMetaPutPayload(metaDraft))
      const data = res.data as {
        okf_concept_path?: string | null
        okf_type?: string | null
        okf_metadata?: Record<string, unknown> | null
        frontmatter?: Record<string, unknown>
      }
      const nextDraft = okfMetadataDraftFromApi(
        {
          okf_concept_path: data.okf_concept_path ?? null,
          okf_type: data.okf_type ?? null,
          frontmatter: data.frontmatter ?? {},
        },
        metaDraft.title,
      )
      setMetaDraft(nextDraft)
      setSavedMetaDraft(nextDraft)
      patchFileIndex(file.id, {
        okf_concept_path: data.okf_concept_path ?? undefined,
        okf_type: data.okf_type ?? undefined,
        okf_metadata: data.okf_metadata ?? undefined,
        tags: nextDraft.tags,
      })
      setLiveFile((prev) =>
        prev
          ? {
              ...prev,
              okf_concept_path: data.okf_concept_path ?? prev.okf_concept_path,
              okf_type: data.okf_type ?? prev.okf_type,
              okf_metadata: data.okf_metadata ?? prev.okf_metadata,
              tags: nextDraft.tags,
            }
          : null,
      )
      setOkfRaw('')
      appMessage.success(t('okfNative.metadataSaved'))
      onSaved?.()
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 409) {
        appMessage.error(t('okfNative.pathConflict'))
      } else {
        appMessage.error(formatApiError(err))
      }
    } finally {
      setMetaSaving(false)
    }
  }

  async function saveNote() {
    if (!file || effectiveReadOnly) return
    if (source === savedSource) {
      appMessage.info(t('mdEditor.unchanged'))
      onClose()
      return
    }
    setSaving(true)
    try {
      const res = await uploadFileMd(file.id, source)
      const data = res.data as { index_status?: string; unchanged?: boolean }
      if (data.unchanged) {
        appMessage.info(t('mdEditor.unchanged'))
        setSavedSource(source)
        onClose()
        return
      }
      const status = data.index_status ?? 'pending'
      patchFileIndex(file.id, { index_status: status, index_error: null, has_md: true })
      mdNoteRawRef.current = source
      setSavedSource(source)
      appMessage.success(t('messages.fileIngested'))
      try {
        const [freshFile, wl] = await Promise.all([getFileById(file.id), getFileWikiLinks(file.id)])
        const anchors = freshFile.data.tag_anchors ?? []
        const wikiOutlinks = wl.data.outlinks
        mdNoteAnchorsRef.current = anchors
        mdNoteWikiOutlinksRef.current = wikiOutlinks
        setWikiLinks(wl.data)
        setPreviewHtml(renderNotePreviewHtml(source, anchors, wikiOutlinks, file.id))
      } catch {
        /* 预览已随编辑更新，互链/锚点刷新失败可忽略 */
      }
      onSaved?.()
      onClose()
    } finally {
      setSaving(false)
    }
  }

  async function confirmDeleteMd() {
    if (!file) return
    setDeleting(true)
    try {
      await deleteFileMd(file.id)
      patchFileIndex(file.id, {
        has_md: false,
        md_has_content: false,
        extracted_at: null,
        extract_engine: null,
      })
      setLiveFile((prev) =>
        prev
          ? { ...prev, has_md: false, md_has_content: false, extracted_at: null, extract_engine: null }
          : null,
      )
      appMessage.success(t('messages.objectPurged'))
      setDeleteConfirmOpen(false)
      onSaved?.()
      onClose()
    } finally {
      setDeleting(false)
    }
  }

  if (!file || !displayFile) return null

  const titleText = resolveTitle(displayFile, t, effectiveReadOnly)
  const showWikiHeader = displayFile.has_md && wikiLinks != null
  const primarySaving = saving || metaSaving

  const footer = effectiveReadOnly ? (
    <div className="pv-note-modal-footer">
      <div className="pv-note-modal-footer-l">
        <div className="pv-note-modal-footer-meta">
          <ExtractEngineFooter file={displayFile} />
        </div>
      </div>
      <div className="pv-note-modal-footer-r">
        <Button onClick={onClose}>{t('common.close')}</Button>
      </div>
    </div>
  ) : (
    <div className="pv-note-modal-footer">
      <div className="pv-note-modal-footer-l">
        {displayFile.has_md ? (
          <div className="pv-note-modal-footer-delete">
            <Button
              danger
              icon={<DeleteActionIcon />}
              loading={deleting}
              onClick={() => setDeleteConfirmOpen(true)}
            >
              {t('fileList.deleteMd')}
            </Button>
          </div>
        ) : null}
        <div className="pv-note-modal-footer-meta">
          <ExtractEngineFooter file={displayFile} />
        </div>
      </div>
      <div className="pv-note-modal-footer-r">
        <Button onClick={onClose} disabled={primarySaving}>
          {t('common.cancel')}
        </Button>
        {activeTab === 'metadata' ? (
          <Button
            type="primary"
            loading={metaSaving}
            disabled={metaLoading || !metaDirty}
            onClick={() => void saveMetadata()}
          >
            {t('okfNative.saveMetadata')}
          </Button>
        ) : activeTab === 'body' ? (
          <Button
            type="primary"
            loading={saving}
            disabled={loading || !dirty}
            onClick={() => void saveNote()}
          >
            {file.has_md ? t('filePreview.saveNote') : t('common.confirm')}
          </Button>
        ) : (
          <Button type="primary" onClick={onClose}>
            {t('common.close')}
          </Button>
        )}
      </div>
    </div>
  )

  return (
    <>
      <Modal
        open={open}
        onCancel={onClose}
        title={
          <div className="pv-header-title">
            <span className="pv-header-title-name" title={file.original_name}>
              {titleText}
              {!file.has_md && !effectiveReadOnly ? ` · ${file.original_name}` : null}
            </span>
            {showWikiHeader ? (
              <div className="pv-header-links">
                {outlinkCountLabel != null ? (
                  <OutlinkHeaderTrigger
                    label={outlinkCountLabel}
                    count={uniqueOutlinks.length}
                    onOpenList={() => setListModalKind('outlinks')}
                  />
                ) : null}
                {backlinkCountLabel != null ? (
                  <BacklinkHeaderTrigger
                    label={backlinkCountLabel}
                    count={uniqueBacklinks.length}
                    onOpenList={() => setListModalKind('backlinks')}
                  />
                ) : null}
              </div>
            ) : null}
          </div>
        }
        width="80%"
        style={{ top: '3vh' }}
        footer={footer}
        destroyOnClose
        rootClassName="pv-root-modal pv-note-modal md-note-view-modal"
        styles={{ body: { overflow: 'hidden' } }}
        zIndex={zIndex}
      >
        {loadError ? (
          <Alert type="warning" showIcon message={loadError} />
        ) : showOkfTabs ? (
          <Tabs
            className="md-note-view-tabs"
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key as NoteEditorTab)}
            items={[
              {
                key: 'body',
                label: t('okfNative.tabBody'),
                children: (
                  <div className="md-note-tab-panel">
                    <MdSplitView
                      source={source}
                      previewHtml={previewHtml}
                      loading={loading}
                      emptyMessage={t('filePreview.mdEmpty')}
                      previewRef={previewRef}
                      className="pv-note-split"
                      fillHeight
                      editable={!effectiveReadOnly}
                      onSourceChange={effectiveReadOnly ? undefined : handleSourceChange}
                    />
                  </div>
                ),
              },
              {
                key: 'metadata',
                label: t('okfNative.tabMetadata'),
                children: (
                  <div className="md-note-tab-panel">
                    {metaLoadError ? (
                      <Alert type="warning" showIcon message={metaLoadError} />
                    ) : (
                      <div className="md-note-metadata-panel">
                        <Spin spinning={metaLoading}>
                          <OkfMetadataForm
                            draft={metaDraft}
                            onChange={setMetaDraft}
                            disabled={effectiveReadOnly}
                            showAdvancedToggle
                          />
                        </Spin>
                      </div>
                    )}
                  </div>
                ),
              },
              {
                key: 'raw',
                label: t('okfNative.tabRaw'),
                children: (
                  <div className="md-note-tab-panel md-note-okf-raw-panel">
                    {okfRawError ? (
                      <Alert type="warning" showIcon message={okfRawError} />
                    ) : (
                      <Spin spinning={okfRawLoading}>
                        <pre className="md-note-okf-raw" aria-readonly>
                          {okfRaw || (okfRawLoading ? '' : t('filePreview.mdEmpty'))}
                        </pre>
                        <p className="okf-metadata-collapse-hint">{t('okfNative.readOnlyHint')}</p>
                      </Spin>
                    )}
                  </div>
                ),
              },
            ]}
          />
        ) : (
          <div className="pv-body pv-note-body md-note-view-modal-body">
            <MdSplitView
              source={source}
              previewHtml={previewHtml}
              loading={loading}
              emptyMessage={t('filePreview.mdEmpty')}
              previewRef={previewRef}
              className="pv-note-split"
              fillHeight
              editable={!effectiveReadOnly}
              onSourceChange={effectiveReadOnly ? undefined : handleSourceChange}
            />
          </div>
        )}
      </Modal>

      {listModalKind && wikiLinks != null ? (
        <WikiLinksListModal
          open
          onClose={() => setListModalKind(null)}
          fileId={displayFile.id}
          fileName={displayFile.original_name}
          linkKind={listModalKind}
          initialData={wikiLinks}
          zIndex={zIndex + 100}
          onOpenOutlink={openWikiOutlinkFromList}
          onOpenFile={(targetFileId, meta) => {
            setListModalKind(null)
            onClose()
            dispatchWikiLinkNavigate({ fileId: targetFileId, anchorId: meta?.anchorId })
          }}
        />
      ) : null}

      {!effectiveReadOnly ? (
        <Modal
          title={t('fileList.confirmPurge')}
          open={deleteConfirmOpen}
          onOk={() => void confirmDeleteMd()}
          onCancel={() => setDeleteConfirmOpen(false)}
          okText={t('common.confirm')}
          cancelText={t('common.cancel')}
          okButtonProps={{ danger: true, loading: deleting }}
          cancelButtonProps={{ disabled: deleting }}
          confirmLoading={deleting}
          centered
          zIndex={zIndex + 100}
          destroyOnClose
          maskClosable={!deleting}
          closable={!deleting}
        >
          <p style={{ margin: 0 }}>{t('fileList.deleteMdConfirm', { name: file.original_name })}</p>
        </Modal>
      ) : null}
    </>
  )
}
