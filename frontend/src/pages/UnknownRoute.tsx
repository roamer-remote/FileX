import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Button, Result } from 'antd'

/** 已登录用户访问未注册 SPA 路径时的占位页（避免通配路由静默跳回首页）。 */
export default function UnknownRoutePage() {
  const { t } = useTranslation()
  const { pathname } = useLocation()

  return (
    <div className="unknown-route-page">
      <Result
        status="404"
        title={t('unknownRoute.title')}
        subTitle={t('unknownRoute.subtitle', { path: pathname })}
        extra={[
          <Link key="home" to="/">
            <Button type="primary">{t('unknownRoute.toFiles')}</Button>
          </Link>,
        ]}
      />
    </div>
  )
}
