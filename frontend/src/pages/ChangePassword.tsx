import { useTranslation } from 'react-i18next'
import { SafetyCertificateOutlined } from '@ant-design/icons'
import ChangePasswordForm from '@/components/ChangePasswordForm'
import './ChangePassword.css'

export default function ChangePasswordPage() {
  const { t } = useTranslation()

  return (
    <div className="cp-root">
      <header className="cp-header">
        <div className="ah-title-group">
          <h2 className="cp-title ah-title">
            <span className="cp-title-icon" aria-hidden>
              <SafetyCertificateOutlined />
            </span>
            {t('changePassword.title')}
          </h2>
          <span className="cp-sub ah-sub">{t('changePassword.subtitle')}</span>
        </div>
      </header>
      <ChangePasswordForm />
    </div>
  )
}
