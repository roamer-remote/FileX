import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Dropdown } from 'antd'
import { DownOutlined } from '@ant-design/icons'
import NavMenuLabel from './NavMenuLabel'
import { useSystemSettingsStore } from '@/stores/systemSettingsStore'
import './AdminEnterpriseDataNavMenu.css'

const ENTERPRISE_DATA_PATHS = [
  '/admin/organization',
  '/admin/enterprise-roles',
  '/admin/workspaces',
] as const

export default function AdminEnterpriseDataNavMenu() {
  const { t } = useTranslation()
  const location = useLocation()
  const sharedWorkspacesEnabled = useSystemSettingsStore((s) => s.shared_workspaces_enabled ?? true)
  const [open, setOpen] = useState(false)
  const routeActive = ENTERPRISE_DATA_PATHS.some(
    (path) => location.pathname === path || location.pathname.startsWith(`${path}/`),
  )

  if (!sharedWorkspacesEnabled) {
    return null
  }

  const panel = (
    <div className="nav-submenu-panel" role="menu" aria-label={t('appLayout.enterpriseData')}>
      <NavLink
        to="/admin/organization"
        className={({ isActive }) => 'nav-submenu-item' + (isActive ? ' active' : '')}
        role="menuitem"
        onClick={() => setOpen(false)}
      >
        <NavMenuLabel icon="organization">{t('appLayout.enterpriseOrganization')}</NavMenuLabel>
      </NavLink>
      <NavLink
        to="/admin/enterprise-roles"
        className={({ isActive }) => 'nav-submenu-item' + (isActive ? ' active' : '')}
        role="menuitem"
        onClick={() => setOpen(false)}
      >
        <NavMenuLabel icon="enterpriseRoles">{t('appLayout.enterpriseRoles')}</NavMenuLabel>
      </NavLink>
      <NavLink
        to="/admin/workspaces"
        className={({ isActive }) => 'nav-submenu-item' + (isActive ? ' active' : '')}
        role="menuitem"
        onClick={() => setOpen(false)}
      >
        <NavMenuLabel icon="workspaces">{t('appLayout.enterpriseWorkspaces')}</NavMenuLabel>
      </NavLink>
    </div>
  )

  return (
    <Dropdown
      open={open}
      onOpenChange={setOpen}
      trigger={['click']}
      placement="bottomLeft"
      dropdownRender={() => panel}
    >
      <button
        type="button"
        className={'nav-link nav-link--with-icon nav-submenu-trigger' + (open || routeActive ? ' active' : '')}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <NavMenuLabel icon="enterpriseData">{t('appLayout.enterpriseData')}</NavMenuLabel>
        <DownOutlined className="nav-submenu-chevron" aria-hidden />
      </button>
    </Dropdown>
  )
}
