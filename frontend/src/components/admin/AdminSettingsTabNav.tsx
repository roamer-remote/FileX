import { useTranslation } from 'react-i18next'
import {
  ADMIN_SETTINGS_TAB_GROUPS,
  adminSettingsTabsForGroup,
  tabButtonId,
  tabPanelId,
  type AdminSettingsTabId,
} from '@/pages/admin/adminSettingsTabs'

type AdminSettingsTabNavProps = {
  activeTabId: AdminSettingsTabId
  onTabChange: (tabId: AdminSettingsTabId) => void
}

export default function AdminSettingsTabNav({ activeTabId, onTabChange }: AdminSettingsTabNavProps) {
  const { t } = useTranslation()

  return (
    <nav
      className="admin-settings-side-nav"
      role="tablist"
      aria-label={t('admin.settings.title')}
    >
      {ADMIN_SETTINGS_TAB_GROUPS.map((group, groupIndex) => (
        <div key={group.groupKey} className="admin-settings-side-nav__group">
          <div
            className={`admin-settings-side-nav__group-label${groupIndex > 0 ? ' admin-settings-side-nav__group-label--spaced' : ''}`}
          >
            {t(group.labelKey)}
          </div>
          {adminSettingsTabsForGroup(group.groupKey).map((tab) => {
            const isActive = activeTabId === tab.tabId
            return (
              <button
                key={tab.tabId}
                type="button"
                role="tab"
                id={tabButtonId(tab.hash)}
                className={`admin-settings-side-nav__item${isActive ? ' is-active' : ''}`}
                aria-selected={isActive}
                aria-controls={tabPanelId(tab.hash)}
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
