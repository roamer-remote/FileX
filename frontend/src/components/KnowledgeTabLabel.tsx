import type { ReactNode } from 'react'
import {
  ApartmentOutlined,
  BookOutlined,
  ClusterOutlined,
  EyeOutlined,
  FileTextOutlined,
  GlobalOutlined,
  LineChartOutlined,
  ShareAltOutlined,
  SnippetsOutlined,
  SwapOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons'
import './KnowledgeTabLabel.css'

export type KnowledgeTabKey =
  | 'files'
  | 'wikiPages'
  | 'tags'
  | 'wikiLinks'
  | 'libraryMap'
  | 'eval'
  | 'preview'
  | 'previewAuto'
  | 'previewWikiPages'
  | 'previewWiki'
  | 'previewLinkGraph'
  | 'log'
  | 'okf'

const TAB_ICONS = {
  files: FileTextOutlined,
  wikiPages: BookOutlined,
  tags: ApartmentOutlined,
  wikiLinks: ShareAltOutlined,
  libraryMap: GlobalOutlined,
  eval: LineChartOutlined,
  preview: EyeOutlined,
  previewAuto: SnippetsOutlined,
  previewWikiPages: BookOutlined,
  previewWiki: ShareAltOutlined,
  previewLinkGraph: ClusterOutlined,
  log: UnorderedListOutlined,
  okf: SwapOutlined,
} as const

type Props = {
  tab: KnowledgeTabKey
  children: ReactNode
}

export default function KnowledgeTabLabel({ tab, children }: Props) {
  const Icon = TAB_ICONS[tab]
  return (
    <span className={`knowledge-tab-label knowledge-tab-label--${tab}`}>
      <Icon className="knowledge-tab-label__icon" aria-hidden />
      <span className="knowledge-tab-label__text">{children}</span>
    </span>
  )
}
