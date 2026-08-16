import { useEffect, useState, type ReactNode } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Button, Input, Spin, message } from 'antd'
import { getShareInfo, verifySharePassword, getShareDownloadUrl, type ShareInfo } from '@/api/share'
import { SHARE_INACTIVE_NAV_PATH } from '@/lib/shareNavigation'
import AppBackdrop from '@/components/AppBackdrop'
import AppLogo from '@/components/AppLogo'
import './Share.css'

function ShareFrame({ children }: { children: ReactNode }) {
  return (
    <div className="share-root">
      <AppBackdrop variant="auth" />
      <AppLogo placement="auth" to="/login" />
      {children}
    </div>
  )
}

export default function SharePage() {
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [shareInfo, setShareInfo] = useState<ShareInfo | null>(null)
  const [password, setPassword] = useState('')
  const [verified, setVerified] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      setShareInfo(null)
      try {
        const res = await getShareInfo(token)
        if (cancelled) return
        setShareInfo(res.data)
        setVerified(false)
        setPassword('')
      } catch (e: unknown) {
        const err = e as { response?: { data?: { detail?: string } } }
        if (!cancelled) {
          setShareInfo(null)
          setError(err.response?.data?.detail || t('share.linkExpired'))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [token, t])

  useEffect(() => {
    if (!shareInfo || loading || error) return
    if (shareInfo.has_password && !verified) return
    window.location.replace(getShareDownloadUrl(token))
  }, [shareInfo, loading, error, token, verified])

  async function onVerify() {
    if (!password) return
    setVerifying(true)
    try {
      await verifySharePassword(token, password)
      setVerified(true)
    } catch {
      message.error(t('share.incorrectPasskey'))
    } finally {
      setVerifying(false)
    }
  }

  if (loading) {
    return (
      <ShareFrame>
        <div className="share-card">
          <Spin spinning tip={t('share.loadingText')} />
        </div>
      </ShareFrame>
    )
  }

  if (error || !shareInfo) {
    return (
      <ShareFrame>
        <div className="share-card">
          <div className="sc-status">
            <span className="sc-dot-dead" />
            <span className="sc-status-text">{t('share.linkInactive')}</span>
          </div>
          <p className="sc-error-title">{t('share.decryptionFailed')}</p>
          <p className="sc-error-sub">{error || t('share.linkExpired')}</p>
          <Button block className="sc-home-btn" onClick={() => navigate(SHARE_INACTIVE_NAV_PATH)}>
            {t('share.goLogin')}
          </Button>
        </div>
        <div className="share-footer">
          <span className="sf-text">FileX</span>
        </div>
      </ShareFrame>
    )
  }

  if (shareInfo.has_password && !verified) {
    return (
      <ShareFrame>
        <div className="share-card">
          <div className="sc-status">
            <span className="sc-dot-lock" />
            <span className="sc-status-text">{t('share.encryptedLink')}</span>
          </div>
          <p className="sc-pw-hint">{t('share.decryptionHint')}</p>
          <div className="sc-pw-form">
            <Input.Password
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t('share.passkeyPlaceholder')}
              size="large"
              onPressEnter={() => void onVerify()}
            />
            <Button
              type="primary"
              size="large"
              block
              loading={verifying}
              onClick={() => void onVerify()}
              className="sc-verify-btn"
            >
              {t('share.decrypt')}
            </Button>
          </div>
        </div>
        <div className="share-footer">
          <span className="sf-text">FileX</span>
        </div>
      </ShareFrame>
    )
  }

  return (
    <ShareFrame>
      <div className="share-card">
        <Spin spinning tip={t('share.redirectingDownload')} />
      </div>
      <div className="share-footer">
        <span className="sf-text">FileX</span>
      </div>
    </ShareFrame>
  )
}
