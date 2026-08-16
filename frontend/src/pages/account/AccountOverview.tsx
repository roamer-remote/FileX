import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { App, Avatar, Button, Modal, Spin, Tag, Tooltip } from 'antd'
import {
  CameraOutlined,
  ClockCircleOutlined,
  LockOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  WechatOutlined,
} from '@ant-design/icons'
import { getUserPreferences } from '@/api/settings'
import { useAuthStore } from '@/stores/authStore'
import { uploadAvatar, deleteAvatar } from '@/api/auth'
import { formatApiError } from '@/api/index'
import { formatDate } from '@/utils'
import ApiKeysSection from '@/components/ApiKeysSection'
import { DeleteActionIcon } from '@/components/DeleteActionIcon'
import ChangePasswordForm from '@/components/ChangePasswordForm'
import WechatBindPanel from '@/components/WechatBindPanel'
import { useUserAvatarUrl } from '@/hooks/useUserAvatarUrl'
import './AccountOverview.css'

function StatInlineItem({
  icon,
  label,
  value,
  mono,
}: {
  icon: ReactNode
  label: string
  value: ReactNode
  mono?: boolean
}) {
  return (
    <div className="account-stat-item">
      <div className="account-stat-icon-wrap">{icon}</div>
      <div className="account-stat-item-text account-stat-item-text--cols">
        <div className={'account-stat-value' + (mono ? ' account-stat-value--mono' : '')}>{value}</div>
        <div className="account-stat-label">{label}</div>
      </div>
    </div>
  )
}

export default function AccountOverview({
  embedded = false,
  onNavigateAway,
}: {
  embedded?: boolean
  onNavigateAway?: () => void
}) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const user = useAuthStore((s) => s.user)
  const refreshUser = useAuthStore((s) => s.refreshUser)
  const bumpAvatarRevision = useAuthStore((s) => s.bumpAvatarRevision)
  const avatarRevision = useAuthStore((s) => s.avatarRevision)
  const { avatarUrl, initial } = useUserAvatarUrl(user?.has_avatar, user?.username, avatarRevision)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [changePasswordOpen, setChangePasswordOpen] = useState(false)
  const [wechatBindOpen, setWechatBindOpen] = useState(false)
  const [overrideCount, setOverrideCount] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    const refreshSummary = async () => {
      try {
        const res = await getUserPreferences({ skipErrorToast: true })
        if (!cancelled) {
          setOverrideCount(Object.keys(res.data.overrides).length)
        }
      } catch {
        if (!cancelled) setOverrideCount(null)
      }
    }
    void refreshSummary()
    const onChanged = () => {
      void refreshSummary()
    }
    window.addEventListener('filex:user-settings-changed', onChanged)
    return () => {
      cancelled = true
      window.removeEventListener('filex:user-settings-changed', onChanged)
    }
  }, [])

  const handleWechatBindSuccess = useCallback(async () => {
    await refreshUser()
    setWechatBindOpen(false)
    message.success(t('account.wechatBindSuccess'))
  }, [message, refreshUser, t])

  function onPickAvatarClick() {
    fileInputRef.current?.click()
  }

  async function onAvatarFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setUploading(true)
    try {
      await uploadAvatar(file, { skipErrorToast: true })
      await refreshUser()
      bumpAvatarRevision()
      message.success(t('account.avatarUploadSuccess'))
    } catch (err) {
      message.error(formatApiError(err))
    } finally {
      setUploading(false)
    }
  }

  async function onRemoveAvatar() {
    if (!user?.has_avatar) {
      message.info(t('account.avatarRemoveNothing'))
      return
    }
    setRemoving(true)
    try {
      await deleteAvatar({ skipErrorToast: true })
      await refreshUser()
      bumpAvatarRevision()
      message.success(t('account.avatarRemoveSuccess'))
    } catch (err) {
      message.error(formatApiError(err))
    } finally {
      setRemoving(false)
    }
  }

  const roleLine = user?.is_admin ? t('account.roleLineAdmin') : t('account.roleLineUser')
  const statusTag = user?.is_active ? (
    <Tag color="success">{t('account.statusNormal')}</Tag>
  ) : (
    <Tag color="error">{t('account.statusAbnormal')}</Tag>
  )

  return (
    <div
      className={
        'account-overview account-tab-panel' + (embedded ? ' account-overview--embedded' : '')
      }
    >
      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif"
        style={{ display: 'none' }}
        onChange={(e) => void onAvatarFileChange(e)}
      />
      <div className="account-overview-shell">
        <div className="account-overview-layout">
          <aside className="account-overview-profile" aria-label={t('account.profileAsideAria')}>
            <div className="account-overview-avatar-wrap">
              <button
                type="button"
                className="account-overview-avatar-trigger"
                onClick={onPickAvatarClick}
                disabled={uploading || removing}
                aria-label={t('account.avatarClickToChange')}
              >
                <Avatar size={112} className="account-overview-avatar" src={avatarUrl ?? undefined}>
                  {!avatarUrl ? initial : null}
                </Avatar>
                <span className="account-overview-avatar-overlay" aria-hidden>
                  {uploading ? <Spin size="small" /> : <CameraOutlined />}
                </span>
              </button>
              {(user?.has_avatar || avatarUrl) && (
                <Tooltip title={t('account.avatarRemove')}>
                  <button
                    type="button"
                    className="account-overview-avatar-remove"
                    disabled={removing || uploading}
                    aria-label={t('account.avatarRemove')}
                    onClick={(e) => {
                      e.stopPropagation()
                      void onRemoveAvatar()
                    }}
                  >
                    {removing ? <Spin size="small" /> : <DeleteActionIcon />}
                  </button>
                </Tooltip>
              )}
            </div>
            <Button
              type="default"
              className="account-overview-change-password"
              icon={<LockOutlined />}
              block
              onClick={() => setChangePasswordOpen(true)}
            >
              {t('account.tabPassword')}
            </Button>
            {!user?.wechat_bound ? (
              <Button
                type="default"
                className="account-overview-bind-wechat"
                icon={<WechatOutlined />}
                block
                onClick={() => setWechatBindOpen(true)}
              >
                {t('account.bindWechat')}
              </Button>
            ) : (
              <Tag color="success" className="account-wechat-bound-tag">{t('account.wechatBound')}</Tag>
            )}
            <h2 className="account-overview-username">{user?.username ?? '—'}</h2>
            <p className="account-overview-role-line">{roleLine}</p>
          </aside>

          <div className="account-overview-content">
            <div className="account-stat-card account-stat-card--combined">
              <StatInlineItem
                icon={<SafetyCertificateOutlined />}
                label={t('account.fieldStatus')}
                value={statusTag}
              />
              <div className="account-stat-divider" aria-hidden />
              <StatInlineItem
                icon={<ClockCircleOutlined />}
                label={t('account.fieldCreatedAt')}
                value={user?.created_at ? formatDate(user.created_at) : '—'}
                mono
              />
            </div>

            <section className="account-overview-preferences" aria-label={t('account.preferences.title')}>
              <div className="account-preferences-card">
                <div className="account-preferences-card__inner">
                  <SettingOutlined className="account-preferences-card__icon" aria-hidden />
                  <div className="account-preferences-card__main">
                    <h3 className="account-preferences-card__title">{t('account.preferences.title')}</h3>
                    <p className="account-preferences-card__summary">
                      {overrideCount === null
                        ? t('account.preferences.summaryUnknown')
                        : overrideCount === 0
                          ? t('account.preferences.summaryInherited')
                          : t('account.preferences.summaryOverrides', { count: overrideCount })}
                    </p>
                  </div>
                  <Link
                    to="/account/preferences"
                    className="account-preferences-card__link"
                    onClick={() => onNavigateAway?.()}
                  >
                    {t('account.preferences.openFullSettings')}
                    <RightOutlined aria-hidden />
                  </Link>
                </div>
              </div>
            </section>

            <section className="account-overview-api-keys" aria-label={t('apiKeys.title')}>
              <ApiKeysSection embedded />
            </section>
          </div>
        </div>
      </div>


      <Modal
        title={t('account.bindWechatTitle')}
        open={wechatBindOpen}
        onCancel={() => setWechatBindOpen(false)}
        footer={null}
        destroyOnClose
        width={420}
        rootClassName="wechat-bind-modal"
      >
        <WechatBindPanel onSuccess={handleWechatBindSuccess} />
      </Modal>

      <Modal
        title={t('changePassword.title')}
        open={changePasswordOpen}
        onCancel={() => setChangePasswordOpen(false)}
        footer={null}
        destroyOnClose
        width={480}
        className="account-change-password-modal"
      >
        <ChangePasswordForm onDismiss={() => setChangePasswordOpen(false)} />
      </Modal>
    </div>
  )
}
