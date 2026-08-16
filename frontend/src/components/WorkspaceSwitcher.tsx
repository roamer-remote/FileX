import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Select, Spin } from 'antd'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { useFilesStore } from '@/stores/filesStore'
import { useFoldersStore } from '@/stores/foldersStore'
import { useSystemSettingsStore } from '@/stores/systemSettingsStore'
import { SidebarNavGroup, useSidebarNavAccordion } from './SidebarNav'
import './WorkspaceSwitcher.css'

export default function WorkspaceSwitcher() {
  const { t } = useTranslation()
  const sidebarNavAccordion = useSidebarNavAccordion()
  const workspaces = useWorkspaceStore((s) => s.workspaces)
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const loading = useWorkspaceStore((s) => s.loading)
  const fetchWorkspaces = useWorkspaceStore((s) => s.fetchWorkspaces)
  const setActiveWorkspace = useWorkspaceStore((s) => s.setActiveWorkspace)
  const switchWorkspace = useFoldersStore((s) => s.switchWorkspace)
  const loadFiles = useFilesStore((s) => s.loadFiles)
  const sharedEnabled = useSystemSettingsStore((s) => s.shared_workspaces_enabled ?? true)
  const settingsRevision = useSystemSettingsStore((s) => s.revision)
  const loadSettings = useSystemSettingsStore((s) => s.load)

  useEffect(() => {
    void loadSettings()
  }, [loadSettings])

  useEffect(() => {
    void fetchWorkspaces()
  }, [fetchWorkspaces, settingsRevision])

  useEffect(() => {
    const onSettingsChanged = () => {
      void loadSettings().then(() => fetchWorkspaces())
    }
    window.addEventListener('filex:system-settings-changed', onSettingsChanged)
    return () => window.removeEventListener('filex:system-settings-changed', onSettingsChanged)
  }, [loadSettings, fetchWorkspaces])

  const onChange = (id: number) => {
    if (id === activeWorkspaceId) return
    sidebarNavAccordion?.onItemClick('workspace')
    switchWorkspace(activeWorkspaceId, id)
    setActiveWorkspace(id)
    void loadFiles()
  }

  const visibleWorkspaces = sharedEnabled
    ? workspaces
    : workspaces.filter((w) => w.kind === 'personal')

  if (!sharedEnabled || visibleWorkspaces.length <= 1) {
    return null
  }

  if (loading && visibleWorkspaces.length === 0) {
    return <Spin size="small" className="workspace-switcher-spin" />
  }

  return (
    <SidebarNavGroup id="workspace" title={t('workspace.title')} defaultOpen>
      <Select
        className="workspace-switcher-select"
        value={activeWorkspaceId ?? undefined}
        onChange={onChange}
        onOpenChange={(open) => {
          if (open) sidebarNavAccordion?.onItemClick('workspace')
        }}
        options={visibleWorkspaces.map((w) => ({
          value: w.id,
          label: w.name,
        }))}
      />
    </SidebarNavGroup>
  )
}
