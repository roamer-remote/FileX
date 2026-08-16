import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { App, Button, Checkbox, Form, Input } from 'antd'
import AuthMethodSwitch from '@/components/AuthMethodSwitch'
import { formatApiError } from '@/api/index'
import { useAuthStore } from '@/stores/authStore'
import { getCachedUiState } from '@/lib/uiStateSync'
import AuthScreen from '@/components/AuthScreen'
import WechatLoginPanel from '@/components/WechatLoginPanel'

const AUTH_METHOD_KEY = 'filex_auth_method'
const REMEMBER_ME_KEY = 'filex_remember_me'

type AuthMethod = 'password' | 'wechat'

function readAuthMethod(): AuthMethod {
  const v = localStorage.getItem(AUTH_METHOD_KEY)
  return v === 'wechat' ? 'wechat' : 'password'
}

function readRememberMePreference(): boolean {
  return localStorage.getItem(REMEMBER_ME_KEY) !== '0'
}

export default function LoginPage() {
  const { message } = App.useApp()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)
  const completeWechatAuth = useAuthStore((s) => s.completeWechatAuth)
  const [submitting, setSubmitting] = useState(false)
  const [authMethod, setAuthMethod] = useState<AuthMethod>(() => readAuthMethod())
  const [rememberMe, setRememberMe] = useState(() => readRememberMePreference())
  const [form] = Form.useForm<{ username: string; password: string }>()

  useEffect(() => {
    const cached = getCachedUiState()
    if (cached?.login.auth_method === 'wechat' || cached?.login.auth_method === 'password') {
      setAuthMethod(cached.login.auth_method)
    } else {
      const fromLocal = readAuthMethod()
      if (fromLocal !== authMethod) setAuthMethod(fromLocal)
    }
    const rm = localStorage.getItem(REMEMBER_ME_KEY)
    if (rm !== null) setRememberMe(rm !== '0')
  }, [])

  useEffect(() => {
    localStorage.setItem(AUTH_METHOD_KEY, authMethod)
  }, [authMethod])

  useEffect(() => {
    localStorage.setItem(REMEMBER_ME_KEY, rememberMe ? '1' : '0')
  }, [rememberMe])

  async function onFinish(values: { username: string; password: string }) {
    setSubmitting(true)
    try {
      await login(values, rememberMe)
      navigate('/')
    } catch (err) {
      message.error(formatApiError(err))
    } finally {
      setSubmitting(false)
    }
  }

  async function onWechatSuccess(token: string) {
    try {
      await completeWechatAuth(token, rememberMe)
      message.success(t('wechat.loginSuccess'))
      navigate('/')
    } catch (err) {
      message.error(formatApiError(err))
    }
  }

  function onWechatNeedRegister(state: string) {
    navigate(`/register?wechat_state=${encodeURIComponent(state)}`)
  }

  const loginFooters = (
    <>
      <div className="auth-footer">
        <Link to="/register" className="auth-link">
          {t('login.registerCta')}
        </Link>
      </div>
      <div className="auth-footer auth-footer-hint">
        <span className="auth-footer-text">{t('login.contactAdminHint')}</span>
      </div>
    </>
  )

  return (
    <AuthScreen>
      <div className="auth-card-inner">
        <div className="auth-header">
          <div className="ah-title-group auth-heading">
            <h1 className="auth-title ah-title" dangerouslySetInnerHTML={{ __html: t('login.title') }} />
            <span className="auth-subtitle ah-sub">{t('login.subtitle')}</span>
          </div>
        </div>

        <AuthMethodSwitch
          value={authMethod}
          onChange={setAuthMethod}
          ariaLabel={t('login.authMethodAriaLabel')}
          options={[
            { label: t('login.methodUsername'), value: 'password' },
            { label: t('login.methodWechat'), value: 'wechat' },
          ]}
        />

        {authMethod === 'password' ? (
          <Form form={form} layout="vertical" className="auth-form" onFinish={(v) => void onFinish(v)}>
            <Form.Item
              name="username"
              label={t('login.identLabel')}
              rules={[{ required: true, message: t('validation.requiredIdent') }]}
            >
              <Input size="large" placeholder={t('login.identPlaceholder')} disabled={submitting} />
            </Form.Item>
            <Form.Item
              name="password"
              label={t('login.accessKeyLabel')}
              rules={[{ required: true, message: t('validation.requiredPassword') }]}
            >
              <Input.Password
                size="large"
                placeholder={t('login.accessKeyPlaceholder')}
                disabled={submitting}
                onPressEnter={() => form.submit()}
              />
            </Form.Item>
            <Form.Item>
              <Checkbox checked={rememberMe} onChange={(e) => setRememberMe(e.target.checked)}>
                {t('login.rememberMe')}
              </Checkbox>
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" size="large" className="auth-btn" block loading={submitting}>
                {t('login.authenticate')}
              </Button>
            </Form.Item>
          </Form>
        ) : (
          <div className="auth-wechat-tab wechat-embed-host">
            <div className="auth-wechat-main">
              <WechatLoginPanel
                mode="login"
                onSuccess={(token) => onWechatSuccess(token)}
                onNeedRegister={onWechatNeedRegister}
              />
              <div className="auth-remember-row" style={{ marginTop: 8 }}>
                <Checkbox checked={rememberMe} onChange={(e) => setRememberMe(e.target.checked)}>
                  {t('login.rememberMe')}
                </Checkbox>
              </div>
            </div>
            <div className="auth-wechat-tab-footers">{loginFooters}</div>
          </div>
        )}

        {authMethod === 'password' ? loginFooters : null}
      </div>
    </AuthScreen>
  )
}
