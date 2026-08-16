export const ADMIN_SETTINGS_TAB_GROUPS = [
  {
    groupKey: 'system',
    labelKey: 'admin.settings.navGroups.system',
  },
  {
    groupKey: 'platform',
    labelKey: 'admin.settings.navGroups.platform',
  },
  {
    groupKey: 'kb',
    labelKey: 'admin.settings.navGroups.kb',
  },
] as const

export type AdminSettingsTabGroupKey = (typeof ADMIN_SETTINGS_TAB_GROUPS)[number]['groupKey']

export const ADMIN_SETTINGS_TABS = [
  {
    tabId: 'license',
    hash: 'license',
    sectionId: 'admin-settings-license',
    groupKey: 'system',
    labelKey: 'admin.settings.sections.license.title',
    navTitleKey: 'admin.settings.sections.license.navTitle',
    descKey: 'admin.settings.sections.license.desc',
  },
  {
    tabId: 'clipboard',
    hash: 'clipboard',
    sectionId: 'admin-settings-clipboard',
    groupKey: 'platform',
    labelKey: 'admin.settings.sections.clipboard.title',
    navTitleKey: 'admin.settings.sections.clipboard.navTitle',
    descKey: 'admin.settings.sections.clipboard.desc',
  },
  {
    tabId: 'workspace',
    hash: 'workspace',
    sectionId: 'admin-settings-workspace',
    groupKey: 'platform',
    labelKey: 'admin.settings.sections.workspace.title',
    navTitleKey: 'admin.settings.sections.workspace.navTitle',
    descKey: 'admin.settings.sections.workspace.desc',
  },
  {
    tabId: 'tagGraph',
    hash: 'tag-graph',
    sectionId: 'admin-settings-tag-graph',
    groupKey: 'platform',
    labelKey: 'admin.settings.sections.tagGraph.title',
    navTitleKey: 'admin.settings.sections.tagGraph.navTitle',
    descKey: 'admin.settings.sections.tagGraph.desc',
  },
  {
    tabId: 'agentSkillInstall',
    hash: 'agent-skill-install',
    sectionId: 'admin-settings-agent-skill-install',
    groupKey: 'platform',
    labelKey: 'admin.settings.sections.agentSkillInstall.title',
    navTitleKey: 'admin.settings.sections.agentSkillInstall.navTitle',
    descKey: 'admin.settings.sections.agentSkillInstall.desc',
  },
  {
    tabId: 'kbPipeline',
    hash: 'kb-pipeline',
    sectionId: 'admin-settings-kb-pipeline',
    groupKey: 'kb',
    labelKey: 'admin.settings.sections.kbPipeline.title',
    navTitleKey: 'admin.settings.sections.kbPipeline.navTitle',
    descKey: 'admin.settings.sections.kbPipeline.desc',
  },
  {
    tabId: 'ollama',
    hash: 'ollama',
    sectionId: 'admin-settings-ollama',
    groupKey: 'kb',
    labelKey: 'admin.settings.sections.ollama.title',
    navTitleKey: 'admin.settings.sections.ollama.navTitle',
    descKey: 'admin.settings.sections.ollama.desc',
  },
  {
    tabId: 'kbSag',
    hash: 'kb-sag',
    sectionId: 'admin-settings-kb-sag',
    groupKey: 'kb',
    labelKey: 'admin.settings.sections.kbSag.title',
    navTitleKey: 'admin.settings.sections.kbSag.navTitle',
    descKey: 'admin.settings.sections.kbSag.desc',
  },
  {
    tabId: 'kbSearch',
    hash: 'kb-search',
    sectionId: 'admin-settings-kb-search',
    groupKey: 'kb',
    labelKey: 'admin.settings.sections.kbSearch.title',
    navTitleKey: 'admin.settings.sections.kbSearch.navTitle',
    descKey: 'admin.settings.sections.kbSearch.desc',
  },
  {
    tabId: 'wiki',
    hash: 'wiki',
    sectionId: 'admin-settings-wiki',
    groupKey: 'kb',
    labelKey: 'admin.settings.sections.wiki.title',
    navTitleKey: 'admin.settings.sections.wiki.navTitle',
    descKey: 'admin.settings.sections.wiki.desc',
  },
  {
    tabId: 'ragasEval',
    hash: 'ragas-eval',
    sectionId: 'admin-settings-ragas-eval',
    groupKey: 'kb',
    labelKey: 'admin.settings.sections.ragasEval.title',
    navTitleKey: 'admin.settings.sections.ragasEval.navTitle',
    descKey: 'admin.settings.sections.ragasEval.desc',
  },
] as const

export type AdminSettingsTabDef = (typeof ADMIN_SETTINGS_TABS)[number]

export type AdminSettingsTabId = AdminSettingsTabDef['tabId']

export const DEFAULT_ADMIN_SETTINGS_TAB: AdminSettingsTabId = 'clipboard'

export const ADMIN_SETTINGS_TAB_BY_ID = Object.fromEntries(
  ADMIN_SETTINGS_TABS.map((tab) => [tab.tabId, tab]),
) as Record<AdminSettingsTabId, AdminSettingsTabDef>

export function tabPanelId(hash: string): string {
  return `admin-settings-tabpanel-${hash}`
}

export function tabButtonId(hash: string): string {
  return `admin-settings-tab-${hash}`
}

/** Map URL hash (with or without `#`) to tab id; unknown/empty → default. */
export function resolveAdminSettingsTabFromHash(hash: string): AdminSettingsTabId {
  const normalized = hash.replace(/^#/, '').trim()
  if (!normalized) return DEFAULT_ADMIN_SETTINGS_TAB
  const tab = ADMIN_SETTINGS_TABS.find((entry) => entry.hash === normalized)
  return tab?.tabId ?? DEFAULT_ADMIN_SETTINGS_TAB
}

export function adminSettingsTabsForGroup(groupKey: AdminSettingsTabGroupKey): AdminSettingsTabDef[] {
  return ADMIN_SETTINGS_TABS.filter((tab) => tab.groupKey === groupKey)
}
