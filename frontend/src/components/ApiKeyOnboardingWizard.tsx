import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { App, Button, Input, Modal, Space, Steps } from 'antd'
import { CopyOutlined } from '@ant-design/icons'
import { createApiKey, type ApiKeyCreateResponse } from '@/api/apiKeys'
import { buildDingSkillInstallPrompt, fetchAgentSkillInstallPrompt } from '@/lib/agentSkillInstall'
import { API_KEY_ONBOARDING_MODAL_GUARD } from '@/lib/apiKeyOnboardingGate'
import {
  canAdvanceFromStep2,
  wizardStepTitleKey,
  type ApiKeyWizardStep,
} from '@/lib/apiKeyOnboardingWizard'
import { copyToClipboard } from '@/utils'
import '@/pages/ApiKeys.css'

const MODAL_WIDTH = 'min(560px, calc(100vw - 32px))'

type Props = {
  open: boolean
  onEnsured: () => void
}

function resetWizardState(): {
  step: ApiKeyWizardStep
  name: string
  created: ApiKeyCreateResponse | null
  installCopySucceeded: boolean
} {
  return { step: 1, name: '', created: null, installCopySucceeded: false }
}

export default function ApiKeyOnboardingWizard({ open, onEnsured }: Props) {
  const { message: msg } = App.useApp()
  const { t } = useTranslation()
  const [step, setStep] = useState<ApiKeyWizardStep>(1)
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [created, setCreated] = useState<ApiKeyCreateResponse | null>(null)
  const [installCopySucceeded, setInstallCopySucceeded] = useState(false)

  useEffect(() => {
    if (!open) {
      const reset = resetWizardState()
      setStep(reset.step)
      setName(reset.name)
      setCreated(reset.created)
      setInstallCopySucceeded(reset.installCopySucceeded)
    }
  }, [open])

  const [installText, setInstallText] = useState('')

  useEffect(() => {
    if (!created?.plain_text_key) {
      setInstallText('')
      return
    }
    let cancelled = false
    fetchAgentSkillInstallPrompt(window.location.origin, {
      apiKey: created.plain_text_key,
    }).then((text) => {
      if (!cancelled) setInstallText(text)
    }).catch(() => {
      if (!cancelled) {
        setInstallText(
          buildDingSkillInstallPrompt(window.location.origin, {
            apiKey: created.plain_text_key,
          })
        )
      }
    })
    return () => { cancelled = true }
  }, [created?.plain_text_key])

  async function handleCreate() {
    const trimmed = name.trim()
    if (!trimmed) {
      msg.warning(t('apiKeys.nameRequired'))
      return
    }
    if (creating) return
    setCreating(true)
    try {
      const res = await createApiKey(trimmed)
      setCreated(res.data)
    } catch {
      /* interceptor */
    } finally {
      setCreating(false)
    }
  }

  async function handleCopyKey() {
    if (!created) return
    try {
      await copyToClipboard(created.plain_text_key)
      msg.success(t('apiKeys.copyComplete'))
    } catch {
      msg.error(t('apiKeys.copyFailed'))
    }
  }

  async function handleCopyInstall() {
    if (!installText) return
    try {
      await copyToClipboard(installText)
      setInstallCopySucceeded(true)
      msg.success(t('apiKeyOnboardingWizard.copyInstallSuccess'))
    } catch {
      msg.error(t('apiKeyOnboardingWizard.copyInstallFailed'))
    }
  }

  function handleFinish() {
    const reset = resetWizardState()
    setStep(reset.step)
    setName(reset.name)
    setCreated(reset.created)
    setInstallCopySucceeded(reset.installCopySucceeded)
    onEnsured()
  }

  function renderFooter() {
    if (step === 1) {
      if (!created) {
        return (
          <Button type="primary" loading={creating} onClick={() => void handleCreate()}>
            {t('apiKeys.generate')}
          </Button>
        )
      }
      return (
        <Space>
          <Button icon={<CopyOutlined />} onClick={() => void handleCopyKey()}>
            {t('apiKeys.copyKey')}
          </Button>
          <Button type="primary" onClick={() => setStep(2)}>
            {t('apiKeyOnboardingWizard.next')}
          </Button>
        </Space>
      )
    }

    if (step === 2) {
      return (
        <Space wrap>
          <Button onClick={() => setStep(3)}>{t('apiKeyOnboardingWizard.manualCopyContinue')}</Button>
          <Button type="primary" icon={<CopyOutlined />} onClick={() => void handleCopyInstall()}>
            {t('apiKeyOnboardingWizard.copyInstall')}
          </Button>
          <Button
            type="primary"
            disabled={!canAdvanceFromStep2(installCopySucceeded)}
            onClick={() => setStep(3)}
          >
            {t('apiKeyOnboardingWizard.next')}
          </Button>
        </Space>
      )
    }

    return (
      <Button type="primary" onClick={handleFinish}>
        {t('apiKeyOnboardingWizard.finish')}
      </Button>
    )
  }

  return (
    <Modal
      open={open}
      title={t(wizardStepTitleKey(step))}
      width={MODAL_WIDTH}
      rootClassName="apikeys-modal apikeys-modal--onboarding apikeys-modal--wizard"
      styles={{ body: { maxWidth: '100%' } }}
      {...API_KEY_ONBOARDING_MODAL_GUARD}
      centered
      zIndex={1200}
      footer={renderFooter()}
    >
      <Steps
        className="ak-wizard-steps"
        current={step - 1}
        size="small"
        items={[
          { title: t('apiKeyOnboardingWizard.step1Label') },
          { title: t('apiKeyOnboardingWizard.step2Label') },
          { title: t('apiKeyOnboardingWizard.step3Label') },
        ]}
      />

      {step === 1 && !created && (
        <>
          <p className="ak-onboarding-intro">{t('apiKeyOnboardingWizard.step1Intro')}</p>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('apiKeys.namePlaceholder')}
            size="large"
            disabled={creating}
            onPressEnter={() => void handleCreate()}
            autoFocus
          />
        </>
      )}

      {step === 1 && created && (
        <div className="ak-result">
          <p className="ak-result-msg">{t('apiKeys.saveKey')}</p>
          <p className="ak-result-key ak-result-key--full">
            <code>{created.plain_text_key}</code>
          </p>
          <p className="ak-result-sub">{t('apiKeys.saveKeySub')}</p>
        </div>
      )}

      {step === 2 && (
        <>
          <p className="ak-onboarding-intro">{t('apiKeyOnboardingWizard.step2Intro')}</p>
          <Input.TextArea
            className="ak-wizard-prompt"
            value={installText}
            readOnly
            autoSize={{ minRows: 8, maxRows: 14 }}
          />
        </>
      )}

      {step === 3 && (
        <p className="ak-onboarding-intro ak-wizard-done">{t('apiKeyOnboardingWizard.step3Intro')}</p>
      )}
    </Modal>
  )
}
