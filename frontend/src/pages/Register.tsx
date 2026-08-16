import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { App, Alert, Button, Form, Input } from 'antd'
import { formatApiError } from '@/api/index'
import { useAuthStore } from '@/stores/authStore'
import AuthScreen from '@/components/AuthScreen'

const REMEMBER_ME_KEY = 'filex_remember_me'

function readRememberMePreference(): boolean {
  return localStorage.getItem(REMEMBER_ME_KEY) !== '0'
}

export default function RegisterPage() {
  const { message } = App.useApp()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const wechatState = useMemo(() => (searchParams.get('wechat_state') || '').trim() || null, [searchParams])
  const register = useAuthStore((s) => s.register)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm<{ username: string; password: string; confirm: string }>()

  async function onFinish(values: { username: string; password: string }) {
    setSubmitting(true)
    try {
      await register(
        { username: values.username.trim(), password: values.password, wechat_state: wechatState },
        readRememberMePreference(),
      )
      message.success(t('register.success'))
      navigate('/')
    } catch (err) {
      message.error(formatApiError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthScreen>
      <div className="auth-card-inner">
        <div className="auth-header">
          <div className="ah-title-group auth-heading">
            <h1 className="auth-title ah-title" dangerouslySetInnerHTML={{ __html: t('register.title') }} />
            <span className="auth-subtitle ah-sub">{t('register.subtitle')}</span>
          </div>
        </div>
        {wechatState ? (
          <Alert type="info" showIcon message={t('register.wechatPendingHint')} style={{ marginBottom: 16 }} />
        ) : null}
        <Form form={form} layout="vertical" className="auth-form" onFinish={(v) => void onFinish(v)}>
          <Form.Item name="username" label={t('login.identLabel')} rules={[{ required: true, message: t('validation.requiredIdent') }]}>
            <Input size="large" placeholder={t('login.identPlaceholder')} disabled={submitting} />
          </Form.Item>
          <Form.Item
            name="password"
            label={t('login.accessKeyLabel')}
            rules={[
              { required: true, message: t('validation.requiredPassword') },
              { min: 6, message: t('validation.passwordMinLength') },
              { max: 100, message: t('validation.passwordMaxLength') },
            ]}
          >
            <Input.Password size="large" placeholder={t('login.accessKeyPlaceholder')} disabled={submitting} />
          </Form.Item>
          <Form.Item
            name="confirm"
            label={t('register.confirmLabel')}
            dependencies={['password']}
            rules={[
              { required: true, message: t('validation.requiredConfirm') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error(t('validation.passwordMismatch')))
                },
              }),
            ]}
          >
            <Input.Password size="large" placeholder={t('register.confirmPlaceholder')} disabled={submitting} onPressEnter={() => form.submit()} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" size="large" className="auth-btn" block loading={submitting}>
              {t('register.submit')}
            </Button>
          </Form.Item>
        </Form>
        <div className="auth-footer">
          <Link to="/login" className="auth-link">
            {t('register.backToLogin')}
          </Link>
        </div>
        <div className="auth-footer" style={{ marginTop: 8 }}>
          <span className="auth-footer-text">{t('register.hint')}</span>
        </div>
      </div>
    </AuthScreen>
  )
}
