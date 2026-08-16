import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button, Modal } from 'antd'
import { getApiKeys } from '@/api/apiKeys'
import {
  API_KEY_ONBOARDING_MODAL_GUARD,
  initialApiKeyGateState,
  loadApiKeyGateState,
  readApiKeyGateCache,
  writeApiKeyGateCache,
  type ApiKeyGateState,
} from '@/lib/apiKeyOnboardingGate'
import ApiKeyOnboardingWizard from './ApiKeyOnboardingWizard'

const MODAL_WIDTH = 'min(560px, calc(100vw - 32px))'

export type { ApiKeyGateState }

type Props = {
  userId: number | undefined
  onGateStateChange?: (state: ApiKeyGateState) => void
}

export default function ApiKeyOnboardingGate({ userId, onGateStateChange }: Props) {
  const { t } = useTranslation()
  const [gate, setGate] = useState<ApiKeyGateState>(() => initialApiKeyGateState(userId))
  const fetchSeq = useRef(0)

  const setGateState = useCallback(
    (next: ApiKeyGateState) => {
      setGate(next)
      onGateStateChange?.(next)
    },
    [onGateStateChange],
  )

  const refreshGate = useCallback(async () => {
    if (!userId) {
      setGateState('pending')
      return
    }
    const seq = ++fetchSeq.current
    const cached = readApiKeyGateCache(userId)
    if (cached !== 'ok') {
      setGateState(cached === 'blocked' ? 'blocked' : 'pending')
    }
    const next = await loadApiKeyGateState(async () => {
      const res = await getApiKeys()
      return res.data
    })
    if (seq !== fetchSeq.current) return
    setGateState(next)
    if (next === 'ok' || next === 'blocked') {
      writeApiKeyGateCache(userId, next)
    }
  }, [setGateState, userId])

  useEffect(() => {
    setGate(initialApiKeyGateState(userId))
    void refreshGate()
  }, [refreshGate, userId])

  if (!userId) return null

  const modalGuard = API_KEY_ONBOARDING_MODAL_GUARD

  return (
    <>
      <Modal
        open={gate === 'error'}
        title={t('apiKeyOnboarding.title')}
        width={MODAL_WIDTH}
        rootClassName="apikeys-modal apikeys-modal--onboarding"
        {...modalGuard}
        centered
        zIndex={1200}
        footer={
          <Button type="primary" onClick={() => void refreshGate()}>
            {t('apiKeyOnboarding.retry')}
          </Button>
        }
      >
        <p className="ak-onboarding-intro">{t('apiKeyOnboarding.loadError')}</p>
      </Modal>

      <ApiKeyOnboardingWizard
        open={gate === 'blocked'}
        onEnsured={() => void refreshGate()}
      />
    </>
  )
}
