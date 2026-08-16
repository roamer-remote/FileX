import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { FolderOutlined } from '@ant-design/icons'
import { useFoldersStore } from '@/stores/foldersStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import '@/components/FolderFloatingPanel.css'
import { folderSelectionLabel, virtualRootDisplayLabel } from '@/lib/folderTree'
import { anchorFromElement } from '@/lib/folderPanelMotion'

export default function FolderPanelTrigger() {
  const { t } = useTranslation()
  const triggerRef = useRef<HTMLButtonElement>(null)
  const selected = useFoldersStore((s) => s.selected)
  const folders = useFoldersStore((s) => s.folders)
  const workspaces = useWorkspaceStore((s) => s.workspaces)
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const activeWs = workspaces.find((w) => w.id === activeWorkspaceId)
  const virtualRootLabel = virtualRootDisplayLabel(activeWs, t)
  const panelOpen = useFoldersStore((s) => s.panelOpen)
  const panelMinimized = useFoldersStore((s) => s.panelMinimized)
  const panelMotion = useFoldersStore((s) => s.panelMotion)
  const togglePanelFromAnchor = useFoldersStore((s) => s.togglePanelFromAnchor)
  const panelActive = panelOpen || panelMinimized
  const panelLinked = panelMotion === 'enter' || panelMotion === 'exit'
  const label = folderSelectionLabel(selected, folders, t, virtualRootLabel)

  const anchorFromTrigger = () =>
    anchorFromElement(triggerRef.current) ??
    anchorFromElement(document.querySelector('.folder-panel-trigger'))

  return (
    <div className="folder-panel-trigger-wrap">
      <button
        ref={triggerRef}
        type="button"
        className={
          'folder-panel-trigger' +
          (panelActive ? ' folder-panel-trigger--active' : '') +
          (panelLinked ? ' folder-panel-trigger--linked' : '')
        }
        aria-expanded={panelActive}
        onClick={() => {
          const anchor = anchorFromTrigger()
          if (anchor) togglePanelFromAnchor(anchor)
        }}
        title={t('folders.openPanel')}
      >
        <FolderOutlined aria-hidden />
        <span className="folder-panel-trigger__label">{label}</span>
      </button>
    </div>
  )
}
