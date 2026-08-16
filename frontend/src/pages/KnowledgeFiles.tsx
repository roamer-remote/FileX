import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import FilePreview from '@/components/FilePreview'
import KbRetrievalEval from '@/components/KbRetrievalEval'
import {
  KnowledgeFilesTabPane,
  KnowledgeTagsTabPane,
  KnowledgeWikiPagesTabPane,
  KnowledgeWikiTabPane,
  KnowledgeLibraryMapTabPane,
} from '@/components/knowledge/KnowledgeTabPanes'
import LibraryLobby from '@/components/knowledge/LibraryLobby'
import KnowledgeLobbyToolbar from '@/components/knowledge/KnowledgeLobbyToolbar'
import KnowledgePanelDrawer from '@/components/knowledge/KnowledgePanelDrawer'
import KnowledgePanelFilenameSearchBar from '@/components/knowledge/KnowledgePanelFilenameSearchBar'
import { getFileById, type FileItem } from '@/api/files'
import { FOLDER_NAV_TO_FILE_LIST } from '@/lib/wikiLinkEvents'
import { useWikiLinkNavigation } from '@/hooks/useWikiLinkNavigation'
import { KnowledgePageTabsProvider, type KnowledgePageTabKey } from '@/contexts/KnowledgePageTabsContext'
import { showKnowledgeGraphTabs } from '@/lib/folderTree'
import {
  isPanelVisible,
  parsePanelParam,
} from '@/lib/knowledgePanelConfig'
import {
  KB_EVAL_TRIAL_CLIP_PARAM,
  parseKbEvalDeepLink,
} from '@/lib/kbEvalLobbyLink'
import { useFoldersStore } from '@/stores/foldersStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useFilesStore } from '@/stores/filesStore'
import type { FileListHandle } from '@/components/FileList'
import type { TagRelationChartsHandle } from '@/components/TagRelationCharts'
import type { LibraryMapTabHandle } from '@/components/LibraryMapTab'
import type { WikiLinkGraphHandle } from '@/components/WikiLinkGraph'
import type { WikiPagesTabPaneHandle } from '@/components/WikiPagesTabPane'
import { useSystemSettingsStore } from '@/stores/systemSettingsStore'
import {
  clearActiveKbPanelTransition,
  pickKbPanelTransition,
  type KbPanelTransitionId,
} from '@/lib/knowledgePanelTransition'
import { APP_BUILD_VERSION } from '@/lib/buildVersion'
import './KnowledgeFiles.css'

export default function KnowledgeFilesPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const [previewFile, setPreviewFile] = useState<FileItem | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewAnchorId, setPreviewAnchorId] = useState<string | undefined>(undefined)
  const [previewMdNote, setPreviewMdNote] = useState(false)
  // 从 URL 同步初始化，确保 `/?panel=files` 首次渲染就是资料页，不先闪现大厅。
  const [activePanel, setActivePanel] = useState<KnowledgePageTabKey | null>(() =>
    parsePanelParam(searchParams.get('panel')),
  )
  const [panelTransition, setPanelTransition] = useState<KbPanelTransitionId | null>(null)
  const [evalSeedQuery, setEvalSeedQuery] = useState('')
  const [evalSeedRunNonce, setEvalSeedRunNonce] = useState(0)
  const [wikiPagesDrawerActions, setWikiPagesDrawerActions] = useState<ReactNode | null>(null)
  const [libraryMapDrawerExtra, setLibraryMapDrawerExtra] = useState<ReactNode | null>(null)
  const [wikiLinksDrawerExtra, setWikiLinksDrawerExtra] = useState<ReactNode | null>(null)
  const fileListRef = useRef<FileListHandle>(null)
  const wikiPagesRef = useRef<WikiPagesTabPaneHandle>(null)
  const tagChartsRef = useRef<TagRelationChartsHandle>(null)
  const libraryMapRef = useRef<LibraryMapTabHandle>(null)
  const wikiGraphRef = useRef<WikiLinkGraphHandle>(null)
  const previewParam = searchParams.get('preview')
  const previewNoteParam = searchParams.get('note')
  const setTagFilters = useFilesStore((s) => s.setTagFilters)
  const loadFiles = useFilesStore((s) => s.loadFiles)
  const files = useFilesStore((s) => s.files)
  const folderSelection = useFoldersStore((s) => s.selected)
  const folderList = useFoldersStore((s) => s.folders)
  const zeroAclMember = useFoldersStore((s) => s.zeroAclMember)
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const workspaces = useWorkspaceStore((s) => s.workspaces)
  const graphTabsVisible = showKnowledgeGraphTabs(folderSelection)
  const tagGraphEnabled = useSystemSettingsStore((s) => s.tag_graph_enabled ?? true)

  const activeWs = workspaces.find((w) => w.id === activeWorkspaceId)
  const showZeroAclEmpty = zeroAclMember && activeWs?.kind === 'shared'
  const showEmptyGuide = !showZeroAclEmpty && files.length === 0 && folderList.length === 0

  useEffect(() => {
    void loadFiles()
  }, [loadFiles])

  const refreshTabPane = useCallback((key: string) => {
    window.requestAnimationFrame(() => {
      if (key === 'files') {
        fileListRef.current?.refresh()
      } else if (key === 'wikiPages') {
        wikiPagesRef.current?.refresh()
      } else if (key === 'tags') {
        tagChartsRef.current?.refresh()
      } else if (key === 'libraryMap') {
        libraryMapRef.current?.refresh()
      } else if (key === 'wikiLinks') {
        wikiGraphRef.current?.refresh()
      }
      // eval：由 KbRetrievalEval + seedRunNonce 驱动，Drawer 刷新按钮无需 reload 文件列表
    })
  }, [])

  const openPanel = useCallback(
    (key: KnowledgePageTabKey) => {
      if (!isPanelVisible(key, true, tagGraphEnabled)) return
      setPanelTransition(pickKbPanelTransition())
      setActivePanel(key)
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set('panel', key)
          return next
        },
        { replace: false },
      )
      if (key !== 'libraryMap') refreshTabPane(key)
    },
    [tagGraphEnabled, refreshTabPane, setSearchParams],
  )

  const closePanel = useCallback(() => {
    setEvalSeedQuery('')
    setActivePanel(null)
    setPanelTransition(null)
    clearActiveKbPanelTransition()
    // replace: true — 关闭 Drawer 不新增历史条目，避免「返回」需多点一次
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.delete('panel')
        return next
      },
      { replace: true },
    )
  }, [setSearchParams])

  const focusFilesPanel = useCallback(() => {
    openPanel('files')
  }, [openPanel])

  const prevGraphTabsVisibleRef = useRef(graphTabsVisible)

  useEffect(() => {
    const parsed = parsePanelParam(searchParams.get('panel'))
    if (!parsed) {
      setActivePanel(null)
      setPanelTransition(null)
      clearActiveKbPanelTransition()
      return
    }
    if (isPanelVisible(parsed, true, tagGraphEnabled)) {
      setActivePanel((prev) => {
        if (prev !== parsed) {
          setPanelTransition(pickKbPanelTransition())
        }
        return parsed
      })
      return
    }
    setActivePanel(null)
    setPanelTransition(null)
    clearActiveKbPanelTransition()
    setSearchParams(
      (prev) => {
        if (!prev.get('panel')) return prev
        const next = new URLSearchParams(prev)
        next.delete('panel')
        return next
      },
      { replace: true },
    )
  }, [searchParams, tagGraphEnabled, setSearchParams])

  useEffect(() => {
    const prev = prevGraphTabsVisibleRef.current
    prevGraphTabsVisibleRef.current = graphTabsVisible
    if (!prev || graphTabsVisible) return
    const parsed = parsePanelParam(searchParams.get('panel'))
    if (!parsed || parsed === 'files' || parsed === 'eval') return
    closePanel()
  }, [graphTabsVisible, searchParams, closePanel])


  useEffect(() => {
    const panel = parsePanelParam(searchParams.get('panel'))
    if (panel !== 'eval') return

    const { prefillQuery, workspaceId, trialClip } = parseKbEvalDeepLink(searchParams)

    if (workspaceId != null) {
      const ws = useWorkspaceStore.getState()
      const prev = ws.activeWorkspaceId
      if (prev !== workspaceId) {
        ws.setActiveWorkspace(workspaceId)
        useFoldersStore.getState().switchWorkspace(prev, workspaceId)
      }
    }

    if (prefillQuery) {
      setEvalSeedQuery(prefillQuery)
      setEvalSeedRunNonce((n) => n + 1)
      return
    }

    if (!trialClip) return

    let cancelled = false
    void (async () => {
      try {
        const clipText = await navigator.clipboard.readText()
        if (cancelled) return
        const q = clipText.trim()
        if (q) {
          setEvalSeedQuery(q)
          setEvalSeedRunNonce((n) => n + 1)
        }
      } catch {
        /* 无剪贴板权限时仅打开 eval Drawer */
      } finally {
        if (!cancelled) {
          setSearchParams(
            (prev) => {
              if (prev.get(KB_EVAL_TRIAL_CLIP_PARAM) !== '1') return prev
              const next = new URLSearchParams(prev)
              next.delete(KB_EVAL_TRIAL_CLIP_PARAM)
              return next
            },
            { replace: true },
          )
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [searchParams, setSearchParams])

  useEffect(() => {
    const onFolderNav = () => focusFilesPanel()
    window.addEventListener(FOLDER_NAV_TO_FILE_LIST, onFolderNav)
    return () => window.removeEventListener(FOLDER_NAV_TO_FILE_LIST, onFolderNav)
  }, [focusFilesPanel])

  useEffect(() => {
    if (!previewParam) return
    const id = Number(previewParam)
    if (!Number.isFinite(id) || id <= 0) return
    setPreviewMdNote(previewNoteParam === '1')
    let cancelled = false
    void getFileById(id)
      .then((res) => {
        if (cancelled) return
        setPreviewFile(res.data)
        setPreviewOpen(true)
      })
      .catch(() => {
        if (cancelled) return
        setPreviewFile(null)
        setPreviewOpen(false)
        setPreviewMdNote(false)
      })
    return () => {
      cancelled = true
    }
  }, [previewParam, previewNoteParam])

  const onPreviewFile = useCallback(
    (f: FileItem, anchorId?: string, options?: { mdNote?: boolean }) => {
      setPreviewFile(f)
      setPreviewAnchorId(anchorId)
      setPreviewMdNote(Boolean(options?.mdNote))
      setPreviewOpen(true)
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set('preview', String(f.id))
          if (options?.mdNote) {
            next.set('note', '1')
          } else {
            next.delete('note')
          }
          return next
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  useWikiLinkNavigation((fileId, anchorId) => {
    void getFileById(fileId)
      .then((res) => onPreviewFile(res.data, anchorId))
      .catch(() => undefined)
  })

  const closePreview = useCallback(() => {
    setPreviewOpen(false)
    setPreviewAnchorId(undefined)
    setPreviewMdNote(false)
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.delete('preview')
        next.delete('note')
        return next
      },
      { replace: true },
    )
  }, [setSearchParams])

  const onTagFilterSelect = useCallback(
    (tag: string, tag2?: string) => {
      setTagFilters(tag, tag2)
      openPanel('files')
    },
    [setTagFilters, openPanel],
  )

  const handleLobbyEvalOpen = useCallback(
    (query: string) => {
      setEvalSeedQuery(query)
      setEvalSeedRunNonce((n) => n + 1)
      openPanel('eval')
    },
    [openPanel],
  )

  const handleRefreshActive = useCallback(() => {
    if (activePanel) refreshTabPane(activePanel)
  }, [activePanel, refreshTabPane])

  const filesDrawerSearch = useMemo(
    () => <KnowledgePanelFilenameSearchBar className="knowledge-panel-drawer-head__filename-bar" />,
    [],
  )

  const panelContent = useMemo(() => {
    if (!activePanel) return null
    switch (activePanel) {
      case 'files':
        return (
          <KnowledgeFilesTabPane
            ref={fileListRef}
            className="knowledge-files-tab-pane knowledge-files-tab-pane--files"
            onPreview={onPreviewFile}
          />
        )
      case 'wikiPages':
        return (
          <KnowledgeWikiPagesTabPane
            ref={wikiPagesRef}
            className="knowledge-files-tab-pane knowledge-files-tab-pane--wiki-pages"
            onPreview={onPreviewFile}
            onHeaderActionsChange={setWikiPagesDrawerActions}
          />
        )
      case 'wikiLinks':
        return (
          <KnowledgeWikiTabPane
            ref={wikiGraphRef}
            className="knowledge-files-tab-pane knowledge-files-tab-pane--wiki"
            onPreview={onPreviewFile}
            onDrawerExtraChange={setWikiLinksDrawerExtra}
          />
        )
      case 'libraryMap':
        return (
          <KnowledgeLibraryMapTabPane
            ref={libraryMapRef}
            className="knowledge-files-tab-pane knowledge-files-tab-pane--library"
            onPreview={onPreviewFile}
            onDrawerExtraChange={setLibraryMapDrawerExtra}
          />
        )
      case 'tags':
        return (
          <KnowledgeTagsTabPane
            ref={tagChartsRef}
            className="knowledge-files-tab-pane knowledge-files-tab-pane--tags"
            onPreview={onPreviewFile}
            onTagFilterSelect={onTagFilterSelect}
          />
        )
      case 'eval':
        return (
          <div className="knowledge-files-tab-pane knowledge-files-tab-pane--eval">
            <KbRetrievalEval
              files={files}
              onPreview={onPreviewFile}
              seedQuery={evalSeedQuery}
              seedRunNonce={evalSeedRunNonce || undefined}
              onRefresh={handleRefreshActive}
            />
          </div>
        )
      default:
        return null
    }
  }, [activePanel, evalSeedQuery, evalSeedRunNonce, files, handleRefreshActive, onPreviewFile, onTagFilterSelect])

  return (
    <div className="knowledge-files-page knowledge-files-page--lobby">
      <div className="knowledge-lobby-stage-wrap">
        <KnowledgeLobbyToolbar onOpenEval={handleLobbyEvalOpen} />
        {activePanel === null ? (
          <LibraryLobby showEmptyGuide={showEmptyGuide} zeroAclEmpty={showZeroAclEmpty} />
        ) : null}

            <KnowledgePageTabsProvider activeTab={activePanel}>
              <KnowledgePanelDrawer
                open={activePanel !== null}
                panelKey={activePanel}
                transitionId={panelTransition}
                onClose={closePanel}
                onRefresh={handleRefreshActive}
                headerAfterTitle={activePanel === 'files' ? filesDrawerSearch : undefined}
                headerActions={activePanel === 'wikiPages' ? wikiPagesDrawerActions : undefined}
                headerToolbarSlot={activePanel === 'eval'}
                panelExtra={
                  activePanel === 'libraryMap'
                    ? libraryMapDrawerExtra
                    : activePanel === 'wikiLinks'
                      ? wikiLinksDrawerExtra
                      : undefined
                }
              >
                {panelContent}
              </KnowledgePanelDrawer>
            </KnowledgePageTabsProvider>

        {APP_BUILD_VERSION ? (
          <span
            className="knowledge-lobby-build-version"
            title={APP_BUILD_VERSION}
            aria-label={t('knowledge.buildVersionAria', { version: APP_BUILD_VERSION })}
          >
            {APP_BUILD_VERSION}
          </span>
        ) : null}
      </div>

      <FilePreview
        open={previewOpen}
        file={previewFile}
        scrollToAnchorId={previewAnchorId}
        openMdNote={previewMdNote}
        onClose={closePreview}
      />

    </div>
  )
}
