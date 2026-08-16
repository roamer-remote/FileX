import { ApartmentOutlined, SearchOutlined } from '@ant-design/icons'
import { Select, Tag } from 'antd'
import { useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  branchSummary,
  branchTitle,
  type SessionBranch,
  type SessionBranchStatus,
} from '@/utils/agentRunSessionTree'

export type AgentRunSessionTreeProps = {
  questionPreview: string
  branches: SessionBranch[]
  selectedBranchId: string | null
  onSelectBranch: (branchId: string) => void
}

function statusTagColor(status: SessionBranchStatus): string {
  switch (status) {
    case 'running':
      return 'processing'
    case 'done':
      return 'success'
    case 'error':
      return 'error'
    default:
      return 'default'
  }
}

function BranchKindIcon({ kind }: { kind: SessionBranch['kind'] }) {
  if (kind === 'search') {
    return <SearchOutlined aria-hidden className="agent-run-session-tree__kind-icon" />
  }
  return <ApartmentOutlined aria-hidden className="agent-run-session-tree__kind-icon" />
}

export default function AgentRunSessionTree({
  questionPreview,
  branches,
  selectedBranchId,
  onSelectBranch,
}: AgentRunSessionTreeProps) {
  const { t } = useTranslation()

  const options = useMemo(
    () =>
      branches.map((branch) => ({
        value: branch.id,
        label: branchTitle(branch, t),
      })),
    [branches, t],
  )

  const handleBranchKeyDown = useCallback(
    (branchId: string, event: React.KeyboardEvent<HTMLButtonElement>) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        onSelectBranch(branchId)
      }
    },
    [onSelectBranch],
  )

  if (branches.length === 0) return null

  return (
    <nav className="agent-run-session-tree" aria-label={t('agentRuns.sessionTree.ariaLabel')}>
      <div className="agent-run-session-tree__root">
        <span className="agent-run-session-tree__root-label">{t('agentRuns.sessionTree.root')}</span>
        <span className="agent-run-session-tree__root-preview">{questionPreview}</span>
      </div>

      <div className="agent-run-session-tree__select-mobile">
        <Select
          size="small"
          aria-label={t('agentRuns.sessionTree.selectBranch')}
          value={selectedBranchId ?? undefined}
          options={options}
          onChange={(value) => onSelectBranch(value)}
        />
      </div>

      <div className="agent-run-session-tree__branches" role="tablist" aria-label={t('agentRuns.sessionTree.branchList')}>
        {branches.map((branch) => {
          const selected = selectedBranchId === branch.id
          const title = branchTitle(branch, t)
          const summary = branchSummary(branch, t)
          return (
            <button
              key={branch.id}
              type="button"
              role="tab"
              id={`agent-run-branch-tab-${branch.id}`}
              aria-selected={selected}
              tabIndex={selected ? 0 : -1}
              className={
                'agent-run-session-tree__branch' +
                (selected ? ' agent-run-session-tree__branch--selected' : '') +
                (branch.status === 'running' ? ' agent-run-session-tree__branch--running' : '')
              }
              onClick={() => onSelectBranch(branch.id)}
              onKeyDown={(event) => handleBranchKeyDown(branch.id, event)}
            >
              <span className="agent-run-session-tree__branch-head">
                <BranchKindIcon kind={branch.kind} />
                <span className="agent-run-session-tree__branch-title">{title}</span>
              </span>
              <span className="agent-run-session-tree__branch-meta">
                <Tag color={statusTagColor(branch.status)} className="agent-run-session-tree__status">
                  {t(`agentRuns.sessionTree.status.${branch.status}`)}
                </Tag>
                {summary ? <span className="agent-run-session-tree__summary">{summary}</span> : null}
              </span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}

// 兼容旧 import 路径；新代码请从 @/utils/agentRunSessionTree 引入
export { branchSummary, branchTitle } from '@/utils/agentRunSessionTree'
