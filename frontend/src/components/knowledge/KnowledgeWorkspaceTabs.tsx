import { Tabs, type TabsProps } from 'antd'
import '@/styles/knowledge-workspace-layout.css'

type Props = Omit<TabsProps, 'type'> & {
  /** 内层子 Tab（如索引预览子视图） */
  nested?: boolean
}

/**
 * 资料库工作区统一 Tabs 壳：与大厅 Drawer 内容区同套 flex 高度链与 ink-bar 样式。
 * 用于 `/knowledge-base` 全页、后续可复用的资料库子工作区。
 */
export default function KnowledgeWorkspaceTabs({ nested = false, className, size, ...props }: Props) {
  return (
    <Tabs
      type="line"
      size={size ?? (nested ? 'small' : 'middle')}
      className={[
        'home-knowledge-tabs',
        'knowledge-workspace-tabs',
        nested ? 'knowledge-workspace-tabs--nested' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      {...props}
    />
  )
}
