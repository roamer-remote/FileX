import type { MqUserActiveTask } from '@/api/mq'
import type { MqQueueStatus } from '@/api/admin'
import MqQueueCard, {
  type MainQueueDbSource,
  mqQueueTitle,
  type ADMIN_QUEUE_GROUPS,
  type USER_QUEUE_GROUPS,
} from '@/components/mq/MqQueueCard'

type QueueGroup = (typeof ADMIN_QUEUE_GROUPS)[number] | (typeof USER_QUEUE_GROUPS)[number]

type MqClassicQueueGroupsProps = {
  groups: readonly QueueGroup[]
  sortedQueues: MqQueueStatus[]
  activeTasks: MqUserActiveTask[]
  t: (k: string, opts?: Record<string, unknown>) => string
  mode?: 'admin' | 'user'
  groupsLabel: string
  onViewMessages: (
    queueName: string,
    queueLabel: string,
    queueKey: string,
    dbSource: MainQueueDbSource,
  ) => void
  trailing?: React.ReactNode
}

export default function MqClassicQueueGroups({
  groups,
  sortedQueues,
  activeTasks,
  t,
  mode = 'admin',
  groupsLabel,
  onViewMessages,
  trailing,
}: MqClassicQueueGroupsProps) {
  if (sortedQueues.length === 0) return null

  const queueByLabel = new Map(sortedQueues.map((q) => [q.label, q]))

  return (
    <div className="mq-queue-groups" aria-label={groupsLabel}>
      {groups.map((group) => {
        const groupQueues = group.labels
          .map((label) => queueByLabel.get(label))
          .filter((q): q is MqQueueStatus => !!q)
        if (groupQueues.length === 0) return null
        const gridClass =
          group.key === 'other'
            ? 'mq-queue-group-grid mq-queue-group-grid--cols-4'
            : 'mq-queue-group-grid'
        return (
          <section
            key={group.key}
            className={`mq-queue-group mq-queue-group--${group.key}`}
            aria-label={t(group.titleKey)}
          >
            <h3 className="mq-queue-group-title">{t(group.titleKey)}</h3>
            <div className={gridClass} role="list">
              {groupQueues.map((q) => (
                <MqQueueCard
                  key={q.name}
                  q={q}
                  title={mqQueueTitle(q.label, t)}
                  t={t}
                  mode={mode}
                  activeTasks={activeTasks}
                  onViewMessages={onViewMessages}
                />
              ))}
            </div>
          </section>
        )
      })}
      {trailing}
    </div>
  )
}
