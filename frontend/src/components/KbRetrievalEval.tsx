import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { App, Button, Empty, Input, InputNumber, Select, Spin, Switch, Table, Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { getFileById, type FileItem } from '@/api/files'
import {
  searchKnowledgeBase,
  type KbChunkHit,
  type KbSearchMeta,
} from '@/api/knowledgeBase'
import { formatApiError } from '@/api/index'
import { useFilesStore } from '@/stores/filesStore'
import { useSystemSettingsStore } from '@/stores/systemSettingsStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { FlTableMarqueeText } from '@/components/FileListComponents'
import { dedupeKbHitsByFile } from '@/lib/kbEvalDedupe'
import { patchKbEvalUiState } from '@/lib/uiStateSync'
import { useKnowledgePanelToolbarSlot } from '@/contexts/KnowledgePanelToolbarSlotContext'
import '@/components/FileList.css'
import '@/components/knowledge/KnowledgeLobbyToolbar.css'
import './KbRetrievalEval.css'

const KB_CROSS_WS_KEY = 'filex_kb_search_cross_workspace'
const KB_EVAL_FILENAME_BOOST_KEY = 'filex_kb_eval_filename_boost'
const KB_EVAL_MODALITY_BOOST_KEY = 'filex_kb_eval_modality_boost'
const KB_EVAL_HYBRID_KEY = 'filex_kb_eval_hybrid'
const KB_EVAL_QUERY_EXPANSION_KEY = 'filex_kb_eval_query_expansion'
const KB_EVAL_RAPTOR_EXPAND_KEY = 'filex_kb_eval_raptor_expand'
const KB_EVAL_SAG_EXPAND_KEY = 'filex_kb_eval_sag_expand'
const KB_EVAL_SAG_MODE_KEY = 'filex_kb_eval_sag_mode'
const KB_EVAL_SEARCH_TRACE_KEY = 'filex_kb_eval_search_trace'
const KB_EVAL_EVIDENCE_MODE_KEY = 'filex_kb_eval_evidence_mode'
/** 007：评测页默认开文件名加权与混合检索；查询扩展默认关（与 API 一致） */
const KB_EVAL_FILENAME_BOOST_DEFAULT = true
const KB_EVAL_HYBRID_DEFAULT = true
const KB_EVAL_QUERY_EXPANSION_DEFAULT = false
const KB_EVAL_MODALITY_BOOST_DEFAULT = false
const KB_EVAL_TOP_K_MIN = 5
const KB_EVAL_TOP_K_MAX = 50

function clampEvalTopK(n: number): number {
  return Math.min(KB_EVAL_TOP_K_MAX, Math.max(KB_EVAL_TOP_K_MIN, Math.round(n)))
}

function loadBoolPref(key: string, defaultValue = false): boolean {
  try {
    const raw = localStorage.getItem(key)
    if (raw === null) return defaultValue
    return raw === '1'
  } catch {
    return defaultValue
  }
}

type EvidenceMode = 'chunk' | 'monte_carlo'
type SagSearchMode = 'fast' | 'standard'

function loadSagModePref(): SagSearchMode {
  try {
    const raw = localStorage.getItem(KB_EVAL_SAG_MODE_KEY)
    return raw === 'standard' ? 'standard' : 'fast'
  } catch {
    return 'fast'
  }
}

function saveSagModePref(mode: SagSearchMode) {
  try {
    localStorage.setItem(KB_EVAL_SAG_MODE_KEY, mode)
  } catch {
    /* ignore */
  }
  patchKbEvalUiState()
}

function loadEvidenceModePref(): EvidenceMode {
  try {
    const raw = localStorage.getItem(KB_EVAL_EVIDENCE_MODE_KEY)
    return raw === 'monte_carlo' ? 'monte_carlo' : 'chunk'
  } catch {
    return 'chunk'
  }
}

function saveEvidenceModePref(mode: EvidenceMode) {
  try {
    localStorage.setItem(KB_EVAL_EVIDENCE_MODE_KEY, mode)
  } catch {
    /* ignore */
  }
  patchKbEvalUiState()
}

function saveBoolPref(key: string, enabled: boolean) {
  try {
    localStorage.setItem(key, enabled ? '1' : '0')
  } catch {
    /* ignore */
  }
  patchKbEvalUiState()
}

function loadCrossWorkspacePref(): boolean {
  return loadBoolPref(KB_CROSS_WS_KEY, true)
}

function saveCrossWorkspacePref(enabled: boolean) {
  saveBoolPref(KB_CROSS_WS_KEY, enabled)
}

function snippetPreview(text: string, maxLen = 200): string {
  const one = text.replace(/\s+/g, ' ').trim()
  if (one.length <= maxLen) return one
  return `${one.slice(0, maxLen)}…`
}

type Props = {
  files: FileItem[]
  onPreview: (file: FileItem) => void
  /** 大厅顶栏带入的评测查询词 */
  seedQuery?: string
  /** 递增时自动以 seedQuery 执行评测检索（大厅 Enter） */
  seedRunNonce?: number
  /** Drawer 顶栏刷新（与搜索栏同行底对齐） */
  onRefresh?: () => void
}

type EvalRow = KbChunkHit & { rank: number; key: string }

function EvalQueryBar({
  seedQuery,
  loading,
  placeholder,
  runLabel,
  onRun,
}: {
  seedQuery?: string
  loading: boolean
  placeholder: string
  runLabel: string
  onRun: (query: string) => void
}) {
  const [draft, setDraft] = useState('')
  const composingRef = useRef(false)

  useEffect(() => {
    if (seedQuery !== undefined) setDraft(seedQuery)
  }, [seedQuery])

  const submit = useCallback(() => {
    if (composingRef.current) return
    onRun(draft)
  }, [draft, onRun])

  return (
    <div className="knowledge-lobby-google-bar kb-retrieval-eval-query-bar">
      <span className="knowledge-lobby-google-bar__lead" aria-hidden>
        <PlusOutlined />
      </span>
      <Input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onCompositionStart={() => {
          composingRef.current = true
        }}
        onCompositionEnd={(e) => {
          composingRef.current = false
          setDraft(e.currentTarget.value)
        }}
        placeholder={placeholder}
        allowClear
        disabled={loading}
        variant="borderless"
        onPressEnter={submit}
        className="knowledge-lobby-google-bar__input"
        aria-label={runLabel}
      />
      <button
        type="button"
        className="knowledge-lobby-google-bar__ai-chip"
        disabled={loading}
        aria-label={runLabel}
        onClick={submit}
      >
        <SearchOutlined className="knowledge-lobby-google-bar__ai-chip-icon" aria-hidden />
        <span>{runLabel}</span>
      </button>
    </div>
  )
}

export default function KbRetrievalEval({
  files,
  onPreview,
  seedQuery,
  seedRunNonce,
  onRefresh,
}: Props) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const tagFilter = useFilesStore((s) => s.tagFilter)
  const tagFilter2 = useFilesStore((s) => s.tagFilter2)
  const sharedEnabled = useSystemSettingsStore((s) => s.shared_workspaces_enabled ?? true)
  const settingsLoaded = useSystemSettingsStore((s) => s.loaded)
  const settingsRevision = useSystemSettingsStore((s) => s.revision)
  const loadSettings = useSystemSettingsStore((s) => s.load)
  const defaultTopK = useSystemSettingsStore((s) => s.kb_search_default_top_k ?? 8)
  const workspaces = useWorkspaceStore((s) => s.workspaces)
  const crossWorkspaceSearch =
    settingsLoaded && sharedEnabled && workspaces.some((w) => w.kind === 'shared')

  const lastSeedRunRef = useRef(0)

  /** null = 跟随系统参数 kb_search_default_top_k；非 null = Drawer 内临时覆盖 */
  const [topKOverride, setTopKOverride] = useState<number | null>(null)
  const effectiveTopK = useMemo(
    () => clampEvalTopK(topKOverride ?? defaultTopK),
    [topKOverride, defaultTopK],
  )
  const [loading, setLoading] = useState(false)
  const [rows, setRows] = useState<EvalRow[]>([])
  const [searched, setSearched] = useState(false)
  const [crossWorkspace, setCrossWorkspace] = useState(loadCrossWorkspacePref)
  const [filenameBoost, setFilenameBoost] = useState(() =>
    loadBoolPref(KB_EVAL_FILENAME_BOOST_KEY, KB_EVAL_FILENAME_BOOST_DEFAULT),
  )
  const [modalityBoost, setModalityBoost] = useState(() =>
    loadBoolPref(KB_EVAL_MODALITY_BOOST_KEY, KB_EVAL_MODALITY_BOOST_DEFAULT),
  )
  const [hybridOverride, setHybridOverride] = useState(() =>
    loadBoolPref(KB_EVAL_HYBRID_KEY, KB_EVAL_HYBRID_DEFAULT),
  )
  const [queryExpansion, setQueryExpansion] = useState(() =>
    loadBoolPref(KB_EVAL_QUERY_EXPANSION_KEY, KB_EVAL_QUERY_EXPANSION_DEFAULT),
  )
  const [raptorExpand, setRaptorExpand] = useState(() => loadBoolPref(KB_EVAL_RAPTOR_EXPAND_KEY, false))
  const [sagExpand, setSagExpand] = useState(() => loadBoolPref(KB_EVAL_SAG_EXPAND_KEY, false))
  const [sagSearchMode, setSagSearchMode] = useState<SagSearchMode>(() => loadSagModePref())
  const [returnSearchTrace, setReturnSearchTrace] = useState(() =>
    loadBoolPref(KB_EVAL_SEARCH_TRACE_KEY, false),
  )
  const [evidenceMode, setEvidenceMode] = useState<EvidenceMode>(() => loadEvidenceModePref())
  const [searchMeta, setSearchMeta] = useState<KbSearchMeta | null>(null)
  const [embeddingModel, setEmbeddingModel] = useState<string | null>(null)
  const [responseTopK, setResponseTopK] = useState<number | null>(null)

  useEffect(() => {
    void loadSettings()
  }, [loadSettings])

  useEffect(() => {
    const onSettingsChanged = () => {
      void loadSettings()
    }
    window.addEventListener('filex:system-settings-changed', onSettingsChanged)
    return () => window.removeEventListener('filex:system-settings-changed', onSettingsChanged)
  }, [loadSettings])

  useEffect(() => {
    if (!crossWorkspaceSearch) return
    setCrossWorkspace(loadCrossWorkspacePref())
  }, [crossWorkspaceSearch])

  useEffect(() => {
    if (!settingsLoaded || sharedEnabled) return
    setCrossWorkspace(false)
    saveCrossWorkspacePref(false)
  }, [settingsLoaded, sharedEnabled, settingsRevision])

  useEffect(() => {
    if (!settingsLoaded) return
    setTopKOverride(null)
  }, [settingsLoaded, settingsRevision, defaultTopK])

  const runSearch = useCallback(async (queryText: string) => {
    const q = queryText.trim()
    if (!q) {
      message.warning(t('kbSearch.queryRequired'))
      return
    }
    setLoading(true)
    setSearched(true)
    try {
      const res = await searchKnowledgeBase({
        query: q,
        top_k: effectiveTopK,
        tags: tagFilter ? [tagFilter] : undefined,
        group_by_file: true,
        source_files_only: true,
        context_chunks: 0,
        cross_workspace: crossWorkspaceSearch && crossWorkspace ? true : undefined,
        debug: true,
        filename_boost: filenameBoost,
        modality_boost: modalityBoost,
        hybrid: hybridOverride,
        query_expansion: queryExpansion,
        evidence_mode: evidenceMode,
        raptor_expand: raptorExpand,
        expand_sag_events: sagExpand,
        sag_search_mode: sagSearchMode,
        return_search_trace: returnSearchTrace || sagExpand,
      })
      const uniqueHits = dedupeKbHitsByFile(res.items, effectiveTopK)
      const nextRows: EvalRow[] = uniqueHits.map((hit, i) => ({
        ...hit,
        rank: i + 1,
        key: `${hit.file_id}-${hit.chunk_id ?? hit.chunk_index}`,
      }))
      setRows(nextRows)
      setSearchMeta(res.meta ?? null)
      setEmbeddingModel(res.embedding_model)
      setResponseTopK(res.top_k)
    } catch (e) {
      message.error(formatApiError(e))
      setRows([])
      setSearchMeta(null)
      setEmbeddingModel(null)
      setResponseTopK(null)
    } finally {
      setLoading(false)
    }
  }, [
    effectiveTopK,
    tagFilter,
    crossWorkspaceSearch,
    crossWorkspace,
    filenameBoost,
    modalityBoost,
    hybridOverride,
    queryExpansion,
    raptorExpand,
    sagExpand,
    sagSearchMode,
    returnSearchTrace,
    evidenceMode,
    message,
    t,
  ])

  useEffect(() => {
    if (!seedRunNonce || seedRunNonce === lastSeedRunRef.current) return
    if (!settingsLoaded) return
    lastSeedRunRef.current = seedRunNonce
    const q = (seedQuery ?? '').trim()
    if (!q) return
    void runSearch(q)
  }, [seedRunNonce, seedQuery, runSearch, settingsLoaded])

  const openHit = useCallback(
    async (hit: KbChunkHit) => {
      try {
        let file = files.find((f) => f.id === hit.file_id)
        if (!file) {
          const res = await getFileById(hit.file_id)
          file = res.data
        }
        onPreview(file)
      } catch {
        message.error(t('kbSearch.fileOpenFailed'))
      }
    },
    [files, onPreview, message, t],
  )

  const formatPct = (v: number | undefined | null) =>
    v == null ? '—' : `${(v * 100).toFixed(1)}%`

  const columns = useMemo<ColumnsType<EvalRow>>(
    () => [
      {
        title: t('kbRetrievalEval.colRank'),
        dataIndex: 'rank',
        width: 56,
        fixed: 'left',
      },
      {
        title: t('kbRetrievalEval.colFile'),
        dataIndex: 'original_name',
        width: 160,
        render: (name: string, row) => (
          <button
            type="button"
            className="kb-eval-file-link"
            onClick={() => void openHit(row)}
          >
            <FlTableMarqueeText text={name} />
          </button>
        ),
      },
      {
        title: t('kbRetrievalEval.colChunk'),
        width: 100,
        render: (_: unknown, row) =>
          row.chunk_id != null ? `#${row.chunk_id} · ${row.chunk_index}` : String(row.chunk_index),
      },
      {
        title: t('kbRetrievalEval.colScore'),
        dataIndex: 'score',
        width: 88,
        render: (v: number) => formatPct(v),
      },
      {
        title: t('kbRetrievalEval.colBaseScore'),
        dataIndex: 'base_score',
        width: 88,
        render: (v: number | undefined) => formatPct(v),
      },
      {
        title: t('kbRetrievalEval.colFilenameBoost'),
        dataIndex: 'filename_boost',
        width: 88,
        render: (v: number | undefined) => formatPct(v),
      },
      {
        title: t('kbRetrievalEval.colModalityBoost'),
        dataIndex: 'modality_boost',
        width: 88,
        render: (v: number | undefined) => formatPct(v),
      },
      {
        title: t('kbRetrievalEval.colContentKind'),
        dataIndex: 'content_kind',
        width: 88,
        render: (v: string | null | undefined) => v || '—',
      },
      {
        title: t('kbRetrievalEval.colKeywordBoost'),
        dataIndex: 'keyword_boost',
        width: 88,
        render: (v: number | undefined) => formatPct(v),
      },
      {
        title: t('kbRetrievalEval.colVector'),
        dataIndex: 'vector_score',
        width: 88,
        render: (v: number | undefined) => formatPct(v),
      },
      {
        title: t('kbRetrievalEval.colRerank'),
        dataIndex: 'rerank_score',
        width: 88,
        render: (v: number | undefined) => formatPct(v),
      },
      {
        title: t('kbRetrievalEval.colHeading'),
        dataIndex: 'heading_path',
        width: 140,
        ellipsis: true,
        render: (v: string | null | undefined) => v || '—',
      },
      {
        title: t('kbRetrievalEval.colPreview'),
        dataIndex: 'text',
        width: 320,
        ellipsis: true,
        render: (text: string, row) => (
          <span className="kb-eval-preview" title={row.context_text || text}>
            {snippetPreview(row.context_text || text)}
          </span>
        ),
      },
    ],
    [t, openHit],
  )

  const toolbarSlot = useKnowledgePanelToolbarSlot()

  const toolbarNode = (
    <div className="kb-retrieval-eval-toolbar">
      <div className="kb-retrieval-eval-toolbar-search">
        <EvalQueryBar
          seedQuery={seedQuery}
          loading={loading}
          placeholder={t('kbRetrievalEval.queryPlaceholder')}
          runLabel={t('kbRetrievalEval.run')}
          onRun={(q) => void runSearch(q)}
        />
        <label className="kb-retrieval-eval-topk">
          <span>{t('kbRetrievalEval.topK')}</span>
          <InputNumber
            size="small"
            min={5}
            max={50}
            step={5}
            value={effectiveTopK}
            disabled={loading}
            onChange={(v) =>
              setTopKOverride(typeof v === 'number' ? clampEvalTopK(v) : null)
            }
          />
        </label>
        {onRefresh ? (
          <Button
            type="text"
            size="small"
            className="kb-retrieval-eval-refresh"
            icon={<ReloadOutlined aria-hidden />}
            aria-label={t('knowledge.refresh')}
            onClick={onRefresh}
          />
        ) : null}
      </div>
      <div className="kb-retrieval-eval-toolbar-switches">
        <label className="kb-retrieval-eval-switch">
          <Switch
            size="small"
            checked={modalityBoost}
            onChange={(checked) => {
              setModalityBoost(checked)
              saveBoolPref(KB_EVAL_MODALITY_BOOST_KEY, checked)
            }}
          />
          <Tooltip title={t('kbRetrievalEval.modalityBoostSwitchHint')}>
            <span>{t('kbRetrievalEval.modalityBoostSwitch')}</span>
          </Tooltip>
        </label>
        <label className="kb-retrieval-eval-switch">
          <Switch
            size="small"
            checked={filenameBoost}
            onChange={(checked) => {
              setFilenameBoost(checked)
              saveBoolPref(KB_EVAL_FILENAME_BOOST_KEY, checked)
            }}
          />
          <span>{t('kbRetrievalEval.filenameBoostSwitch')}</span>
        </label>
        <label className="kb-retrieval-eval-switch">
          <Switch
            size="small"
            checked={hybridOverride}
            onChange={(checked) => {
              setHybridOverride(checked)
              saveBoolPref(KB_EVAL_HYBRID_KEY, checked)
            }}
          />
          <span>{t('kbRetrievalEval.hybridSwitch')}</span>
        </label>
        <label className="kb-retrieval-eval-switch">
          <Switch
            size="small"
            checked={queryExpansion}
            onChange={(checked) => {
              setQueryExpansion(checked)
              saveBoolPref(KB_EVAL_QUERY_EXPANSION_KEY, checked)
            }}
          />
          <span>{t('kbRetrievalEval.queryExpansionSwitch')}</span>
        </label>
        <label className="kb-retrieval-eval-switch">
          <Switch
            size="small"
            checked={raptorExpand}
            onChange={(checked) => {
              setRaptorExpand(checked)
              saveBoolPref(KB_EVAL_RAPTOR_EXPAND_KEY, checked)
            }}
          />
          <span>{t('kbRetrievalEval.raptorExpandSwitch')}</span>
        </label>
        <label className="kb-retrieval-eval-switch">
          <Switch
            size="small"
            checked={sagExpand}
            onChange={(checked) => {
              setSagExpand(checked)
              saveBoolPref(KB_EVAL_SAG_EXPAND_KEY, checked)
            }}
          />
          <span>{t('kbRetrievalEval.sagExpandSwitch')}</span>
        </label>
        {sagExpand ? (
          <label className="kb-retrieval-eval-switch kb-retrieval-eval-evidence">
            <span>{t('kbRetrievalEval.sagModeSwitch')}</span>
            <Select<SagSearchMode>
              size="small"
              value={sagSearchMode}
              disabled={loading}
              style={{ minWidth: 96 }}
              options={[
                { value: 'fast', label: t('kbRetrievalEval.sagModeFast') },
                { value: 'standard', label: t('kbRetrievalEval.sagModeStandard') },
              ]}
              onChange={(mode) => {
                const next = mode ?? 'fast'
                setSagSearchMode(next)
                saveSagModePref(next)
              }}
            />
          </label>
        ) : null}
        <label className="kb-retrieval-eval-switch">
          <Switch
            size="small"
            checked={returnSearchTrace}
            onChange={(checked) => {
              setReturnSearchTrace(checked)
              saveBoolPref(KB_EVAL_SEARCH_TRACE_KEY, checked)
            }}
          />
          <span>{t('kbRetrievalEval.searchTraceSwitch')}</span>
        </label>
        <label className="kb-retrieval-eval-switch kb-retrieval-eval-evidence">
          <span>{t('kbRetrievalEval.evidenceModeSwitch')}</span>
          <Select<EvidenceMode>
            size="small"
            value={evidenceMode}
            disabled={loading}
            style={{ minWidth: 120 }}
            options={[
              { value: 'chunk', label: t('kbRetrievalEval.evidenceModeChunk') },
              { value: 'monte_carlo', label: t('kbRetrievalEval.evidenceModeMonteCarlo') },
            ]}
            onChange={(mode) => {
              const next = mode ?? 'chunk'
              setEvidenceMode(next)
              saveEvidenceModePref(next)
            }}
          />
        </label>
        {crossWorkspaceSearch ? (
          <label className="kb-retrieval-eval-switch">
            <Switch
              size="small"
              checked={crossWorkspace}
              onChange={(checked) => {
                setCrossWorkspace(checked)
                saveCrossWorkspacePref(checked)
              }}
            />
            <span>{t('kbSearch.crossWorkspaceSwitch')}</span>
          </label>
        ) : null}
        {tagFilter ? (
          <Tag color="processing">
            {tagFilter2
              ? t('kbSearch.tagFilterDualHint', { tag: tagFilter, tag2: tagFilter2 })
              : t('kbSearch.tagFilterHint', { tag: tagFilter })}
          </Tag>
        ) : null}
      </div>
    </div>
  )


  return (
    <div className="kb-retrieval-eval">
      {toolbarSlot ? createPortal(toolbarNode, toolbarSlot) : toolbarNode}
      {searchMeta || embeddingModel ? (
        <div className="kb-retrieval-eval-meta">
          {embeddingModel ? (
            <span>
              {t('kbRetrievalEval.metaModel', {
                model: embeddingModel,
                topK: responseTopK ?? effectiveTopK,
              })}
            </span>
          ) : null}
          {searchMeta ? (
            <span>
              {t('kbRetrievalEval.debugMetaExtended', {
                hybrid: searchMeta.effective_hybrid ?? searchMeta.hybrid_enabled ? 'on' : 'off',
                fts: searchMeta.effective_fts_config ?? '—',
                filenameBoost: searchMeta.filename_boost_enabled ? 'on' : 'off',
                modalityBoost: searchMeta.modality_boost_enabled ? 'on' : 'off',
                modalityIntent: searchMeta.modality_intent?.length
                  ? searchMeta.modality_intent.join('、')
                  : '—',
                queryExpansion: searchMeta.query_expansion_enabled ? 'on' : 'off',
                expandedTerms: searchMeta.expanded_terms?.length
                  ? searchMeta.expanded_terms.join('、')
                  : '—',
                rerank: searchMeta.rerank_applied ? 'on' : 'off',
              })}
              {searchMeta.cache_hit != null ? (
                <>
                  {' · '}
                  {t('kbRetrievalEval.metaCacheHit', {
                    hit: searchMeta.cache_hit ? 'yes' : 'no',
                    sim:
                      searchMeta.cache_similarity != null
                        ? `${(searchMeta.cache_similarity * 100).toFixed(1)}%`
                        : '—',
                  })}
                </>
              ) : null}
              {searchMeta.monte_carlo_sample_count != null ? (
                <>
                  {' · '}
                  {t('kbRetrievalEval.metaMonteCarlo', {
                    count: searchMeta.monte_carlo_sample_count,
                  })}
                </>
              ) : null}
              {searchMeta.raptor_expanded ? (
                <>
                  {' · '}
                  {t('kbRetrievalEval.metaRaptorExpand', {
                    count: searchMeta.raptor_added_hits ?? 0,
                  })}
                </>
              ) : null}
              {searchMeta.sag_expanded ? (
                <>
                  {' · '}
                  {t('kbRetrievalEval.metaSagExpand', {
                    count: searchMeta.sag_added_hits ?? 0,
                    mode: searchMeta.sag_mode_effective ?? searchMeta.sag_mode_requested ?? 'fast',
                    degraded: searchMeta.sag_mode_degraded ? 'yes' : 'no',
                  })}
                </>
              ) : null}
              {searchMeta.debug_funnel ? (
                <>
                  {' · '}
                  {t('kbRetrievalEval.debugFunnel', {
                    vector: searchMeta.debug_funnel.vector_candidates,
                    fts: searchMeta.debug_funnel.fts_candidates,
                    merged: searchMeta.debug_funnel.merged_unique,
                    acl: searchMeta.debug_funnel.after_acl_filter,
                    minScore: searchMeta.debug_funnel.after_min_score,
                    rerank: searchMeta.debug_funnel.after_rerank,
                    mmr: searchMeta.debug_funnel.after_mmr,
                    filenameBoost: searchMeta.debug_funnel.filename_boost_applied,
                  })}
                </>
              ) : null}
            </span>
          ) : null}
        </div>
      ) : null}

      {searchMeta?.search_trace ? (
        <pre className="kb-retrieval-eval-trace">
          {JSON.stringify(searchMeta.search_trace, null, 2)}
        </pre>
      ) : null}

      <div className="kb-retrieval-eval-table-wrap">
        {loading ? (
          <div className="kb-retrieval-eval-loading">
            <Spin />
          </div>
        ) : !searched ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('kbRetrievalEval.emptyBeforeSearch')} />
        ) : rows.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('kbSearch.noResults')} />
        ) : (
          <Table<EvalRow>
            size="small"
            columns={columns}
            dataSource={rows}
            pagination={false}
            scroll={{ x: 1400, y: 'calc(100vh - 240px)' }}
          />
        )}
      </div>
    </div>
  )
}
