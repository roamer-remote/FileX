import { useState } from 'react'
import { App, Button, Form, Input } from 'antd'
import { useTranslation } from 'react-i18next'
import { activateLicense, type LicenseStatus } from '@/api/license'
import { formatApiError } from '@/api/index'
import './LicenseGate.css'

type Props = {
  status: LicenseStatus
  onActivated: () => void | Promise<void>
}

type FormValues = {
  license_key: string
  admin_username: string
  admin_password: string
}

function reasonLabel(reason: string | null, t: (k: string) => string): string {
  switch (reason) {
    case 'trial_expired':
      return t('license.reasonTrialExpired')
    case 'expired':
      return t('license.reasonExpired')
    case 'missing':
    case 'invalid_signature':
    case 'malformed':
      return t('license.reasonInvalid')
    default:
      return t('license.reasonExpired')
  }
}

export default function LicenseGate({ status, onActivated }: Props) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm<FormValues>()

  async function onFinish(values: FormValues) {
    setSubmitting(true)
    try {
      await activateLicense({
        license_key: values.license_key.trim(),
        admin_username: values.admin_username.trim(),
        admin_password: values.admin_password,
      })
      message.success(t('license.activateSuccess'))
      await onActivated()
    } catch (err) {
      message.error(formatApiError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="license-gate-overlay" role="dialog" aria-modal="true" aria-labelledby="license-gate-title">
      <div className="license-gate-card">
        <h1 id="license-gate-title">{t('license.title')}</h1>
        <div className="license-gate-meta">
          <p>{reasonLabel(status.reason, t)}</p>
          {status.expires_at ? (
            <p>
              {t('license.expiresAt')}: {new Date(status.expires_at).toLocaleString()}
            </p>
          ) : null}
          {status.customer_id ? (
            <p>
              {t('license.customer')}: {status.customer_id}
            </p>
          ) : null}
          {status.in_trial ? <p>{t('license.trialHint')}</p> : null}
        </div>
        <Form form={form} layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item
            name="license_key"
            label={t('license.keyLabel')}
            rules={[{ required: true, message: t('license.keyRequired') }]}
          >
            <Input.TextArea rows={3} placeholder={t('license.keyPlaceholder')} autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="admin_username"
            label={t('license.adminUser')}
            rules={[{ required: true, message: t('license.adminUserRequired') }]}
          >
            <Input autoComplete="username" />
          </Form.Item>
          <Form.Item
            name="admin_password"
            label={t('license.adminPassword')}
            rules={[{ required: true, message: t('license.adminPasswordRequired') }]}
          >
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={submitting} block>
              {t('license.activate')}
            </Button>
          </Form.Item>
        </Form>
      </div>
    </div>
  )
}
