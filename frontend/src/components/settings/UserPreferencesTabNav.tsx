import { useTranslation } from 'react-i18next'
import {
  USER_PREFERENCES_TAB_GROUPS,
  userPreferencesTabButtonId,
  userPreferencesTabPanelId,
  userPreferencesTabsForGroup,
  type UserPreferencesTabId,
} from '@/pages/account/userPreferencesTabs'

type UserPreferencesTabNavProps = {
  activeTabId: UserPreferencesTabId
  onTabChange: (tabId: UserPreferencesTabId) => void
}

export default function UserPreferencesTabNav({ activeTabId, onTabChange }: UserPreferencesTabNavProps) {
  const { t } = useTranslation()

  return (
    <nav
      className="admin-settings-side-nav"
      role="tablist"
      aria-label={t('account.preferences.title')}
    >
      {USER_PREFERENCES_TAB_GROUPS.map((group, groupIndex) => (
        <div key={group.groupKey} className="admin-settings-side-nav__group">
          <div
            className={`admin-settings-side-nav__group-label${groupIndex > 0 ? ' admin-settings-side-nav__group-label--spaced' : ''}`}
          >
            {t(group.labelKey)}
          </div>
          {userPreferencesTabsForGroup(group.groupKey).map((tab) => {
            const isActive = activeTabId === tab.tabId
            return (
              <button
                key={tab.tabId}
                type="button"
                role="tab"
                id={userPreferencesTabButtonId(tab.hash)}
                className={`admin-settings-side-nav__item${isActive ? ' is-active' : ''}`}
                aria-selected={isActive}
                aria-controls={userPreferencesTabPanelId(tab.hash)}
                onClick={() => onTabChange(tab.tabId)}
              >
                {t(tab.navTitleKey)}
              </button>
            )
          })}
        </div>
      ))}
    </nav>
  )
}
