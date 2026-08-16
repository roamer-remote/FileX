import { forwardRef, type ReactNode } from 'react'
import FileList, { type FileListHandle } from '@/components/FileList'
import TagRelationCharts, { type TagRelationChartsHandle } from '@/components/TagRelationCharts'
import LibraryMapTab, { type LibraryMapTabHandle } from '@/components/LibraryMapTab'
import WikiLinkGraph, { type WikiLinkGraphHandle } from '@/components/WikiLinkGraph'
import WikiPagesTabPane, { type WikiPagesTabPaneHandle } from '@/components/WikiPagesTabPane'
import { useKnowledgePageTab } from '@/contexts/KnowledgePageTabsContext'
import type { FileItem } from '@/api/files'

type PreviewHandler = (file: FileItem, anchorId?: string, options?: { mdNote?: boolean }) => void

export const KnowledgeFilesTabPane = forwardRef<
  FileListHandle,
  { className: string; onPreview: PreviewHandler }
>(function KnowledgeFilesTabPane({ className, onPreview }, ref) {
  return (
    <div className={className}>
      <FileList ref={ref} onPreview={onPreview} />
    </div>
  )
})

export const KnowledgeWikiPagesTabPane = forwardRef<
  WikiPagesTabPaneHandle,
  {
    className: string
    onPreview: PreviewHandler
    onHeaderActionsChange?: (actions: ReactNode | null) => void
  }
>(function KnowledgeWikiPagesTabPane({ className, onPreview, onHeaderActionsChange }, ref) {
  const activeTab = useKnowledgePageTab()
  return (
    <div className={className}>
      <WikiPagesTabPane
        ref={ref}
        active={activeTab === 'wikiPages'}
        onPreview={onPreview}
        onHeaderActionsChange={onHeaderActionsChange}
      />
    </div>
  )
})

export const KnowledgeWikiTabPane = forwardRef<
  WikiLinkGraphHandle,
  { className: string; onPreview: PreviewHandler; onDrawerExtraChange?: (extra: ReactNode | null) => void }
>(function KnowledgeWikiTabPane({ className, onPreview, onDrawerExtraChange }, ref) {
  const activeTab = useKnowledgePageTab()
  return (
    <div className={className}>
      <WikiLinkGraph
        ref={ref}
        active={activeTab === 'wikiLinks'}
        onPreview={onPreview}
        onDrawerExtraChange={onDrawerExtraChange}
      />
    </div>
  )
})

export const KnowledgeTagsTabPane = forwardRef<
  TagRelationChartsHandle,
  {
    className: string
    onPreview: PreviewHandler
    onTagFilterSelect?: (tag: string, tag2?: string) => void
  }
>(function KnowledgeTagsTabPane({ className, onPreview, onTagFilterSelect }, ref) {
  const activeTab = useKnowledgePageTab()
  return (
    <div className={className}>
      <TagRelationCharts
        ref={ref}
        active={activeTab === 'tags'}
        onPreview={onPreview}
        onTagFilterSelect={onTagFilterSelect}
      />
    </div>
  )
})

export const KnowledgeLibraryMapTabPane = forwardRef<
  LibraryMapTabHandle,
  { className: string; onPreview: PreviewHandler; onDrawerExtraChange?: (extra: ReactNode | null) => void }
>(function KnowledgeLibraryMapTabPane({ className, onPreview, onDrawerExtraChange }, ref) {
  const activeTab = useKnowledgePageTab()
  return (
    <div className={className}>
      <LibraryMapTab
        ref={ref}
        active={activeTab === 'libraryMap'}
        onPreview={onPreview}
        onDrawerExtraChange={onDrawerExtraChange}
      />
    </div>
  )
})
