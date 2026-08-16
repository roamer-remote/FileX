import { QuestionCircleFilled } from '@ant-design/icons'
import './FolderTreeIcon.css'

export type FolderTreeIconVariant = 'root' | 'child' | 'uncategorized'

type FolderTreeIconProps = {
  variant: FolderTreeIconVariant
  open?: boolean
  className?: string
}

/** 侧栏目录树：彩色文件夹图标，浅/深主题自适应；一级目录展开时显示打开态；未分类为红色问号 */
export default function FolderTreeIcon({ variant, open = false, className }: FolderTreeIconProps) {
  if (variant === 'uncategorized') {
    return (
      <QuestionCircleFilled
        className={['folder-tree-icon', 'folder-tree-icon--uncategorized', className].filter(Boolean).join(' ')}
        aria-hidden
      />
    )
  }

  const rootOpen = variant === 'root' && open
  const cls = [
    'folder-tree-icon',
    `folder-tree-icon--${variant}`,
    rootOpen ? 'folder-tree-icon--open' : 'folder-tree-icon--closed',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  if (rootOpen) {
    return (
      <svg className={cls} viewBox="0 0 16 16" width="16" height="16" aria-hidden focusable="false">
        <path className="folder-tree-icon-back" d="M1.5 4.25h5.1l1.15 1.35H14.5V12a1 1 0 0 1-1 1H2.5a1 1 0 0 1-1-1V4.25z" />
        <path className="folder-tree-icon-flap" d="M1.5 4.25h5.1l1.15 1.35H14.5L12.2 7.1H3.35L1.5 4.25z" />
        <path className="folder-tree-icon-front" d="M1.5 7.1h10.7L9.85 12.35H2.5a1 1 0 0 1-1-1V7.1z" />
      </svg>
    )
  }

  return (
    <svg className={cls} viewBox="0 0 16 16" width="16" height="16" aria-hidden focusable="false">
      <path className="folder-tree-icon-tab" d="M1.75 4.1h4.55l1.05 1.25h7.15a.85.85 0 0 1 .85.85v.55H1.75V4.1z" />
      <path className="folder-tree-icon-body" d="M1.75 5.95h12.85a1 1 0 0 1 1 1v5.1a1 1 0 0 1-1 1H2.75a1 1 0 0 1-1-1V5.95z" />
    </svg>
  )
}
