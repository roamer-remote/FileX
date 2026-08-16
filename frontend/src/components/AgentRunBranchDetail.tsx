import AgentRunFlowGraph from '@/components/AgentRunFlowGraph'
import AgentRunSearchBranchCard from '@/components/AgentRunSearchBranchCard'
import type { AgentRunEvent } from '@/api/agentRuns'
import type { SessionBranch } from '@/utils/agentRunSessionTree'

type Props = {
  branch: SessionBranch | null
  running?: boolean
  onDrillSearchTrace?: (event: AgentRunEvent) => void
}

/** FR-110-002 mount gate：search 不 mount FlowGraph */
export default function AgentRunBranchDetail({ branch, running = false, onDrillSearchTrace }: Props) {
  if (!branch) return null
  if (branch.kind === 'search') {
    return <AgentRunSearchBranchCard branch={branch} onDrillSearchTrace={onDrillSearchTrace} />
  }
  return <AgentRunFlowGraph events={branch.events} running={running} />
}
