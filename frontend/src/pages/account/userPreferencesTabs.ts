export const USER_PREFERENCES_TAB_GROUPS = [
  {
    groupKey: 'platform',
    labelKey: 'admin.settings.navGroups.platform',
  },
  {
    groupKey: 'kb',
    labelKey: 'admin.settings.navGroups.kb',
  },
] as const

export type UserPreferencesTabGroupKey = (typeof USER_PREFERENCES_TAB_GROUPS)[number]['groupKey']

export const USER_PREFERENCES_TABS = [
  {
    tabId: 'tagGraph',
    hash: 'tag-graph',
    sectionId: 'user-prefs-tag-graph',
    groupKey: 'platform',
    labelKey: 'admin.settings.sections.tagGraph.title',
    navTitleKey: 'admin.settings.sections.tagGraph.navTitle',
    descKey: 'account.preferences.sections.tagGraph.desc',
  },
  {
    tabId: 'kbPipeline',
    hash: 'kb-pipeline',
    sectionId: 'user-prefs-kb-pipeline',
    groupKey: 'kb',
    labelKey: 'admin.settings.sections.kbPipeline.title',
    navTitleKey: 'admin.settings.sections.kbPipeline.navTitle',
    descKey: 'account.preferences.sections.kbPipeline.desc',
  },
  {
    tabId: 'kbSearch',
    hash: 'kb-search',
    sectionId: 'user-prefs-kb-search',
    groupKey: 'kb',
    labelKey: 'admin.settings.sections.kbSearch.title',
    navTitleKey: 'admin.settings.sections.kbSearch.navTitle',
    descKey: 'account.preferences.sections.kbSearch.desc',
  },
  {
    tabId: 'wiki',
    hash: 'wiki',
    sectionId: 'user-prefs-wiki',
    groupKey: 'kb',
    labelKey: 'admin.settings.sections.wiki.title',
    navTitleKey: 'admin.settings.sections.wiki.navTitle',
    descKey: 'account.preferences.sections.wiki.desc',
  },
] as const

export type UserPreferencesTabDef = (typeof USER_PREFERENCES_TABS)[number]

export type UserPreferencesTabId = UserPreferencesTabDef['tabId']

export const DEFAULT_USER_PREFERENCES_TAB: UserPreferencesTabId = 'tagGraph'

export const USER_PREFERENCES_TAB_BY_ID = Object.fromEntries(
  USER_PREFERENCES_TABS.map((tab) => [tab.tabId, tab]),
) as Record<UserPreferencesTabId, UserPreferencesTabDef>

export function userPreferencesTabPanelId(hash: string): string {
  return `user-preferences-tabpanel-${hash}`
}

export function userPreferencesTabButtonId(hash: string): string {
  return `user-preferences-tab-${hash}`
}

export function userPreferencesTabsForGroup(groupKey: UserPreferencesTabGroupKey): UserPreferencesTabDef[] {
  return USER_PREFERENCES_TABS.filter((tab) => tab.groupKey === groupKey)
}

export function resolveUserPreferencesTabFromHash(hash: string): UserPreferencesTabId {
  const normalized = hash.replace(/^#/, '').trim()
  if (!normalized) return DEFAULT_USER_PREFERENCES_TAB
  const tab = USER_PREFERENCES_TABS.find((entry) => entry.hash === normalized)
  return tab?.tabId ?? DEFAULT_USER_PREFERENCES_TAB
}
