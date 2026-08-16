import { Button, Tag } from 'antd'
import { useTranslation } from 'react-i18next'
import type { AgentRunEvent } from '@/api/agentRuns'
import {
  branchDurationMs,
  formatSearchTaskKeyShort,
  searchBranchHitCount,
  type SessionBranch,
} from '@/utils/agentRunSessionTree'
import { eventHasSearchTraceDrill } from '@/utils/agentRunSearchTrace'
import { formatDate } from '@/utils'

type Props = {
  branch: SessionBranch
  onDrillSearchTrace?: (event: AgentRunEvent) => void
}

function phaseColor(phase: string): string {
  switch (phase) {
    case 'start':
      return 'processing'
    case 'end':
      return 'success'
    case 'error':
      return 'error'
    default:
      return 'default'
  }
}

export default function AgentRunSearchBranchCard({ branch, onDrillSearchTrace }: Props) {
  const { t } = useTranslation()
  const taskKey = branch.taskKey ?? ''
  const short = formatSearchTaskKeyShort(taskKey)
  const hits = searchBranchHitCount(branch)
  const duration = branchDurationMs(branch)
  const startEv = branch.events.find((ev) => ev.phase === 'start')
  const endEv = [...branch.events].reverse().find((ev) => ev.phase === 'end')
  const drillEvent = branch.events.find((ev) => eventHasSearchTraceDrill(ev))

  return (
    <article className="agent-run-search-branch-card" aria-label={t('agentRuns.searchBranchCard.title')}>
      <header className="agent-run-search-branch-card__head">
        <h4 className="agent-run-search-branch-card__title">
          {t('agentRuns.searchBranchCard.heading', { short })}
        </h4>
        {branch.status === 'running' ? (
          <Tag color="processing">{t('agentRuns.sessionTree.status.running')}</Tag>
        ) : null}
      </header>
      <dl className="agent-run-search-branch-card__meta">
        {hits != null ? (
          <>
            <dt>{t('agentRuns.searchBranchCard.hits')}</dt>
            <dd>{t('agentRuns.searchTraceHitCount', { count: hits })}</dd>
          </>
        ) : null}
        {duration != null ? (
          <>
            <dt>{t('agentRuns.colDuration')}</dt>
            <dd>{duration < 1000 ? `${duration} ms` : `${(duration / 1000).toFixed(1)} s`}</dd>
          </>
        ) : null}
        {startEv ? (
          <>
            <dt>{t('agentRuns.searchBranchCard.started')}</dt>
            <dd>{formatDate(startEv.ts)}</dd>
          </>
        ) : null}
        {endEv ? (
          <>
            <dt>{t('agentRuns.searchBranchCard.finished')}</dt>
            <dd>{formatDate(endEv.ts)}</dd>
          </>
        ) : null}
        <dt>{t('agentRuns.searchBranchCard.fingerprint')}</dt>
        <dd>
          <code className="agent-run-search-branch-card__fp">{taskKey || short}</code>
        </dd>
        <dt>{t('agentRuns.timelinePhase')}</dt>
        <dd>
          <Tag color={phaseColor(endEv?.phase ?? startEv?.phase ?? 'default')}>
            {endEv?.phase ?? startEv?.phase ?? '—'}
          </Tag>
        </dd>
      </dl>
      {drillEvent && onDrillSearchTrace ? (
        <Button type="link" size="small" onClick={() => onDrillSearchTrace(drillEvent)}>
          {t('agentRuns.searchTraceDrill')}
        </Button>
      ) : null}
    </article>
  )
}
