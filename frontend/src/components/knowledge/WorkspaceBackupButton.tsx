import { useState } from 'react'
import { App, Button, Popover, Tooltip } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { formatApiError } from '@/api/index'
import { downloadWorkspaceBackup } from '@/api/workspaceBackup'
import { useAuthStore } from '@/stores/authStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'

type Props = {
  /** 仅显示彩色图标（用于资料库总览 Tab 工具栏） */
  iconOnly?: boolean
}

export default function WorkspaceBackupButton({ iconOnly = false }: Props) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const userId = useAuthStore((s) => s.user?.id)
  const username = useAuthStore((s) => s.user?.username)
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const workspaces = useWorkspaceStore((s) => s.workspaces)
  const activeWs = workspaces.find((w) => w.id === activeWorkspaceId)
  const [loading, setLoading] = useState(false)

  const isPersonalOwner =
    activeWs?.kind === 'personal' && userId != null && activeWs.owner_user_id === userId
  const isShared = activeWs?.kind === 'shared'

  if (!activeWs || (!isPersonalOwner && !isShared)) {
    return null
  }

  const handleDownload = async () => {
    if (activeWorkspaceId == null || !isPersonalOwner) return
    setLoading(true)
    try {
      const fallbackName = username?.trim()
        ? `${username}-backup.zip`
        : userId != null
          ? `user-${userId}-backup.zip`
          : 'workspace-backup.zip'
      await downloadWorkspaceBackup(activeWorkspaceId, fallbackName)
      message.success(t('workspaceBackup.success'))
    } catch (e: unknown) {
      const detail = formatApiError(e)
      message.error(detail || t('workspaceBackup.failed'))
    } finally {
      setLoading(false)
    }
  }

  const helpContent = (
    <div className="workspace-backup-help">
      <p>{t('workspaceBackup.disclaimer')}</p>
      <p>{t('workspaceBackup.noteFormat')}</p>
    </div>
  )

  const button = (
    <Button
      type="default"
      size="small"
      icon={
        <DownloadOutlined
          className={iconOnly ? 'kb-index-toolbar-icon kb-index-toolbar-icon--backup' : undefined}
          aria-hidden
        />
      }
      loading={loading}
      disabled={isShared}
      aria-label={iconOnly ? t('workspaceBackup.download') : undefined}
      onClick={() => void handleDownload()}
    >
      {iconOnly ? null : t('workspaceBackup.download')}
    </Button>
  )

  if (isShared) {
    return (
      <Tooltip title={t('workspaceBackup.errors.sharedNotSupported')}>
        <span className="workspace-backup-btn-wrap">{button}</span>
      </Tooltip>
    )
  }

  return (
    <Popover content={helpContent} trigger="hover" placement="bottomRight">
      {button}
    </Popover>
  )
}
