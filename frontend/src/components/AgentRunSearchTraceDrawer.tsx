import { Drawer, Tag } from 'antd'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { AgentRunEvent } from '@/api/agentRuns'
import {
  buildSearchTraceSteps,
  parseCoverageReceiptTrace,
  parseSearchTraceSummary,
} from '@/utils/agentRunSearchTrace'

type Props = {
  event: AgentRunEvent | null
  open: boolean
  onClose: () => void
}

export default function AgentRunSearchTraceDrawer({ event, open, onClose }: Props) {
  const { t } = useTranslation()
  const summary = useMemo(
    () => parseSearchTraceSummary(event?.meta_json ?? null),
    [event?.meta_json],
  )
  const steps = useMemo(
    () => (summary ? buildSearchTraceSteps(summary, t) : []),
    [summary, t],
  )
  const receipt = useMemo(
    () => parseCoverageReceiptTrace(event?.meta_json ?? null),
    [event?.meta_json],
  )

  return (
    <Drawer
      title={t('agentRuns.searchTraceDrawerTitle')}
      open={open}
      onClose={onClose}
      width={420}
      destroyOnClose
    >
      {event ? (
        <div className="agent-run-search-trace">
          <div className="agent-run-search-trace__head">
            <Tag>{event.label}</Tag>
            <span className="agent-run-search-trace__seq">#{event.seq}</span>
            {summary?.hit_count != null ? (
              <span className="agent-run-search-trace__hits">
                {t('agentRuns.searchTraceHitCount', { count: summary.hit_count })}
              </span>
            ) : null}
          </div>
          {receipt ? (
            <section className="agent-run-search-trace__coverage">
              <div className="agent-run-search-trace__coverage-head">
                <strong>{t('agentRuns.coverageReceiptTitle')}</strong>
                <Tag color={receipt.answerable === false ? 'error' : 'success'}>
                  {receipt.answerable === false
                    ? t('agentRuns.coverageReceiptBlocked')
                    : t('agentRuns.coverageReceiptAnswerable')}
                </Tag>
                {receipt.version ? <span>v{receipt.version.replace(/^v/, '')}</span> : null}
              </div>
              <dl className="agent-run-search-trace__coverage-list">
                <dt>{t('agentRuns.coverageReceiptFiles')}</dt>
                <dd>{receipt.selected_file_ids.length ? receipt.selected_file_ids.join(', ') : '—'}</dd>
                <dt>{t('agentRuns.coverageReceiptFullMd')}</dt>
                <dd>{receipt.full_md_file_ids.length ? receipt.full_md_file_ids.join(', ') : '—'}</dd>
                <dt>{t('agentRuns.coverageReceiptSections')}</dt>
                <dd>
                  {receipt.selected_section_locators.length
                    ? receipt.selected_section_locators.map((locator) => (
                        <div key={`${locator.file_id}-${locator.chunk_id ?? locator.heading_path ?? ''}`}>
                          #{locator.file_id}
                          {locator.chunk_id != null ? ` / #${locator.chunk_id}` : ''}
                          {locator.heading_path ? ` · ${locator.heading_path}` : ''}
                        </div>
                      ))
                    : '—'}
                </dd>
                {receipt.insufficient_reasons.length ? (
                  <>
                    <dt>{t('agentRuns.coverageReceiptReasons')}</dt>
                    <dd>{receipt.insufficient_reasons.join(', ')}</dd>
                  </>
                ) : null}
              </dl>
            </section>
          ) : null}
          {steps.length ? (
            <ol className="agent-run-search-trace__steps">
              {steps.map((step) => (
                <li key={step.id} className="agent-run-search-trace__step">
                  <div className="agent-run-search-trace__step-title">{t(step.labelKey)}</div>
                  {step.detail ? (
                    <div className="agent-run-search-trace__step-detail">{step.detail}</div>
                  ) : null}
                  {step.ms != null ? (
                    <div className="agent-run-search-trace__step-ms">
                      {t('agentRuns.searchTraceStepMs', { ms: step.ms.toFixed(1) })}
                    </div>
                  ) : null}
                </li>
              ))}
            </ol>
          ) : (
            <p className="agent-run-search-trace__empty">{t('agentRuns.searchTraceEmpty')}</p>
          )}
          {summary?.timings_ms && Object.keys(summary.timings_ms).length > 0 ? (
            <details className="agent-run-search-trace__raw">
              <summary>{t('agentRuns.searchTraceTimingsToggle')}</summary>
              <pre>{JSON.stringify(summary.timings_ms, null, 2)}</pre>
            </details>
          ) : null}
        </div>
      ) : null}
    </Drawer>
  )
}
