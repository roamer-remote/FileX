import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Alert, App, Button, Spin, Tooltip } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { formatApiError } from '@/api/index'
import { getFileById, type FileItem } from '@/api/files'
import { getKnowledgeBaseIndex, rebuildKnowledgeBaseIndex } from '@/api/knowledgeBase'
import { getCachedUiState, patchKbIndexUiState } from '@/lib/uiStateSync'
import { LEGACY_KB_INDEX_REBUILD_TAB, resolveKbIndexTabs } from '@/lib/kbIndexUiState'
import type { KbIndexMainTab, KbIndexPreviewSubTab } from '@/lib/uiStateTypes'
import { markdownToSafeHtml } from '@/utils/markdownPreview'
import FilePreview from '@/components/FilePreview'
import KbIndexMdPreviewModal from '@/components/KbIndexMdPreviewModal'
import { useWikiLinkNavigation } from '@/hooks/useWikiLinkNavigation'
import KbIndexPreviewTable from '@/components/KbIndexPreviewTable'
import KbWikiIndexPreviewTable from '@/components/KbWikiIndexPreviewTable'
import { OKF_IMPORT_EXPORT_UI_ENABLED } from '@/lib/featureFlags'
import OkfImportExport from '@/components/OkfImportExport'
import WikiPagesTabPane from '@/components/WikiPagesTabPane'
import WikiLinkGraph, { type WikiLinkGraphHandle } from '@/components/WikiLinkGraph'
import KnowledgeTabLabel from '@/components/KnowledgeTabLabel'
import KnowledgeWorkspaceTabs from '@/components/knowledge/KnowledgeWorkspaceTabs'
import KnowledgePanelToolbarExtra from '@/components/knowledge/KnowledgePanelToolbarExtra'
import WorkspaceBackupButton from '@/components/knowledge/WorkspaceBackupButton'
import KnowledgePanelFilenameSearchBar from '@/components/knowledge/KnowledgePanelFilenameSearchBar'
import {
  extractKbIndexProse,
  hasKbWikiIndexSection,
  parseKbIndexRows,
  parseKbWikiIndexRows,
  filterKbIndexRows,
  filterKbWikiIndexDisplayRows,
} from '@/utils/parseKbIndexTable'
import '@/styles/knowledge-panel-shell.css'
import '@/styles/knowledge-workspace-layout.css'
import '@/components/FileList.css'
import './KnowledgeBaseIndex.css'

export default function KnowledgeBaseIndexPage() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const initialKbTabs = resolveKbIndexTabs(getCachedUiState()?.kb_index)
  const [loading, setLoading] = useState(true)
  const [text, setText] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [rebuilding, setRebuilding] = useState(false)
  const [activeTab, setActiveTab] = useState<KbIndexMainTab>(initialKbTabs.active_tab)
  const [previewSubTab, setPreviewSubTab] = useState<KbIndexPreviewSubTab>(initialKbTabs.preview_sub_tab)
  const [previewFile, setPreviewFile] = useState<FileItem | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [mdPreview, setMdPreview] = useState<{ fileId: number; fileName: string } | null>(null)
  const [autoPreviewSearch, setAutoPreviewSearch] = useState('')
  const wikiGraphRef = useRef<WikiLinkGraphHandle>(null)

  /** 全页总览嵌入：主题页操作条仅在大厅 Drawer 展示，此处丢弃注册 */
  const discardWikiPagesHeaderActions = useCallback(() => {}, [])

  const loadIndex = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true)
    try {
      const data = await getKnowledgeBaseIndex()
      setText(data)
      setLoadError(null)
    } catch (e: unknown) {
      setText(null)
      setLoadError(formatApiError(e) || t('knowledgeIndex.loadFailed'))
    } finally {
      if (!opts?.silent) setLoading(false)
    }
  }, [t])

  useEffect(() => {
    void loadIndex()
  }, [loadIndex])

  useEffect(() => {
    const rawTab = getCachedUiState()?.kb_index?.active_tab as string | undefined
    if (rawTab === LEGACY_KB_INDEX_REBUILD_TAB || (!OKF_IMPORT_EXPORT_UI_ENABLED && rawTab === 'okf')) {
      patchKbIndexUiState({ active_tab: 'preview' })
    }
  }, [])

  const handleMainTabChange = useCallback((key: string) => {
    const tab = resolveKbIndexTabs({ active_tab: key as KbIndexMainTab }).active_tab
    setActiveTab(tab)
    patchKbIndexUiState({ active_tab: tab })
  }, [])

  const handlePreviewSubTabChange = useCallback((key: string) => {
    const sub = resolveKbIndexTabs({ preview_sub_tab: key as KbIndexPreviewSubTab }).preview_sub_tab
    setPreviewSubTab(sub)
    patchKbIndexUiState({ preview_sub_tab: sub })
  }, [])

  const tableRows = useMemo(() => (text ? parseKbIndexRows(text) : []), [text])
  const filteredTableRows = useMemo(
    () => filterKbIndexRows(tableRows, autoPreviewSearch),
    [autoPreviewSearch, tableRows],
  )
  const wikiTableRowsRaw = useMemo(() => (text ? parseKbWikiIndexRows(text) : []), [text])
  const wikiTableRows = useMemo(() => filterKbWikiIndexDisplayRows(wikiTableRowsRaw), [wikiTableRowsRaw])
  const wikiSectionPresent = useMemo(() => (text ? hasKbWikiIndexSection(text) : false), [text])

  const proseHtml = useMemo(() => {
    if (!text) return ''
    const prose = extractKbIndexProse(text)
    if (!prose) return ''
    return markdownToSafeHtml(prose)
  }, [text])

  const openFilePreview = useCallback(
    (fileId: number, anchorId?: string) => {
      void getFileById(fileId)
        .then((res) => {
          setPreviewFile(res.data)
          setPreviewOpen(true)
          // Note: 当前索引页预览入口暂未透传 scrollToAnchorId 到 FilePreview（P0 重点在打开可达性）。
          // 若需带锚滚动，可在此扩展状态并传给 <FilePreview scrollToAnchorId={anchorId} ... />
          void anchorId
        })
        .catch(() => {
          message.error(t('kbSearch.fileOpenFailed'))
        })
    },
    [message, t],
  )

  useWikiLinkNavigation(openFilePreview)

  const handleWikiPagePreview = useCallback((file: FileItem) => {
    setPreviewFile(file)
    setPreviewOpen(true)
  }, [])

  const handleRebuild = useCallback(async () => {
    setRebuilding(true)
    try {
      const res = await rebuildKnowledgeBaseIndex()
      setText(res.content)
      setLoadError(null)
      if (res.recovered_from_corrupt) {
        message.success(t('knowledgeIndex.rebuildRecovered', { count: res.file_count }))
      } else {
        message.success(t('knowledgeIndex.rebuildSuccess', { count: res.file_count }))
      }
    } catch (e: unknown) {
      const detail = formatApiError(e)
      message.error(detail ? `${t('knowledgeIndex.rebuildFailed')}：${detail}` : t('knowledgeIndex.rebuildFailed'))
    } finally {
      setRebuilding(false)
    }
  }, [message, t])

  const rebuildToolbarButton = (
    <Tooltip title={t('knowledgeIndex.rebuildDesc')}>
      <Button
        type="default"
        size="small"
        icon={<ReloadOutlined className="kb-index-toolbar-icon kb-index-toolbar-icon--rebuild" aria-hidden />}
        loading={rebuilding}
        aria-label={t('knowledgeIndex.rebuildAction')}
        onClick={() => void handleRebuild()}
      />
    </Tooltip>
  )

  const nestedTabBarExtraRight = (
    <div className="knowledge-workspace-tabs-extra kb-index-tab-toolbar-extra">
      {previewSubTab === 'auto' ? (
        <KnowledgePanelToolbarExtra
          search={
            <KnowledgePanelFilenameSearchBar value={autoPreviewSearch} onChange={setAutoPreviewSearch} />
          }
        />
      ) : null}
      {rebuildToolbarButton}
      <WorkspaceBackupButton iconOnly />
    </div>
  )

  const nestedTabBarExtraContent = nestedTabBarExtraRight

  const autoPreviewPanel = (
    <div className="knowledge-workspace-pane knowledge-files-tab-pane knowledge-files-tab-pane--files">
      <KbIndexPreviewTable
        active={previewSubTab === 'auto'}
        rows={filteredTableRows}
        emptyDescription={
          autoPreviewSearch.trim() ? t('knowledgeIndex.searchNoResults') : undefined
        }
        onOpenFile={openFilePreview}
        onOpenMdPreview={(fileId, fileName) => setMdPreview({ fileId, fileName })}
      />
    </div>
  )

  const wikiPagesPreviewPanel = (
    <div className="knowledge-workspace-pane knowledge-files-tab-pane knowledge-files-tab-pane--wiki-pages">
      <WikiPagesTabPane
        active={previewSubTab === 'wikiPages'}
        onPreview={handleWikiPagePreview}
        onHeaderActionsChange={discardWikiPagesHeaderActions}
      />
    </div>
  )

  const wikiPreviewPanel = (
    <div className="knowledge-workspace-pane">
      {!wikiSectionPresent ? (
        <Alert type="warning" showIcon message={t('knowledgeIndex.wikiSectionMissing')} className="kb-index-wiki-alert" />
      ) : null}
      <KbWikiIndexPreviewTable
        active={previewSubTab === 'wiki'}
        rows={wikiTableRows}
        onOpenFile={openFilePreview}
      />
    </div>
  )

  const linkGraphPreviewPanel = (
    <div className="knowledge-workspace-pane knowledge-files-tab-pane knowledge-files-tab-pane--wiki kb-index-link-graph-pane">
      <WikiLinkGraph
        ref={wikiGraphRef}
        active={previewSubTab === 'linkGraph'}
        onPreview={(file) => openFilePreview(file.id)}
      />
    </div>
  )

  const previewPanel = (
    <div className="knowledge-panel-shell knowledge-workspace-pane kb-index-preview">
      {proseHtml ? (
        <div
          className="kb-index-prose fb-markdown-host markdown-body"
          dangerouslySetInnerHTML={{ __html: proseHtml }}
        />
      ) : null}
      <KnowledgeWorkspaceTabs
        nested
        activeKey={previewSubTab}
        onChange={handlePreviewSubTabChange}
        tabBarExtraContent={nestedTabBarExtraContent}
        items={[
          {
            key: 'auto',
            label: (
              <KnowledgeTabLabel tab="previewAuto">{t('knowledgeIndex.tabPreviewAuto')}</KnowledgeTabLabel>
            ),
            children: autoPreviewPanel,
          },
          {
            key: 'wikiPages',
            label: (
              <KnowledgeTabLabel tab="previewWikiPages">{t('knowledge.tabWikiPages')}</KnowledgeTabLabel>
            ),
            children: wikiPagesPreviewPanel,
          },
          {
            key: 'wiki',
            label: (
              <KnowledgeTabLabel tab="previewWiki">{t('knowledgeIndex.tabPreviewWiki')}</KnowledgeTabLabel>
            ),
            children: wikiPreviewPanel,
          },
          {
            key: 'linkGraph',
            label: (
              <KnowledgeTabLabel tab="previewLinkGraph">{t('knowledgeIndex.tabPreviewLinkGraph')}</KnowledgeTabLabel>
            ),
            children: linkGraphPreviewPanel,
          },
        ]}
      />
    </div>
  )

  const indexTabItems = OKF_IMPORT_EXPORT_UI_ENABLED
    ? [
        {
          key: 'preview' as const,
          label: (
            <span
              role="presentation"
              onMouseDown={(e) => e.stopPropagation()}
              onClick={(e) => e.stopPropagation()}
            >
              {rebuildToolbarButton}
            </span>
          ),
          children: previewPanel,
        },
        {
          key: 'okf' as const,
          label: <KnowledgeTabLabel tab="okf">{t('knowledgeIndex.tabOkf')}</KnowledgeTabLabel>,
          children: (
            <OkfImportExport
              onImportComplete={() => {
                void loadIndex({ silent: true })
              }}
            />
          ),
        },
      ]
    : []

  const pageBody =
    loadError && !loading ? (
      <div className="kb-index-empty">
        <Alert type="error" message={t('knowledgeIndex.loadFailed')} description={loadError} showIcon />
        <Button type="primary" icon={<ReloadOutlined aria-hidden />} loading={rebuilding} onClick={() => void handleRebuild()}>
          {t('knowledgeIndex.rebuildAction')}
        </Button>
      </div>
    ) : text === null && !loading ? (
      <div className="kb-index-empty">
        <Alert type="info" message={t('knowledgeIndex.emptyTitle')} description={t('knowledgeIndex.emptyDesc')} showIcon />
        <Button type="primary" icon={<ReloadOutlined aria-hidden />} loading={rebuilding} onClick={() => void handleRebuild()}>
          {t('knowledgeIndex.rebuildAction')}
        </Button>
      </div>
    ) : OKF_IMPORT_EXPORT_UI_ENABLED ? (
      <KnowledgeWorkspaceTabs
        activeKey={activeTab}
        onChange={handleMainTabChange}
        tabBarExtraContent={activeTab === 'okf' ? <WorkspaceBackupButton iconOnly /> : undefined}
        items={indexTabItems}
      />
    ) : (
      previewPanel
    )

  return (
    <div className="kb-index-page knowledge-workspace-page">
      {loading ? (
        <div className="kb-index-loading" style={{ textAlign: 'center', padding: '3rem' }}>
          <Spin />
        </div>
      ) : (
        pageBody
      )}

      <FilePreview
        open={previewOpen}
        file={previewFile}
        onClose={() => {
          setPreviewOpen(false)
          setPreviewFile(null)
        }}
      />

      <KbIndexMdPreviewModal
        open={mdPreview != null}
        fileId={mdPreview?.fileId ?? 0}
        fileName={mdPreview?.fileName ?? ''}
        onClose={() => setMdPreview(null)}
      />
    </div>
  )
}
