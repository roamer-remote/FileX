import type { KnowledgePageTabKey } from '@/contexts/KnowledgePageTabsContext'

export type LobbyHotspotKey = Exclude<KnowledgePageTabKey, 'eval'>

export const KNOWLEDGE_PANEL_KEYS: KnowledgePageTabKey[] = [
  'files',
  'wikiPages',
  'libraryMap',
  'wikiLinks',
  'tags',
  'eval',
]

/** 浅色大厅完整场景（WebP 优先，PNG 回退） */
export const LOBBY_BG_DESKTOP = '/design-mockups/lobby-light3d-bg-desktop.webp'
export const LOBBY_BG_DESKTOP_FALLBACK = '/design-mockups/lobby-light3d-bg-desktop.png'
/** 移动端横幅：地图墙横裁（WebP 优先） */
export const LOBBY_BG_MOBILE = '/design-mockups/lobby-light3d-bg-mobile.webp'
export const LOBBY_BG_MOBILE_FALLBACK = '/design-mockups/lobby-light3d-bg-mobile.png'
/** 深色主题大厅背景（暂由浅色资产降亮生成，待正式 dark 场景图替换） */
export const LOBBY_BG_DESKTOP_DARK = '/design-mockups/lobby-light3d-bg-desktop-dark.webp'
export const LOBBY_BG_MOBILE_DARK = '/design-mockups/lobby-light3d-bg-mobile-dark.webp'

export type KnowledgePanelLayout = {
  width: string
  fullscreen: boolean
  titleKey: string
  /** 可选：与 title 同行展示在 Drawer 顶栏（panel-subtitle） */
  subtitleKey?: string
}

export const KNOWLEDGE_PANEL_CONFIG: Record<KnowledgePageTabKey, KnowledgePanelLayout> = {
  files: { width: '100%', fullscreen: true, titleKey: 'knowledge.panelTitle.files' },
  wikiPages: { width: '100%', fullscreen: true, titleKey: 'knowledge.panelTitle.wikiPages' },
  wikiLinks: {
    width: '100%',
    fullscreen: true,
    titleKey: 'knowledge.panelTitle.wikiLinks',
    subtitleKey: 'wikiLinks.subtitle',
  },
  libraryMap: {
    width: '100%',
    fullscreen: true,
    titleKey: 'knowledge.panelTitle.libraryMap',
    subtitleKey: 'libraryMap.subtitle',
  },
  tags: { width: '100%', fullscreen: true, titleKey: 'knowledge.panelTitle.tags' },
  eval: { width: '100%', fullscreen: true, titleKey: 'knowledge.panelTitle.eval' },
}

export function parsePanelParam(value: string | null): KnowledgePageTabKey | null {
  if (!value) return null
  return KNOWLEDGE_PANEL_KEYS.includes(value as KnowledgePageTabKey)
    ? (value as KnowledgePageTabKey)
    : null
}

export function isPanelVisible(
  key: KnowledgePageTabKey,
  graphTabsVisible: boolean,
  tagGraphEnabled: boolean,
): boolean {
  if (!graphTabsVisible) {
    if (key === 'files' || key === 'eval') return true
    return false
  }
  if (key === 'tags' && !tagGraphEnabled) return false
  return true
}

/** 大厅 3D 场景热点（不含「检索评测」，该入口在顶栏搜索区） */
export const LOBBY_STAGE_HOTSPOT_KEYS: LobbyHotspotKey[] = KNOWLEDGE_PANEL_KEYS.filter(
  (key): key is LobbyHotspotKey => key !== 'eval',
)

export function getVisibleHotspots(
  graphTabsVisible: boolean,
  tagGraphEnabled: boolean,
): LobbyHotspotKey[] {
  return LOBBY_STAGE_HOTSPOT_KEYS.filter((key) =>
    isPanelVisible(key, graphTabsVisible, tagGraphEnabled),
  )
}
