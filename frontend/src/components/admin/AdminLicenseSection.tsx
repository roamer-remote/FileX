import { useCallback, useEffect, useState } from 'react'
import { App, Button, Col, Descriptions, Form, Input, Row, Spin } from 'antd'
import { useTranslation } from 'react-i18next'
import { formatApiError } from '@/api/index'
import { getAdminLicense, putAdminLicense, type LicenseAdminStatus } from '@/api/license'

type FormValues = { license_key: string }

type AdminLicenseSectionProps = {
  /** Tab 内由 SettingsSection 承担标题，仅渲染表单与状态区 */
  embedded?: boolean
}

export default function AdminLicenseSection({ embedded = false }: AdminLicenseSectionProps) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [status, setStatus] = useState<LicenseAdminStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm<FormValues>()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getAdminLicense()
      setStatus(res.data)
    } catch (err) {
      message.error(formatApiError(err))
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    void load()
  }, [load])

  async function onFinish(values: FormValues) {
    setSubmitting(true)
    try {
      const res = await putAdminLicense(values.license_key.trim())
      setStatus(res.data)
      form.resetFields()
      message.success(t('license.adminSaveSuccess'))
    } catch (err) {
      message.error(formatApiError(err))
    } finally {
      setSubmitting(false)
    }
  }

  const body = (
    <Spin spinning={loading}>
      <Row gutter={[24, 16]} className="admin-settings-license__grid">
        <Col xs={24} lg={12}>
          <Form
            form={form}
            layout="vertical"
            size="small"
            onFinish={onFinish}
            className="admin-settings-form admin-settings-license__form"
          >
            <Form.Item
              name="license_key"
              label={t('license.keyLabel')}
              rules={[{ required: true, message: t('license.keyRequired') }]}
            >
              <Input.TextArea rows={6} placeholder={t('license.keyPlaceholder')} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={submitting} className="admin-settings-license__submit">
              {t('license.adminSave')}
            </Button>
          </Form>
        </Col>
        <Col xs={24} lg={12}>
          {status ? (
            <Descriptions bordered size="small" column={1} className="admin-settings-license__status">
              <Descriptions.Item label={t('license.statusValid')}>
                {status.valid ? t('license.validYes') : t('license.validNo')}
              </Descriptions.Item>
              {status.customer_id ? (
                <Descriptions.Item label={t('license.customer')}>{status.customer_id}</Descriptions.Item>
              ) : null}
              {status.expires_at ? (
                <Descriptions.Item label={t('license.expiresAt')}>
                  {new Date(status.expires_at).toLocaleString()}
                </Descriptions.Item>
              ) : null}
              {status.days_remaining != null ? (
                <Descriptions.Item label={t('license.daysRemaining')}>{status.days_remaining}</Descriptions.Item>
              ) : null}
              {status.license_key_masked ? (
                <Descriptions.Item label={t('license.keyMasked')}>{status.license_key_masked}</Descriptions.Item>
              ) : null}
              <Descriptions.Item label={t('license.hmacSecretEnv')}>
                {status.license_hmac_secret ?? t('license.hmacSecretUnset')}
              </Descriptions.Item>
              {status.license_hmac_secret_effective &&
              status.license_hmac_secret_effective !== status.license_hmac_secret ? (
                <Descriptions.Item label={t('license.hmacSecretEffective')}>
                  {status.license_hmac_secret_effective}
                  <span className="admin-settings-license__hint"> {t('license.hmacSecretDevDefault')}</span>
                </Descriptions.Item>
              ) : null}
            </Descriptions>
          ) : null}
        </Col>
      </Row>
    </Spin>
  )

  if (embedded) {
    return <div className="admin-settings-license">{body}</div>
  }

  return (
    <section
      className="admin-settings-section admin-settings-license"
      aria-labelledby="admin-settings-license-title"
    >
      <header className="admin-settings-section__header">
        <h3 id="admin-settings-license-title" className="admin-settings-section__title">
          {t('license.adminTitle')}
        </h3>
        <p className="admin-settings-section__desc">{t('license.adminSubtitle')}</p>
      </header>
      <div className="admin-settings-section__body">{body}</div>
    </section>
  )
}
