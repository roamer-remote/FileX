import { Tag } from 'antd'
import { useTranslation } from 'react-i18next'
import type { ModuleHintSummary } from '@/utils/agentRunTopology'

type Props = {
  intent?: string | null
  hints: ModuleHintSummary[]
}

export default function AgentRunModuleHintPanel({ intent, hints }: Props) {
  const { t } = useTranslation()

  if (!intent && hints.length === 0) return null

  return (
    <section className="agent-run-module-hints" aria-label={t('agentRuns.moduleHintTitle')}>
      <h3 className="agent-run-section__title">{t('agentRuns.moduleHintTitle')}</h3>
      {intent ? (
        <p className="agent-run-module-hints__intent">
          {t('agentRuns.moduleHintIntent', { intent })}
        </p>
      ) : null}
      {hints.length === 0 ? (
        <p className="agent-run-module-hints__empty">{t('agentRuns.moduleHintEmpty')}</p>
      ) : (
        <ul className="agent-run-module-hints__list">
          {hints.map((hint, index) => (
            <li key={`${hint.intent ?? 'hint'}-${index}`} className="agent-run-module-hints__item">
              <div className="agent-run-module-hints__item-head">
                {hint.intent ? <Tag>{hint.intent}</Tag> : null}
                {hint.execution_mode ? (
                  <span className="agent-run-module-hints__mode">{hint.execution_mode}</span>
                ) : null}
              </div>
              {hint.reason ? (
                <p className="agent-run-module-hints__reason">{hint.reason}</p>
              ) : null}
              {hint.next_action ? (
                <p className="agent-run-module-hints__next">{hint.next_action}</p>
              ) : null}
              {hint.module_ids?.length ? (
                <p className="agent-run-module-hints__modules">
                  {t('agentRuns.moduleHintModules', { modules: hint.module_ids.join(', ') })}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
