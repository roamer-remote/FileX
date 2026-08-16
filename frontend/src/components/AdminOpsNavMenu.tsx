import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Dropdown } from 'antd'
import { DownOutlined } from '@ant-design/icons'
import NavMenuLabel from './NavMenuLabel'
import './AdminEnterpriseDataNavMenu.css'

export const ADMIN_OPS_PATHS = [
  '/admin/users',
  '/admin/files',
  '/admin/logs',
  '/admin/settings',
  '/admin/agent-runs',
  '/admin/kb-search-eval',
  '/admin/knowledge-base/quality-workbench',
] as const

export default function AdminOpsNavMenu() {
  const { t } = useTranslation()
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const routeActive = ADMIN_OPS_PATHS.some(
    (path) => location.pathname === path || location.pathname.startsWith(`${path}/`),
  )

  const panel = (
    <div className="nav-submenu-panel" role="menu" aria-label={t('appLayout.adminOps')}>
      <NavLink
        to="/admin/users"
        className={({ isActive }) => 'nav-submenu-item' + (isActive ? ' active' : '')}
        role="menuitem"
        onClick={() => setOpen(false)}
      >
        <NavMenuLabel icon="userRegistry">{t('appLayout.userRegistry')}</NavMenuLabel>
      </NavLink>
      <NavLink
        to="/admin/files"
        className={({ isActive }) => 'nav-submenu-item' + (isActive ? ' active' : '')}
        role="menuitem"
        onClick={() => setOpen(false)}
      >
        <NavMenuLabel icon="allFiles">{t('appLayout.allFiles')}</NavMenuLabel>
      </NavLink>
      <NavLink
        to="/admin/logs"
        className={({ isActive }) => 'nav-submenu-item' + (isActive ? ' active' : '')}
        role="menuitem"
        onClick={() => setOpen(false)}
      >
        <NavMenuLabel icon="systemLogs">{t('appLayout.systemLogs')}</NavMenuLabel>
      </NavLink>
      <NavLink
        to="/admin/settings"
        className={({ isActive }) => 'nav-submenu-item' + (isActive ? ' active' : '')}
        role="menuitem"
        onClick={() => setOpen(false)}
      >
        <NavMenuLabel icon="systemSettings">{t('appLayout.systemSettings')}</NavMenuLabel>
      </NavLink>
      <NavLink
        to="/admin/agent-runs"
        className={({ isActive }) => 'nav-submenu-item' + (isActive ? ' active' : '')}
        role="menuitem"
        onClick={() => setOpen(false)}
      >
        <NavMenuLabel icon="agentRuns">{t('appLayout.agentRuns')}</NavMenuLabel>
      </NavLink>
      <NavLink
        to="/admin/kb-search-eval"
        className={({ isActive }) => 'nav-submenu-item' + (isActive ? ' active' : '')}
        role="menuitem"
        onClick={() => setOpen(false)}
      >
        <NavMenuLabel icon="kbSearchEval">{t('appLayout.kbSearchEval')}</NavMenuLabel>
      </NavLink>
      <NavLink
        to="/admin/knowledge-base/quality-workbench"
        className={({ isActive }) => 'nav-submenu-item' + (isActive ? ' active' : '')}
        role="menuitem"
        onClick={() => setOpen(false)}
      >
        <NavMenuLabel icon="qualityWorkbench">{t('appLayout.qualityWorkbench')}</NavMenuLabel>
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
        <NavMenuLabel icon="adminOps">{t('appLayout.adminOps')}</NavMenuLabel>
        <DownOutlined className="nav-submenu-chevron" aria-hidden />
      </button>
    </Dropdown>
  )
}
