import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Tabs } from 'antd'
import { useTranslation } from 'react-i18next'
import './AccountLayout.css'

const BASE = '/settings/account'

function tabKeyFromPath(pathname: string): string {
  if (pathname.includes('/password')) return 'password'
  return 'overview'
}

export default function AccountLayout() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const loc = useLocation()
  const activeKey = tabKeyFromPath(loc.pathname)

  return (
    <div className="account-layout">
      <header className="account-layout-header">
        <h1 className="account-layout-title">{t('account.title')}</h1>
      </header>
      <Tabs
        activeKey={activeKey}
        className="account-layout-tabs"
        onChange={(key) => {
          if (key === 'overview') navigate(`${BASE}/overview`)
          else navigate(`${BASE}/password`)
        }}
        items={[
          { key: 'overview', label: t('account.tabOverview') },
          { key: 'password', label: t('account.tabPassword') },
        ]}
      />
      <div className="account-layout-outlet">
        <Outlet />
      </div>
    </div>
  )
}
