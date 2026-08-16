import type { ReactNode } from 'react'
import { Button, Tooltip } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import '@/styles/knowledge-workspace-layout.css'

type Props = {
  /** 搜索条左侧的操作按钮（如新建主题） */
  actions?: ReactNode
  /** 文件名搜索条等 */
  search?: ReactNode
  onRefresh?: () => void
  refreshLoading?: boolean
  refreshAriaLabel?: string
}

/** Tab 栏右侧工具区：操作 → 搜索 → 刷新（与 KnowledgePanelDrawer extra 对齐） */
export default function KnowledgePanelToolbarExtra({
  actions,
  search,
  onRefresh,
  refreshLoading = false,
  refreshAriaLabel,
}: Props) {
  const { t } = useTranslation()
  const refreshLabel = refreshAriaLabel ?? t('knowledge.refresh')

  return (
    <div className="knowledge-workspace-tabs-extra">
      {actions}
      {search}
      {onRefresh ? (
        <Tooltip title={refreshLabel}>
          <Button
            type="text"
            size="small"
            className="knowledge-workspace-tabs-refresh"
            icon={<ReloadOutlined aria-hidden />}
            aria-label={refreshLabel}
            loading={refreshLoading}
            onClick={onRefresh}
          />
        </Tooltip>
      ) : null}
    </div>
  )
}
