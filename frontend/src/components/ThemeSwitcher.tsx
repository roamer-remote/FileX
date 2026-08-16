import { Dropdown } from 'antd'
import type { MenuProps } from 'antd'
import { DownOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { useThemeStore, type ThemePersistMode } from '@/stores/themeStore'
import './ThemeSwitcher.css'

const MODE_ICONS: Record<ThemePersistMode, string> = {
  light: '☀',
  dark: '☽',
  system: '◐',
}

const MODES: ThemePersistMode[] = ['light', 'dark', 'system']

export default function ThemeSwitcher() {
  const { t } = useTranslation()
  const mode = useThemeStore((s) => s.mode)
  const setMode = useThemeStore((s) => s.setMode)

  const items: MenuProps['items'] = MODES.map((m) => ({
    key: m,
    label: t(`theme.${m}`),
    icon: (
      <span className="theme-switcher-menu-icon" aria-hidden>
        {MODE_ICONS[m]}
      </span>
    ),
  }))

  return (
    <Dropdown
      menu={{
        items,
        selectable: true,
        selectedKeys: [mode],
        onClick: ({ key }) => setMode(key as ThemePersistMode),
      }}
      trigger={['click']}
      placement="bottomRight"
    >
      <button
        type="button"
        className="fx-btn theme-switcher-trigger"
        aria-label={t('theme.appearance')}
        aria-haspopup="menu"
      >
        <span className="theme-switcher-icon" aria-hidden>
          {MODE_ICONS[mode]}
        </span>
        <DownOutlined className="theme-switcher-caret" aria-hidden />
      </button>
    </Dropdown>
  )
}
