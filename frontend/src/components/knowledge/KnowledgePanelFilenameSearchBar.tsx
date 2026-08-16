import KnowledgeFilenameSearch from '@/components/KnowledgeFilenameSearch'
import '@/components/knowledge/KnowledgeLobbyToolbar.css'
import '@/styles/knowledge-workspace-layout.css'

type ControlledProps = {
  value: string
  onChange: (value: string) => void
}

type Props = {
  className?: string
  placeholderKey?: string
} & Partial<ControlledProps>

/** 资料库工作区统一文件名搜索条（Drawer 顶栏 / Tab 工具区复用） */
export default function KnowledgePanelFilenameSearchBar({
  className,
  placeholderKey = 'fileList.searchPlaceholder',
  value,
  onChange,
}: Props) {
  const searchProps =
    value !== undefined && onChange !== undefined ? { value, onChange } : {}

  return (
    <div
      className={[
        'knowledge-panel-filename-search-bar',
        'knowledge-lobby-google-bar',
        'knowledge-lobby-google-bar--filename',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <KnowledgeFilenameSearch
        className="knowledge-lobby-toolbar__search knowledge-lobby-filename-search knowledge-panel-drawer-head__filename-search"
        variant="borderless"
        placeholderKey={placeholderKey}
        submitAriaLabelKey={placeholderKey}
        {...searchProps}
      />
    </div>
  )
}
