import { Button, Collapse, Segmented, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { AgentRunEvent } from '@/api/agentRuns'
import { formatDate } from '@/utils'
import { eventHasSearchTraceDrill } from '@/utils/agentRunSearchTrace'
import { buildSessionBranches, branchTitle, type SessionBranch } from '@/utils/agentRunSessionTree'

type Props = {
  events: AgentRunEvent[]
  branches?: SessionBranch[]
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

type ViewMode = 'grouped' | 'flat'

export default function AgentRunTimeline({ events, branches: branchesProp, onDrillSearchTrace }: Props) {
  const { t } = useTranslation()
  const branches = useMemo(
    () => branchesProp ?? buildSessionBranches(events),
    [branchesProp, events],
  )
  const canGroup = branches.length > 1
  const [viewMode, setViewMode] = useState<ViewMode>(canGroup ? 'grouped' : 'flat')
  const prevCanGroupRef = useRef(canGroup)

  useEffect(() => {
    if (canGroup && !prevCanGroupRef.current) {
      setViewMode('grouped')
    }
    prevCanGroupRef.current = canGroup
  }, [canGroup])

  const columns: ColumnsType<AgentRunEvent> = useMemo(
    () => [
      {
        title: t('agentRuns.timelineSeq'),
        dataIndex: 'seq',
        width: 64,
      },
      {
        title: t('agentRuns.timelineTime'),
        dataIndex: 'ts',
        width: 180,
        render: (v: string) => formatDate(v),
      },
      {
        title: t('agentRuns.timelineLabel'),
        dataIndex: 'label',
      },
      {
        title: t('agentRuns.timelinePhase'),
        dataIndex: 'phase',
        width: 90,
        render: (v: string) => <Tag color={phaseColor(v)}>{v}</Tag>,
      },
      {
        title: t('agentRuns.timelineDuration'),
        dataIndex: 'duration_ms',
        width: 100,
        render: (v?: number | null) => (v != null ? `${v} ms` : '—'),
      },
      {
        title: t('agentRuns.timelineDrill'),
        key: 'drill',
        width: 96,
        render: (_: unknown, row) =>
          eventHasSearchTraceDrill(row) ? (
            <Button type="link" size="small" onClick={() => onDrillSearchTrace?.(row)}>
              {t('agentRuns.searchTraceDrill')}
            </Button>
          ) : (
            '—'
          ),
      },
    ],
    [onDrillSearchTrace, t],
  )

  const grouped = viewMode === 'grouped' && canGroup
  const branchIds = useMemo(() => branches.map((b) => b.id), [branches])
  const [activeGroupKeys, setActiveGroupKeys] = useState<string[]>([])

  useEffect(() => {
    if (!canGroup) {
      setActiveGroupKeys([])
      return
    }
    setActiveGroupKeys((prev) => {
      const merged = new Set(prev)
      for (const id of branchIds) merged.add(id)
      return [...merged]
    })
  }, [branchIds, canGroup])

  return (
    <section className="agent-run-timeline">
      <div className="agent-run-timeline__head">
        <h3 className="agent-run-section__title">{t('agentRuns.timelineTitle')}</h3>
        {canGroup ? (
          <Segmented<ViewMode>
            size="small"
            aria-label={t('agentRuns.timelineViewMode')}
            options={[
              { label: t('agentRuns.timelineGrouped'), value: 'grouped' },
              { label: t('agentRuns.timelineFlat'), value: 'flat' },
            ]}
            value={viewMode}
            onChange={(value) => setViewMode(value)}
          />
        ) : null}
      </div>
      {grouped ? (
        <Collapse
          className="agent-run-timeline__groups"
          activeKey={activeGroupKeys}
          onChange={(keys) =>
            setActiveGroupKeys(Array.isArray(keys) ? keys : keys != null ? [String(keys)] : [])
          }
          items={branches.map((branch) => ({
            key: branch.id,
            label: branchTitle(branch, t),
            children: (
              <Table<AgentRunEvent>
                size="small"
                rowKey="seq"
                columns={columns}
                dataSource={[...branch.events].sort((a, b) => a.seq - b.seq)}
                pagination={false}
                scroll={{ y: 200 }}
              />
            ),
          }))}
        />
      ) : (
        <Table<AgentRunEvent>
          size="small"
          rowKey="seq"
          columns={columns}
          dataSource={events}
          pagination={false}
          scroll={{ y: 240 }}
        />
      )}
    </section>
  )
}
