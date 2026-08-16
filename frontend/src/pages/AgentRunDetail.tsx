import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { App, Button, Spin, Tag } from 'antd'
import { ArrowLeftOutlined, ReloadOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import {
  getAgentRun,
  getAgentRunEventsDelta,
  type AgentRunDetailResponse,
  type AgentRunEvent,
} from '@/api/agentRuns'
import AgentRunBranchDetail from '@/components/AgentRunBranchDetail'
import AgentRunModuleHintPanel from '@/components/AgentRunModuleHintPanel'
import AgentRunSearchTraceDrawer from '@/components/AgentRunSearchTraceDrawer'
import AgentRunSessionTree from '@/components/AgentRunSessionTree'
import AgentRunTimeline from '@/components/AgentRunTimeline'
import { fetchEventSource } from '@/lib/fetchEventSource'
import { formatDate } from '@/utils'
import { extractModuleHints, resolveAgentRunViewMode } from '@/utils/agentRunTopology'
import {
  branchDetailSectionTitle,
  buildSessionBranches,
  pickDefaultBranchId,
  resolveSessionViewMode,
  searchBranches,
  shouldShowSessionTreeChrome,
} from '@/utils/agentRunSessionTree'
import '@/pages/admin/AdminPage.css'
import './AgentRunPages.css'

const POLL_MS = 2000

function statusColor(status: string): string {
  switch (status) {
    case 'running':
      return 'processing'
    case 'completed':
      return 'success'
    case 'failed':
      return 'error'
    default:
      return 'default'
  }
}

export default function AgentRunDetailPage() {
  const { runId } = useParams<{ runId: string }>()
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [data, setData] = useState<AgentRunDetailResponse | null>(null)
  const [events, setEvents] = useState<AgentRunEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [live, setLive] = useState(false)
  const [traceEvent, setTraceEvent] = useState<AgentRunEvent | null>(null)
  const [userBranchId, setUserBranchId] = useState<string | null>(null)
  const latestSeqRef = useRef(0)

  const running = live || data?.status === 'running'

  const branches = useMemo(() => buildSessionBranches(events, running), [events, running])
  const sessionViewMode = resolveSessionViewMode(branches)
  const showTreeChrome = shouldShowSessionTreeChrome(sessionViewMode, branches.length)
  const selectedBranchId = useMemo(
    () => pickDefaultBranchId(branches, userBranchId),
    [branches, userBranchId],
  )
  const selectedBranch = useMemo(
    () => branches.find((b) => b.id === selectedBranchId) ?? null,
    [branches, selectedBranchId],
  )
  const displayBranch = selectedBranch ?? (branches.length === 1 ? branches[0] ?? null : null)

  const showModuleHint =
    searchBranches(branches).length === 0 &&
    displayBranch != null &&
    resolveAgentRunViewMode(displayBranch.events) === 'router_only'

  const mergeEvents = useCallback((incoming: AgentRunEvent[]) => {
    if (!incoming.length) return
    setEvents((prev) => {
      const map = new Map(prev.map((e) => [e.seq, e]))
      for (const ev of incoming) map.set(ev.seq, ev)
      const merged = [...map.values()].sort((a, b) => a.seq - b.seq)
      latestSeqRef.current = merged[merged.length - 1]?.seq ?? latestSeqRef.current
      return merged
    })
  }, [])

  const loadSnapshot = useCallback(async () => {
    if (!runId) return
    setLoading(true)
    try {
      const res = await getAgentRun(runId)
      setData(res.data)
      setEvents(res.data.events)
      const evs = res.data.events
      latestSeqRef.current = evs.length ? evs[evs.length - 1].seq : 0
      setLive(res.data.status === 'running')
    } catch (e) {
      message.error(String(e))
    } finally {
      setLoading(false)
    }
  }, [message, runId])

  useEffect(() => {
    void loadSnapshot()
  }, [loadSnapshot])

  useEffect(() => {
    if (!runId || !live) return

    let cancelled = false
    let pollTimer: number | undefined

    const startPoll = () => {
      pollTimer = window.setInterval(() => {
        void (async () => {
          try {
            const res = await getAgentRunEventsDelta(runId, latestSeqRef.current)
            mergeEvents(res.data.events)
            if (res.data.run_status !== 'running') {
              setLive(false)
              setData((d) => (d ? { ...d, status: res.data.run_status } : d))
            }
          } catch {
            /* ignore transient poll errors */
          }
        })()
      }, POLL_MS)
    }

    const ac = new AbortController()
    const prefersReduced =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches

    void (async () => {
      if (prefersReduced) {
        startPoll()
        return
      }
      try {
        await fetchEventSource(
          `/api/agent-runs/${runId}/stream`,
          {
            onEvent: (payload) => {
              const body = payload as { type?: string; event?: AgentRunEvent; status?: string }
              if (body.type === 'event' && body.event) mergeEvents([body.event])
              if (body.type === 'run_status' && body.status) {
                setData((d) => (d ? { ...d, status: body.status! } : d))
                setLive(false)
              }
            },
            onClose: () => setLive(false),
            onError: () => {
              if (!cancelled) startPoll()
            },
          },
          ac.signal,
        )
      } catch {
        if (!cancelled) startPoll()
      }
    })()

    return () => {
      cancelled = true
      ac.abort()
      if (pollTimer) window.clearInterval(pollTimer)
    }
  }, [live, mergeEvents, runId])

  if (!runId) return null

  const moduleHints = extractModuleHints(data?.summary_json)
  const branchSectionTitle = branchDetailSectionTitle(sessionViewMode, t)

  return (
    <div className="admin-root agent-run-root">
      <div className="admin-panel agent-run-panel">
        <header className="admin-header agent-run-panel__header agent-run-panel__header--detail">
          <button
            type="button"
            className="ah-back"
            onClick={() => navigate('/agent/runs')}
          >
            <ArrowLeftOutlined aria-hidden />
            {t('agentRuns.backToList')}
          </button>
          <div className="ah-title-group agent-run-detail-title">
            <div className="agent-run-detail-title-row">
              <h2 className="ah-title">
                {data?.question_preview || t('agentRuns.untitledRun')}
              </h2>
              {data ? (
                <div className="agent-run-detail-meta">
                  <Tag color={statusColor(data.status)}>{data.status}</Tag>
                  <span className="agent-run-detail-meta__item">{formatDate(data.started_at)}</span>
                  {data.duration_ms != null ? (
                    <span className="agent-run-detail-meta__item">
                      {(data.duration_ms / 1000).toFixed(1)}s
                    </span>
                  ) : null}
                  {data.thread_id ? (
                    <span className="agent-run-detail-meta__item agent-run-detail-meta__thread">
                      {data.thread_id}
                    </span>
                  ) : null}
                </div>
              ) : null}
            </div>
            <div className="ah-title-actions">
              <Button
                type="primary"
                size="small"
                icon={<ReloadOutlined spin={loading} />}
                disabled={!data}
                onClick={() => void loadSnapshot()}
              >
                {t('agentRuns.refresh')}
              </Button>
            </div>
          </div>
        </header>

        <Spin spinning={loading && !data} wrapperClassName="agent-run-body-spin">
          <div className="agent-run-body">
            {data ? (
              <>
                {showTreeChrome ? (
                  <AgentRunSessionTree
                    questionPreview={data.question_preview}
                    branches={branches}
                    selectedBranchId={selectedBranchId}
                    onSelectBranch={setUserBranchId}
                  />
                ) : null}
                <section className="agent-run-section" aria-label={branchSectionTitle}>
                  <h3 className="agent-run-section__title">{branchSectionTitle}</h3>
                  <AgentRunBranchDetail
                    branch={displayBranch}
                    running={running}
                    onDrillSearchTrace={(event) => setTraceEvent(event)}
                  />
                </section>
                {showModuleHint ? (
                  <AgentRunModuleHintPanel intent={data.intent} hints={moduleHints} />
                ) : null}
                <AgentRunTimeline
                  events={events}
                  branches={branches}
                  onDrillSearchTrace={(event) => setTraceEvent(event)}
                />
                <AgentRunSearchTraceDrawer
                  event={traceEvent}
                  open={traceEvent != null}
                  onClose={() => setTraceEvent(null)}
                />
              </>
            ) : null}
          </div>
        </Spin>
      </div>
    </div>
  )
}
