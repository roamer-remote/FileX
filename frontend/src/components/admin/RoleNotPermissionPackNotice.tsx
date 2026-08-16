import { Alert } from 'antd'
import type { CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'

type Props = {
  showDisabledHint?: boolean
  className?: string
  style?: CSSProperties
}

export default function RoleNotPermissionPackNotice({ showDisabledHint = false, className, style }: Props) {
  const { t } = useTranslation()
  return (
    <div className={className} style={style}>
      <Alert
        type="info"
        showIcon
        message={t('adminRbac.roleNotPermissionPackTitle')}
        description={
          <>
            <p style={{ marginBottom: showDisabledHint ? 8 : 0 }}>{t('adminRbac.roleNotPermissionPackBody')}</p>
            {showDisabledHint ? <p style={{ marginBottom: 0 }}>{t('adminRbac.roleDisabledHint')}</p> : null}
          </>
        }
      />
    </div>
  )
}
