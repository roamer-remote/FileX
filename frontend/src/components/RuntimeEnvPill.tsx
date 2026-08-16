import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getRuntimeMeta } from '@/api/meta'

type Phase = 'loading' | 'ready' | 'error'

export default function RuntimeEnvPill() {
  const { t } = useTranslation()
  const [phase, setPhase] = useState<Phase>('loading')
  const [rawEnv, setRawEnv] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await getRuntimeMeta()
        if (!cancelled) {
          setRawEnv(res.data.filex_env ?? null)
          setPhase('ready')
        }
      } catch {
        if (!cancelled) setPhase('error')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const trimmed = rawEnv?.trim() ?? ''
  const key = trimmed.toLowerCase()

  let variant: 'prod' | 'dev' | 'other' = 'prod'
  let label: string
  if (phase === 'loading') {
    label = t('appLayout.envLoading')
    variant = 'prod'
  } else if (phase === 'error') {
    label = t('appLayout.envUnavailable')
    variant = 'other'
  } else if (!trimmed) {
    label = t('appLayout.envProduction')
    variant = 'prod'
  } else if (key === 'development') {
    label = t('appLayout.envDevelopment')
    variant = 'dev'
  } else {
    label = t('appLayout.envOther', { value: trimmed })
    variant = 'other'
  }

  return (
    <div className="nav-runtime-env" role="status" aria-live="polite">
      <span className={`nav-runtime-env__pill nav-runtime-env__pill--${variant}`}>{label}</span>
    </div>
  )
}
