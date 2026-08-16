import { describe, expect, it } from 'vitest'
import {
  DEFAULT_USER_PREFERENCES_TAB,
  USER_PREFERENCES_TABS,
  USER_PREFERENCES_TAB_BY_ID,
  resolveUserPreferencesTabFromHash,
  userPreferencesTabsForGroup,
} from './userPreferencesTabs'

describe('userPreferencesTabs', () => {
  it('defines four tabs across platform and kb groups', () => {
    expect(USER_PREFERENCES_TABS).toHaveLength(4)
    expect(userPreferencesTabsForGroup('platform')).toHaveLength(1)
    expect(userPreferencesTabsForGroup('kb')).toHaveLength(3)
  })

  it('defaults to tagGraph', () => {
    expect(DEFAULT_USER_PREFERENCES_TAB).toBe('tagGraph')
    expect(resolveUserPreferencesTabFromHash('')).toBe('tagGraph')
    expect(resolveUserPreferencesTabFromHash('#kb-search')).toBe('kbSearch')
  })

  it('maps tab ids to definitions', () => {
    for (const tab of USER_PREFERENCES_TABS) {
      expect(USER_PREFERENCES_TAB_BY_ID[tab.tabId]).toBe(tab)
    }
  })
})
