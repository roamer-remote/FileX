import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { App, Button, Divider, Form, Input } from 'antd'
import type { FormProps } from 'antd'
import { InfoCircleOutlined, LockOutlined } from '@ant-design/icons'
import { changePassword } from '@/api/auth'
import { formatApiError } from '@/api/index'
import { useAuthStore } from '@/stores/authStore'
import '../pages/ChangePassword.css'

const NEW_PASSWORD_MAX = 100

function passwordStrengthScore(pw: string): 0 | 1 | 2 | 3 {
  if (!pw) return 0
  let score = 0
  if (pw.length >= 6) score += 1
  if (pw.length >= 10) score += 1
  const variety = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((re) => re.test(pw)).length
  if (variety >= 2) score += 1
  if (variety >= 3 && pw.length >= 8) score += 1
  if (score <= 1) return 1
  if (score <= 2) return 2
  return 3
}

export type ChangePasswordFormProps = {
  /** 成功提交后、跳转登录前关闭宿主弹窗等 */
  onDismiss?: () => void
}

export default function ChangePasswordForm({ onDismiss }: ChangePasswordFormProps) {
  const { t } = useTranslation()
  const { modal } = App.useApp()
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const [form] = Form.useForm<{ current_password: string; new_password: string; confirm: string }>()
  const [submitting, setSubmitting] = useState(false)
  const newPw = Form.useWatch('new_password', form) ?? ''

  const strength = useMemo(() => passwordStrengthScore(newPw), [newPw])

  const strengthLabelKey = useMemo(() => {
    if (!newPw) return 'changePassword.strengthNone' as const
    if (strength === 1) return 'changePassword.strengthWeak' as const
    if (strength === 2) return 'changePassword.strengthMedium' as const
    return 'changePassword.strengthStrong' as const
  }, [newPw, strength])

  async function onFinish(values: { current_password: string; new_password: string; confirm: string }) {
    setSubmitting(true)
    try {
      await changePassword({ current_password: values.current_password, new_password: values.new_password })
      modal.success({
        title: t('changePassword.modalSuccessTitle'),
        content: t('changePassword.successAndRelogin'),
        okText: t('common.confirm'),
        afterClose: () => {
          onDismiss?.()
          logout()
          navigate('/login', { replace: true })
        },
      })
    } catch (err) {
      modal.error({
        title: t('changePassword.modalFailTitle'),
        content: formatApiError(err),
        okText: t('common.confirm'),
      })
    } finally {
      setSubmitting(false)
    }
  }

  const onFinishFailed: NonNullable<FormProps['onFinishFailed']> = ({ errorFields }) => {
    const content =
      errorFields
        .flatMap((f) => f.errors)
        .filter(Boolean)
        .join('\n') || t('changePassword.validationUnknown')
    modal.warning({
      title: t('changePassword.modalValidationTitle'),
      content,
      okText: t('common.confirm'),
    })
  }

  const strengthMeter =
    newPw.length > 0 ? (
      <div className="cp-strength">
        <div className="cp-strength-head">
          <span className="cp-strength-label">{t('changePassword.strengthLabel')}</span>
          <span className={`cp-strength-value cp-strength-value--${strength}`}>{t(strengthLabelKey)}</span>
        </div>
        <div className="cp-strength-bars" aria-hidden>
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className={`cp-strength-bar ${i <= strength ? `cp-strength-bar--active cp-strength-bar--${strength}` : ''}`}
            />
          ))}
        </div>
      </div>
    ) : null

  return (
    <>
      <div className="cp-hint" role="note">
        <InfoCircleOutlined className="cp-hint-icon" aria-hidden />
        <p className="cp-hint-text">{t('changePassword.securityHint')}</p>
      </div>

      <Form
        form={form}
        layout="vertical"
        className="cp-form-card cp-form-card--embedded"
        onFinish={(v) => void onFinish(v)}
        onFinishFailed={onFinishFailed}
        scrollToFirstError
      >
        <div className="cp-divider-label">{t('changePassword.sectionCurrent')}</div>
        <Form.Item
          name="current_password"
          label={t('changePassword.current')}
          rules={[{ required: true, message: t('validation.requiredPassword') }]}
        >
          <Input.Password
            size="large"
            autoComplete="current-password"
            prefix={<LockOutlined style={{ color: 'var(--text-muted)' }} />}
          />
        </Form.Item>

        <Divider style={{ margin: '8px 0 16px' }} />

        <div className="cp-divider-label">{t('changePassword.sectionNew')}</div>
        <Form.Item
          name="new_password"
          label={t('changePassword.new')}
          rules={[
            { required: true, message: t('validation.requiredPassword') },
            { min: 6, message: t('validation.passwordMinLength') },
            { max: NEW_PASSWORD_MAX, message: t('validation.passwordMaxLength') },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || value !== getFieldValue('current_password')) return Promise.resolve()
                return Promise.reject(new Error(t('changePassword.sameAsOld')))
              },
            }),
          ]}
          dependencies={['current_password']}
          extra={
            <>
              {strengthMeter}
              <div className="cp-char-count">
                {newPw.length} / {NEW_PASSWORD_MAX}
              </div>
            </>
          }
        >
          <Input.Password
            size="large"
            autoComplete="new-password"
            prefix={<LockOutlined style={{ color: 'var(--text-muted)' }} />}
          />
        </Form.Item>
        <Form.Item
          name="confirm"
          label={t('changePassword.confirm')}
          dependencies={['new_password']}
          rules={[
            { required: true, message: t('validation.requiredConfirm') },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue('new_password') === value) return Promise.resolve()
                return Promise.reject(new Error(t('validation.passwordMismatch')))
              },
            }),
          ]}
        >
          <Input.Password
            size="large"
            autoComplete="new-password"
            prefix={<LockOutlined style={{ color: 'var(--text-muted)' }} />}
          />
        </Form.Item>
        <div className="cp-actions">
          <Button type="default" htmlType="button" size="large" onClick={() => form.resetFields()} disabled={submitting}>
            {t('changePassword.clear')}
          </Button>
          <Button type="primary" htmlType="submit" size="large" loading={submitting}>
            {t('changePassword.submit')}
          </Button>
        </div>
      </Form>
    </>
  )
}
