import { describe, expect, it } from 'vitest'
import {
  ADMIN_SETTINGS_TAB_GROUPS,
  ADMIN_SETTINGS_TABS,
  ADMIN_SETTINGS_TAB_BY_ID,
  DEFAULT_ADMIN_SETTINGS_TAB,
  adminSettingsTabsForGroup,
  resolveAdminSettingsTabFromHash,
  tabButtonId,
  tabPanelId,
} from './adminSettingsTabs'

describe('adminSettingsTabs', () => {
  it('defines 11 tabs with tabId, hash, group, and sectionId', () => {
    expect(ADMIN_SETTINGS_TABS).toHaveLength(11)
    for (const tab of ADMIN_SETTINGS_TABS) {
      expect(tab.tabId).toBeTruthy()
      expect(tab.hash).toBeTruthy()
      expect(tab.sectionId).toMatch(/^admin-settings-/)
      expect(['system', 'platform', 'kb']).toContain(tab.groupKey)
      expect(tab.labelKey).toMatch(/^admin\.settings\.sections\./)
      expect(tab.navTitleKey).toMatch(/^admin\.settings\.sections\./)
      expect(tab.descKey).toMatch(/^admin\.settings\.sections\./)
    }
  })

  it('defines three nav groups in display order', () => {
    expect(ADMIN_SETTINGS_TAB_GROUPS.map((g) => g.groupKey)).toEqual(['system', 'platform', 'kb'])
    expect(adminSettingsTabsForGroup('system')).toHaveLength(1)
    expect(adminSettingsTabsForGroup('platform')).toHaveLength(4)
    expect(adminSettingsTabsForGroup('kb')).toHaveLength(6)
  })

  it('maps tab ids to panel and button element ids via hash', () => {
    for (const tab of ADMIN_SETTINGS_TABS) {
      expect(tabPanelId(tab.hash)).toBe(`admin-settings-tabpanel-${tab.hash}`)
      expect(tabButtonId(tab.hash)).toBe(`admin-settings-tab-${tab.hash}`)
      expect(ADMIN_SETTINGS_TAB_BY_ID[tab.tabId]).toBe(tab)
    }
  })

  it('defaults to clipboard', () => {
    expect(DEFAULT_ADMIN_SETTINGS_TAB).toBe('clipboard')
  })

  describe('resolveAdminSettingsTabFromHash', () => {
    it('maps kebab hashes to tab ids', () => {
      expect(resolveAdminSettingsTabFromHash('#license')).toBe('license')
      expect(resolveAdminSettingsTabFromHash('#kb-pipeline')).toBe('kbPipeline')
      expect(resolveAdminSettingsTabFromHash('tag-graph')).toBe('tagGraph')
      expect(resolveAdminSettingsTabFromHash('#kb-search')).toBe('kbSearch')
    })

    it('returns default for empty or unknown hash', () => {
      expect(resolveAdminSettingsTabFromHash('')).toBe('clipboard')
      expect(resolveAdminSettingsTabFromHash('#')).toBe('clipboard')
      expect(resolveAdminSettingsTabFromHash('#not-a-tab')).toBe('clipboard')
    })

    it('covers all ADMIN_SETTINGS_TABS hash values', () => {
      for (const tab of ADMIN_SETTINGS_TABS) {
        expect(resolveAdminSettingsTabFromHash(`#${tab.hash}`)).toBe(tab.tabId)
      }
    })
  })
})
