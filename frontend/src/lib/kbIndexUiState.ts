import type { KbIndexMainTab, KbIndexPreviewSubTab, KbIndexState } from '@/lib/uiStateTypes'
import { OKF_IMPORT_EXPORT_UI_ENABLED } from '@/lib/featureFlags'

const MAIN_TABS: KbIndexMainTab[] = OKF_IMPORT_EXPORT_UI_ENABLED
  ? ['preview', 'okf']
  : ['preview']
const PREVIEW_SUB_TABS: KbIndexPreviewSubTab[] = ['auto', 'wikiPages', 'wiki', 'linkGraph']

/** 093 前顶栏主 Tab；服务端 enum 仍可能返回此值，读时 normalize 为 preview。 */
export const LEGACY_KB_INDEX_REBUILD_TAB = 'rebuild' as const

function isMainTab(value: unknown): value is KbIndexMainTab {
  return typeof value === 'string' && (MAIN_TABS as string[]).includes(value)
}

function isPreviewSubTab(value: unknown): value is KbIndexPreviewSubTab {
  return typeof value === 'string' && (PREVIEW_SUB_TABS as string[]).includes(value)
}

export function resolveKbIndexTabs(raw?: Partial<KbIndexState> | null): KbIndexState {
  let activeTab: KbIndexMainTab = isMainTab(raw?.active_tab) ? raw.active_tab : 'preview'
  if (!OKF_IMPORT_EXPORT_UI_ENABLED && activeTab === 'okf') {
    activeTab = 'preview'
  }
  return {
    active_tab: activeTab,
    preview_sub_tab: isPreviewSubTab(raw?.preview_sub_tab) ? raw.preview_sub_tab : 'auto',
  }
}
