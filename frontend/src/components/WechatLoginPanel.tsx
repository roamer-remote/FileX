import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Alert, App, Button, Spin } from 'antd'
import {
  confirmWechatBind,
  fetchWechatBindQrcode,
  fetchWechatQrcode,
  fetchWechatStatus,
  triggerMockWechatCallback,
  type WechatQrcodeSession,
} from '@/api/wechat'
import { formatApiError } from '@/api/index'
import {
  getWxLoginBgcolor,
  getWxLoginColorScheme,
  getWxLoginHref,
  getWxLoginStyle,
  WECHAT_EMBED_SURFACE_CLASS,
} from '@/lib/wxLoginStyle'
import { resolveWechatErrorMessage } from '@/lib/wechatErrorMessage'
import { shouldAbortWechatPoll } from '@/lib/wechatPollFailure'
import { useThemeStore } from '@/stores/themeStore'

declare global {
  interface Window {
    WxLogin?: new (options: {
      self_redirect: boolean
      id: string
      appid: string
      scope: string
      redirect_uri: string
      state: string
      style?: string
      href?: string
      color_scheme?: 'light' | 'dark' | 'auto'
      bgcolor?: string
      fast_login?: number
    }) => void
  }
}

const WX_LOGIN_SCRIPT = 'https://res.wx.qq.com/connect/zh_CN/htmledition/js/wxLogin.js'
const POLL_MS = 2000

export type WxEmbedKind = 'qrcode' | 'quick'

function detectWxEmbedKind(iframe: HTMLIFrameElement | null): WxEmbedKind {
  if (!iframe?.src) return 'qrcode'
  const src = iframe.src.toLowerCase()
  if (src.includes('qrconnect')) return 'qrcode'
  if (
    src.includes('fast_login') ||
    src.includes('fastlogin') ||
    src.includes('/sso') ||
    src.includes('waplogin')
  ) {
    return 'quick'
  }
  return 'qrcode'
}

function watchWxEmbedKind(containerId: string, onKind: (kind: WxEmbedKind) => void): () => void {
  const run = () => {
    const el = document.getElementById(containerId)
    const iframe = el?.querySelector('iframe') as HTMLIFrameElement | null
    onKind(detectWxEmbedKind(iframe))
  }
  const el = document.getElementById(containerId)
  if (!el) return () => {}
  run()
  const mo = new MutationObserver(run)
  mo.observe(el, { childList: true, subtree: true, attributes: true, attributeFilter: ['src'] })
  const iframe = el.querySelector('iframe') as HTMLIFrameElement | null
  iframe?.addEventListener('load', run)
  const delays = [400, 1000, 2000].map((ms) => window.setTimeout(run, ms))
  return () => {
    mo.disconnect()
    iframe?.removeEventListener('load', run)
    delays.forEach((id) => window.clearTimeout(id))
  }
}

type WechatLoginPanelProps = {
  mode?: 'login' | 'bind'
  lockRefresh?: boolean
  onSuccess?: (accessToken: string) => void | Promise<void>
  onNeedRegister?: (state: string) => void
}

function loadWxLoginScript(): Promise<void> {
  if (window.WxLogin) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${WX_LOGIN_SCRIPT}"]`)
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('WxLogin.js load failed')))
      if (window.WxLogin) resolve()
      return
    }
    const script = document.createElement('script')
    script.src = WX_LOGIN_SCRIPT
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('WxLogin.js load failed'))
    document.body.appendChild(script)
  })
}

export default function WechatLoginPanel({
  mode = 'login',
  lockRefresh = false,
  onSuccess,
  onNeedRegister,
}: WechatLoginPanelProps) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const resolvedMode = useThemeStore((s) => s.resolvedMode)
  const containerId = useRef(`wx-login-${Math.random().toString(36).slice(2)}`)
  const pollRef = useRef<number | null>(null)
  const handledRef = useRef(false)
  const onSuccessRef = useRef(onSuccess)
  const onNeedRegisterRef = useRef(onNeedRegister)
  onSuccessRef.current = onSuccess
  onNeedRegisterRef.current = onNeedRegister

  const [loading, setLoading] = useState(true)
  const [session, setSession] = useState<WechatQrcodeSession | null>(null)
  const [mockBusy, setMockBusy] = useState(false)
  const [pollingActive, setPollingActive] = useState(false)
  const [embedKind, setEmbedKind] = useState<WxEmbedKind>('qrcode')
  const [showSuccessUi, setShowSuccessUi] = useState(false)
  const [embedError, setEmbedError] = useState<string | null>(null)
  const [awaitingBindConfirm, setAwaitingBindConfirm] = useState(false)
  const [confirmBusy, setConfirmBusy] = useState(false)
  const pollTokenRef = useRef<string | null>(null)
  const pollFailStreakRef = useRef(0)

  const stopPoll = useCallback(() => {
    if (pollRef.current != null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const applyEmbedError = useCallback(
    (detail: string) => {
      handledRef.current = true
      stopPoll()
      setPollingActive(false)
      setShowSuccessUi(false)
      const text = resolveWechatErrorMessage(detail, t)
      setEmbedError(text)
      const el = document.getElementById(containerId.current)
      if (el) el.innerHTML = ''
    },
    [stopPoll, t],
  )

  const handleStatus = useCallback(
    async (state: string) => {
      if (handledRef.current) return
      try {
        const res = await fetchWechatStatus(state, pollTokenRef.current ?? undefined)
        pollFailStreakRef.current = 0
        const data = res.data
        if (data.status === 'need_register') {
          handledRef.current = true
          stopPoll()
          setPollingActive(false)
          onNeedRegisterRef.current?.(state)
          return
        }
        if (data.status === 'awaiting_bind_confirm') {
          stopPoll()
          setPollingActive(false)
          setAwaitingBindConfirm(true)
          return
        }
        if (data.status === 'error') {
          applyEmbedError(data.message)
          return
        }
        if (data.status === 'success' && data.access_token) {
          handledRef.current = true
          stopPoll()
          setPollingActive(false)
          setShowSuccessUi(true)
          setAwaitingBindConfirm(false)
          const el = document.getElementById(containerId.current)
          if (el) el.innerHTML = ''
          const tokenFromStorage = localStorage.getItem('filex_wechat_callback_token')
          const token = tokenFromStorage || data.access_token
          if (tokenFromStorage) localStorage.removeItem('filex_wechat_callback_token')
          await onSuccessRef.current?.(token)
        }
      } catch {
        pollFailStreakRef.current += 1
        if (shouldAbortWechatPoll(pollFailStreakRef.current)) {
          handledRef.current = true
          stopPoll()
          setPollingActive(false)
          applyEmbedError(t('wechat.errorPollFailed'))
        }
      }
    },
    [applyEmbedError, stopPoll],
  )

  const handleConfirmBind = useCallback(async () => {
    if (!session?.state || confirmBusy) return
    setConfirmBusy(true)
    try {
      const res = await confirmWechatBind(session.state, pollTokenRef.current ?? undefined)
      handledRef.current = true
      setAwaitingBindConfirm(false)
      setShowSuccessUi(true)
      const el = document.getElementById(containerId.current)
      if (el) el.innerHTML = ''
      await onSuccessRef.current?.(res.data.access_token)
    } catch (err) {
      message.error(formatApiError(err))
    } finally {
      setConfirmBusy(false)
    }
  }, [confirmBusy, message, session?.state])

  const startPoll = useCallback(
    (state: string) => {
      stopPoll()
      setPollingActive(true)
      void handleStatus(state)
      pollRef.current = window.setInterval(() => void handleStatus(state), POLL_MS)
    },
    [handleStatus, stopPoll],
  )

  const initSession = useCallback(async () => {
    handledRef.current = false
    pollFailStreakRef.current = 0
    setEmbedKind('qrcode')
    setShowSuccessUi(false)
    setAwaitingBindConfirm(false)
    setEmbedError(null)
    setLoading(true)
    setPollingActive(false)
    stopPoll()
    try {
      const res = mode === 'bind' ? await fetchWechatBindQrcode() : await fetchWechatQrcode()
      const sess = res.data
      pollTokenRef.current = sess.poll_token
      setSession(sess)
      startPoll(sess.state)
    } catch (err) {
      message.error(formatApiError(err))
    } finally {
      setLoading(false)
    }
  }, [message, mode, startPoll, stopPoll])

  // 仅挂载 / 切换 login|bind 时拉码；勿依赖 onSuccess 等回调，避免父组件重渲染清空 embedError
  useEffect(() => {
    void initSession()
    return () => stopPoll()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initSession 内含 mode
  }, [mode])

  useEffect(() => {
    const onMessage = (ev: MessageEvent) => {
      const allowed = new Set<string>([window.location.origin])
      if (session?.redirect_uri) {
        try {
          allowed.add(new URL(session.redirect_uri).origin)
        } catch {
          /* ignore */
        }
      }
      if (!allowed.has(ev.origin)) return
      const data = ev.data as { type?: string; token?: string | null; kind?: string; message?: string } | null
      if (!data || data.type !== 'filex_wechat_callback') return
      if (handledRef.current) return

      if (data.kind === 'error') {
        applyEmbedError(typeof data.message === 'string' ? data.message : '')
        return
      }

      const el = document.getElementById(containerId.current)
      if (el) el.innerHTML = ''

      if (data.kind === 'need_register') {
        handledRef.current = true
        stopPoll()
        setPollingActive(false)
        setShowSuccessUi(false)
        if (session?.state) onNeedRegisterRef.current?.(session.state)
        return
      }

      if (data.kind === 'awaiting_bind_confirm') {
        stopPoll()
        setPollingActive(false)
        setAwaitingBindConfirm(true)
        return
      }

      if (data.token) {
        handledRef.current = true
        stopPoll()
        setPollingActive(false)
        setShowSuccessUi(true)
        void onSuccessRef.current?.(data.token)
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [applyEmbedError, session?.redirect_uri, session?.state, stopPoll])

  useEffect(() => {
    if (!session || session.mock_mode || loading) return

    let cancelled = false
    void (async () => {
      try {
        await loadWxLoginScript()
        if (cancelled) return
        const el = document.getElementById(containerId.current)
        if (!el) return
        el.innerHTML = ''
        new window.WxLogin!({
          self_redirect: true,
          id: containerId.current,
          appid: session.app_id,
          scope: 'snsapi_login',
          redirect_uri: encodeURIComponent(session.redirect_uri),
          state: session.state,
          style: getWxLoginStyle(resolvedMode),
          color_scheme: getWxLoginColorScheme(resolvedMode),
          bgcolor: getWxLoginBgcolor(resolvedMode),
          href: getWxLoginHref(resolvedMode),
        })
      } catch (err) {
        if (!cancelled) message.error(formatApiError(err))
      }
    })()

    return () => {
      cancelled = true
      const el = document.getElementById(containerId.current)
      if (el) el.innerHTML = ''
    }
  }, [session, loading, message, resolvedMode])

  useEffect(() => {
    if (!session || session.mock_mode || loading) return
    return watchWxEmbedKind(containerId.current, setEmbedKind)
  }, [session, loading])

  async function onMockScan(scenario: 'need_register' | 'login') {
    if (!session?.mock_mode || mockBusy) return
    setMockBusy(true)
    try {
      await triggerMockWechatCallback(session.state, scenario)
      await handleStatus(session.state)
    } catch (err) {
      message.error(formatApiError(err))
    } finally {
      setMockBusy(false)
    }
  }

  return (
    <div className={`wechat-login-panel ${WECHAT_EMBED_SURFACE_CLASS}`}>
      {!session && loading ? (
        <div className="wechat-login-loading">
          <Spin />
          <span>{t('wechat.loadingQrcode')}</span>
        </div>
      ) : session?.mock_mode ? (
        <div className="wechat-mock-panel">
          <p className="wechat-mock-hint">{t('wechat.mockHint')}</p>
          {mode === 'login' ? (
            <div className="wechat-mock-actions">
              <Button block loading={mockBusy} onClick={() => void onMockScan('need_register')}>
                {t('wechat.mockNeedRegister')}
              </Button>
              <Button block loading={mockBusy} onClick={() => void onMockScan('login')}>
                {t('wechat.mockLogin')}
              </Button>
            </div>
          ) : (
            <Button block loading={mockBusy} type="primary" onClick={() => void onMockScan('login')}>
              {t('wechat.mockBind')}
            </Button>
          )}
          <Button type="link" size="small" disabled={lockRefresh || mockBusy || pollingActive} onClick={() => void initSession()}>
            {t('wechat.refreshQrcode')}
          </Button>
        </div>
      ) : showSuccessUi ? (
        <div className="wechat-login-success" role="status">
          <p className="wechat-login-success-text">
            {mode === 'bind' ? t('account.wechatBindSuccess') : t('wechat.loginSuccess')}
          </p>
        </div>
      ) : awaitingBindConfirm && mode === 'bind' ? (
        <div className="wechat-bind-confirm">
          <p className="wechat-scan-hint">{t('wechat.bindConfirmHint')}</p>
          <Button type="primary" block loading={confirmBusy} onClick={() => void handleConfirmBind()}>
            {t('wechat.bindConfirmButton')}
          </Button>
          <Button
            type="link"
            size="small"
            disabled={lockRefresh || confirmBusy}
            onClick={() => void initSession()}
          >
            {t('wechat.refreshQrcode')}
          </Button>
        </div>
      ) : embedError ? (
        <div className="wechat-login-error">
          <Alert type="error" showIcon message={t('wechat.errorTitle')} description={embedError} />
          <Button
            type="primary"
            ghost
            disabled={lockRefresh || loading}
            onClick={() => void initSession()}
            className="wechat-login-error-retry"
          >
            {t('wechat.refreshQrcode')}
          </Button>
        </div>
      ) : session ? (
        <div className="wechat-qrcode-wrap">
          <div className="wechat-qrcode-stage">
            {loading ? (
              <div className="wechat-login-loading wechat-login-loading--overlay">
                <Spin />
                <span>{t('wechat.loadingQrcode')}</span>
              </div>
            ) : null}
            <div
              id={containerId.current}
              className={`wechat-qrcode-container ${embedKind === 'quick' ? 'is-wechat-quick-login' : 'is-wechat-qrcode'}`}
            />
          </div>
          <p className="wechat-scan-hint">{mode === 'bind' ? t('wechat.bindScanHint') : t('wechat.scanHint')}</p>
          <Button
            type="link"
            size="small"
            disabled={lockRefresh || loading || pollingActive}
            onClick={() => void initSession()}
          >
            {t('wechat.refreshQrcode')}
          </Button>
        </div>
      ) : (
        <div className="wechat-login-loading">
          <Spin />
          <span>{t('wechat.loadingQrcode')}</span>
        </div>
      )}
    </div>
  )
}
