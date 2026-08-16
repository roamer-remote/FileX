import { useEffect, useMemo, useState } from 'react'
import { Alert, App, Button, Card, Empty, Input, InputNumber, Select, Space, Spin, Tabs, Tag, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import {
  getQualityWorkbench,
  getQualityWorkbenchOptions,
  listKnowledgeBaseFileChunks,
  patchKnowledgeBaseChunk,
  searchKnowledgeBase,
  type KbChunkDetail,
  type KbSearchResponse,
  type QualityProjectionState,
  type QualityWorkbenchOptionsResponse,
  type QualityWorkbenchResponse,
} from '@/api/knowledgeBase'
import { buildKbChunkPatchPayload } from '@/lib/kbChunkPatchPayload'
import './AdminPage.css'
import './QualityWorkbench.css'

const PROJECTION_NAMES = ['extraction', 'retrieval', 'evidence', 'answer'] as const
type ProjectionName = (typeof PROJECTION_NAMES)[number]
const VERSION_NAMES = ['parser_version', 'model_version', 'chunk_version', 'index_version', 'schema_version'] as const
const CHUNK_PAGE_SIZE = 100

const SAFE_DATA_KEYS = new Set([
  'file_id',
  'job_id',
  'trace_id',
  'schema_version',
  'status',
  'status_reason',
  'provider',
  'engine',
  'duration_ms',
  'degradation_reason',
  'counts',
  'final_results',
  'vector_candidates',
  'fts_candidates',
  'merged_unique',
  'after_acl_filter',
  'after_rerank',
  'after_mmr',
  'chunk_ids',
  'file_ids',
  'selected_file_ids',
  'covered_file_ids',
  'source_locations',
  'chunk_id',
  'file_id',
  'chunk_index',
  'heading_path',
  'block_type',
  'content_kind',
  'loc_type',
  'loc_start',
  'loc_end',
  'loc_label',
  'dimensions',
  'id',
  'type',
  'reason_codes',
  'version',
  'router_kind',
  'missing_evidence',
  'final_file_ids',
  'final_chunk_ids',
  'coverage',
  'negative_gate',
  'answerable',
  'confidence',
])

export function safeQualityData(data: Record<string, unknown> | null | undefined): Record<string, unknown> | null {
  if (!data) return null
  const sanitize = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(sanitize)
    if (!value || typeof value !== 'object') return value
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([key]) => SAFE_DATA_KEYS.has(key))
        .map(([key, nested]) => [key, sanitize(nested)]),
    )
  }
  return sanitize(data) as Record<string, unknown>
}

function stateColor(state: QualityProjectionState): string {
  if (state === 'present') return 'success'
  if (state === 'partial') return 'warning'
  if (state === 'forbidden') return 'error'
  return 'default'
}

function ProjectionCard({
  name,
  projection,
  t,
}: {
  name: ProjectionName
  projection: QualityWorkbenchResponse['extraction']
  t: TFunction
}) {
  const data = safeQualityData(projection.data)
  const emptyMessage = t(`admin.qualityWorkbench.stateMessages.${projection.state}`)
  return (
    <Card
      size="small"
      className="quality-workbench-card"
      title={t(`admin.qualityWorkbench.sections.${name}`)}
      extra={<Tag color={stateColor(projection.state)}>{t(`admin.qualityWorkbench.states.${projection.state}`)}</Tag>}
    >
      {data && Object.keys(data).length > 0 ? (
        <pre className="quality-workbench-data">
          {JSON.stringify(data, null, 2)}
        </pre>
      ) : (
        <Typography.Text type="secondary">{emptyMessage}</Typography.Text>
      )}
    </Card>
  )
}

export default function QualityWorkbenchPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { message } = App.useApp()
  const { t } = useTranslation()
  const [fileIdInput, setFileIdInput] = useState<number | null>(() => {
    const raw = Number(searchParams.get('file_id'))
    return Number.isInteger(raw) && raw > 0 ? raw : null
  })
  const [jobIdInput, setJobIdInput] = useState<number | null>(null)
  const [traceIdInput, setTraceIdInput] = useState('')
  const [queryInput, setQueryInput] = useState('')
  const [data, setData] = useState<QualityWorkbenchResponse | null>(null)
  const [options, setOptions] = useState<QualityWorkbenchOptionsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [optionsLoading, setOptionsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [optionsError, setOptionsError] = useState<string | null>(null)
  const [chunks, setChunks] = useState<KbChunkDetail[]>([])
  const [chunksLoading, setChunksLoading] = useState(false)
  const [chunksError, setChunksError] = useState<string | null>(null)
  const [chunkPage, setChunkPage] = useState(1)
  const [chunksTotal, setChunksTotal] = useState(0)
  const [selectedChunkId, setSelectedChunkId] = useState<number | null>(null)
  const [editText, setEditText] = useState('')
  const [editBoost, setEditBoost] = useState('')
  const [savingChunk, setSavingChunk] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResult, setSearchResult] = useState<KbSearchResponse | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  const fileId = useMemo(() => {
    const raw = Number(searchParams.get('file_id'))
    return Number.isInteger(raw) && raw > 0 ? raw : null
  }, [searchParams])

  useEffect(() => {
    const rawJobId = Number(searchParams.get('job_id'))
    setJobIdInput(Number.isInteger(rawJobId) && rawJobId > 0 ? rawJobId : null)
    setTraceIdInput(searchParams.get('trace_id') || '')
    setQueryInput(searchParams.get('query') || '')
  }, [searchParams])

  useEffect(() => {
    if (fileId == null) {
      setOptions(null)
      setOptionsError(null)
      return
    }
    let active = true
    setOptions(null)
    setOptionsLoading(true)
    setOptionsError(null)
    void getQualityWorkbenchOptions(fileId)
      .then((next) => {
        if (active) setOptions(next)
      })
      .catch((cause: unknown) => {
        if (!active) return
        const detail = cause instanceof Error ? cause.message : t('admin.qualityWorkbench.requestFailed')
        setOptionsError(detail)
      })
      .finally(() => {
        if (active) setOptionsLoading(false)
      })
    return () => {
      active = false
    }
  }, [fileId, t])

  const selectedJob = options?.jobs.find((job) => job.job_id === jobIdInput) ?? null
  const traceOptions = selectedJob?.traces ?? []
  const selectedChunk = chunks.find((chunk) => chunk.id === selectedChunkId) ?? null

  useEffect(() => {
    setEditText(selectedChunk?.text ?? '')
    setEditBoost(selectedChunk?.boost_keywords ?? '')
  }, [selectedChunk])

  useEffect(() => {
    if (!options || jobIdInput == null) return
    if (!selectedJob) {
      setJobIdInput(null)
      setTraceIdInput('')
      return
    }
    if (traceIdInput && !traceOptions.some((trace) => trace.trace_id === traceIdInput)) {
      setTraceIdInput('')
    }
  }, [jobIdInput, options, selectedJob, traceIdInput, traceOptions])

  useEffect(() => {
    if (fileId == null) {
      setData(null)
      setSearchResult(null)
      setSearchError(null)
      setSearchQuery('')
      return
    }
    setData(null)
    setSearchResult(null)
    setSearchError(null)
    setSearchQuery('')
    setLoading(true)
    setError(null)
    void getQualityWorkbench({
      file_id: fileId,
      job_id: Number(searchParams.get('job_id')) || undefined,
      trace_id: searchParams.get('trace_id') || undefined,
      query: searchParams.get('query') || undefined,
    })
      .then(setData)
      .catch((cause: unknown) => {
        const detail = cause instanceof Error ? cause.message : t('admin.qualityWorkbench.requestFailed')
        setError(detail)
        message.error(detail)
      })
      .finally(() => setLoading(false))
  }, [fileId, message, searchParams, t])

  useEffect(() => {
    if (fileId == null) {
      setChunks([])
      setSelectedChunkId(null)
      setChunksError(null)
      setChunkPage(1)
      setChunksTotal(0)
      return
    }
    let active = true
    setChunks([])
    setSelectedChunkId(null)
    setChunkPage(1)
    setChunksTotal(0)
    setChunksLoading(true)
    setChunksError(null)
    void listKnowledgeBaseFileChunks(fileId, { page: 1, page_size: CHUNK_PAGE_SIZE })
      .then((response) => {
        if (!active) return
        setChunks(response.items)
        setSelectedChunkId(response.items[0]?.id ?? null)
        setChunkPage(response.page)
        setChunksTotal(response.total)
      })
      .catch((cause: unknown) => {
        if (!active) return
        const detail = cause instanceof Error ? cause.message : t('admin.qualityWorkbench.requestFailed')
        setChunksError(detail)
        setChunks([])
        setSelectedChunkId(null)
      })
      .finally(() => {
        if (active) setChunksLoading(false)
      })
    return () => {
      active = false
    }
  }, [fileId, t])

  const load = () => {
    if (fileIdInput == null || !Number.isInteger(fileIdInput) || fileIdInput <= 0) return
    const next: Record<string, string> = { file_id: String(fileIdInput) }
    if (jobIdInput && Number.isInteger(jobIdInput)) next.job_id = String(jobIdInput)
    if (traceIdInput.trim()) next.trace_id = traceIdInput.trim()
    if (queryInput.trim()) next.query = queryInput.trim()
    setSearchParams(next)
  }

  const saveChunkCorrection = async () => {
    if (fileId == null || selectedChunk == null) return
    const built = buildKbChunkPatchPayload({
      originalText: selectedChunk.text,
      editText,
      originalBoost: selectedChunk.boost_keywords,
      editBoost,
    })
    if (built.changed && 'error' in built) {
      message.error(t('admin.qualityWorkbench.emptyChunkText'))
      return
    }
    if (!built.changed) {
      message.info(t('admin.qualityWorkbench.noChunkChanges'))
      return
    }
    setSavingChunk(true)
    try {
      const result = await patchKnowledgeBaseChunk(fileId, selectedChunk.id, built.patch)
      setChunks((current) => current.map((chunk) => (
        chunk.id === selectedChunk.id
          ? { ...chunk, text: result.text, boost_keywords: result.boost_keywords ?? null }
          : chunk
      )))
      message.success(t('admin.qualityWorkbench.chunkSaved'))
    } catch (cause: unknown) {
      const detail = cause instanceof Error ? cause.message : t('admin.qualityWorkbench.requestFailed')
      message.error(detail)
    } finally {
      setSavingChunk(false)
    }
  }

  const runRetrievalTest = async () => {
    if (fileId == null || !searchQuery.trim()) return
    setSearchLoading(true)
    setSearchError(null)
    try {
      const response = await searchKnowledgeBase({
        query: searchQuery.trim(),
        file_ids: [fileId],
        top_k: 5,
        debug: true,
        return_search_trace: true,
        citation_format: 'json',
      })
      setSearchResult(response)
    } catch (cause: unknown) {
      const detail = cause instanceof Error ? cause.message : t('admin.qualityWorkbench.requestFailed')
      setSearchError(detail)
      setSearchResult(null)
    } finally {
      setSearchLoading(false)
    }
  }

  const loadMoreChunks = async () => {
    if (fileId == null || chunksLoading || chunks.length >= chunksTotal) return
    setChunksLoading(true)
    setChunksError(null)
    try {
      const response = await listKnowledgeBaseFileChunks(fileId, {
        page: chunkPage + 1,
        page_size: CHUNK_PAGE_SIZE,
      })
      setChunks((current) => [...current, ...response.items])
      setChunkPage(response.page)
      setChunksTotal(response.total)
    } catch (cause: unknown) {
      const detail = cause instanceof Error ? cause.message : t('admin.qualityWorkbench.requestFailed')
      setChunksError(detail)
    } finally {
      setChunksLoading(false)
    }
  }

  return (
    <div className="admin-root">
      <div className="admin-panel quality-workbench-panel">
        <div className="admin-header">
          <div className="ah-title-group">
            <h2 className="ah-title">{t('admin.qualityWorkbench.title')}</h2>
            <p className="ah-sub">{t('admin.qualityWorkbench.subtitle')}</p>
          </div>
          <Tag color="processing">{t('admin.qualityWorkbench.diagnosticAndCorrection')}</Tag>
        </div>
        <div className="quality-workbench-body">
          <div className="quality-workbench-toolbar">
            <div className="quality-workbench-fields">
              <label className="quality-workbench-field">
                <span>{t('admin.qualityWorkbench.fileId')}</span>
                <InputNumber
                  min={1}
                  value={fileIdInput}
                  onChange={(value) => {
                    setFileIdInput(value)
                    setJobIdInput(null)
                    setTraceIdInput('')
                  }}
                  placeholder={t('admin.qualityWorkbench.fileId')}
                  aria-label={t('admin.qualityWorkbench.fileId')}
                />
              </label>
              <label className="quality-workbench-field">
                <span>{t('admin.qualityWorkbench.jobId')}</span>
                <Select
                  allowClear
                  value={jobIdInput ?? undefined}
                  onChange={(value) => {
                    setJobIdInput(value ?? null)
                    setTraceIdInput('')
                  }}
                  options={(options?.jobs ?? []).map((job) => ({
                    value: job.job_id,
                    label: `#${job.job_id} · ${job.status}${job.provider ? ` · ${job.provider}` : ''}`,
                  }))}
                  loading={optionsLoading}
                  disabled={fileId == null || optionsLoading || optionsError != null}
                  placeholder={
                    optionsLoading
                      ? t('admin.qualityWorkbench.loading')
                      : options?.jobs.length
                        ? t('admin.qualityWorkbench.jobId')
                        : t('admin.qualityWorkbench.noJobs')
                  }
                  aria-label={t('admin.qualityWorkbench.jobId')}
                />
              </label>
              <label className="quality-workbench-field">
                <span>{t('admin.qualityWorkbench.traceId')}</span>
                <Select
                  allowClear
                  value={traceIdInput || undefined}
                  onChange={(value) => {
                    setTraceIdInput(value ?? '')
                    if (value) setQueryInput('')
                  }}
                  options={traceOptions.map((trace) => ({
                    value: trace.trace_id,
                    label: `${trace.trace_id} · ${trace.status}${trace.query_hash ? ` · ${trace.query_hash}` : ''}`,
                  }))}
                  disabled={jobIdInput == null || optionsLoading || optionsError != null}
                  placeholder={
                    jobIdInput == null
                      ? t('admin.qualityWorkbench.selectJobFirst')
                      : traceOptions.length
                        ? t('admin.qualityWorkbench.traceId')
                        : t('admin.qualityWorkbench.noTraces')
                  }
                  aria-label={t('admin.qualityWorkbench.traceId')}
                />
              </label>
              <label className="quality-workbench-field">
                <span>{t('admin.qualityWorkbench.query')}</span>
                <Input
                  value={queryInput}
                  onChange={(event) => setQueryInput(event.target.value)}
                  placeholder={t('admin.qualityWorkbench.query')}
                  aria-label={t('admin.qualityWorkbench.query')}
                />
              </label>
            </div>
            <Button
              type="primary"
              icon={<ReloadOutlined />}
              onClick={load}
              loading={loading}
              disabled={fileIdInput == null || !Number.isInteger(fileIdInput) || fileIdInput <= 0}
            >
              {t('admin.qualityWorkbench.load')}
            </Button>
          </div>

          {loading && <Spin className="quality-workbench-loading" tip={t('admin.qualityWorkbench.loading')} />}
          {error && <Alert type="error" showIcon message={t('admin.qualityWorkbench.requestFailed')} description={error} />}
          {optionsError && <Alert type="error" showIcon message={t('admin.qualityWorkbench.requestFailed')} description={optionsError} />}
          {!loading && fileId == null && !error && <Empty description={t('admin.qualityWorkbench.emptyScope')} />}
          {data && (
            <>
              {data.truncated && (
                <Alert
                  type="warning"
                  showIcon
                  message={t('admin.qualityWorkbench.truncated', {
                    sections:
                      data.truncated_sections
                        .map((section) => t(`admin.qualityWorkbench.sections.${section}`, { defaultValue: section }))
                        .join(', ') || t('admin.qualityWorkbench.partialResponse'),
                  })}
                />
              )}
              <div className="quality-workbench-context">
                <Typography.Text type="secondary">
                  {t('admin.qualityWorkbench.scope', {
                    fileId: data.correlation.file_id,
                    jobId: data.correlation.job_id ?? t('admin.qualityWorkbench.notAvailable'),
                    traceId: data.correlation.trace_id ?? t('admin.qualityWorkbench.notAvailable'),
                  })}
                </Typography.Text>
                <Typography.Text type="secondary" className="quality-workbench-versions">
                  {t('admin.qualityWorkbench.versionsTitle')}:{' '}
                  {VERSION_NAMES.map((versionName) =>
                    `${t(`admin.qualityWorkbench.versions.${versionName}`)}=${data.correlation.versions[versionName] ?? t('admin.qualityWorkbench.notAvailable')}`,
                  ).join(' · ')}
                </Typography.Text>
              </div>
              <Card
                size="small"
                className="quality-workbench-card quality-workbench-chunk-card"
                title={t('admin.qualityWorkbench.chunkWorkbenchTitle')}
                extra={<Tag color="blue">{t('admin.qualityWorkbench.fileScoped')}</Tag>}
              >
                <div className="quality-workbench-chunk-layout">
                  <aside className="quality-workbench-chunk-outline" aria-label={t('admin.qualityWorkbench.chunkOutline')}>
                    <div className="quality-workbench-subheading">
                      <Typography.Text strong>{t('admin.qualityWorkbench.chunkOutline')}</Typography.Text>
                      <Typography.Text type="secondary">{t('admin.qualityWorkbench.chunkCount', { loaded: chunks.length, total: chunksTotal })}</Typography.Text>
                    </div>
                    {chunksLoading && <Spin size="small" />}
                    {chunksError && <Alert type="error" showIcon message={chunksError} />}
                    {!chunksLoading && !chunksError && chunks.length === 0 && (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('admin.qualityWorkbench.noChunks')} />
                    )}
                    <Space direction="vertical" size={4} className="quality-workbench-chunk-list">
                      {chunks.map((chunk) => (
                        <Button
                          key={chunk.id}
                          type={chunk.id === selectedChunkId ? 'primary' : 'text'}
                          className="quality-workbench-chunk-item"
                          onClick={() => setSelectedChunkId(chunk.id)}
                        >
                          <span>#{chunk.chunk_index + 1}</span>
                          <span>{chunk.loc_label || chunk.heading_path || t('admin.qualityWorkbench.unknownLocation')}</span>
                        </Button>
                      ))}
                      {chunks.length < chunksTotal && (
                        <Button block loading={chunksLoading} onClick={() => void loadMoreChunks()}>
                          {t('admin.qualityWorkbench.loadMoreChunks')}
                        </Button>
                      )}
                    </Space>
                  </aside>
                  <section className="quality-workbench-chunk-preview">
                    <div className="quality-workbench-subheading">
                      <Typography.Text strong>{selectedChunk ? `Chunk #${selectedChunk.chunk_index + 1}` : t('admin.qualityWorkbench.chunkPreview')}</Typography.Text>
                      {selectedChunk && <Tag>{selectedChunk.loc_label || t('admin.qualityWorkbench.unknownLocation')}</Tag>}
                    </div>
                    {selectedChunk ? (
                      <>
                        <Typography.Text type="secondary" className="quality-workbench-chunk-meta">
                          {selectedChunk.source} · {selectedChunk.char_start}–{selectedChunk.char_end}{selectedChunk.heading_path ? ` · ${selectedChunk.heading_path}` : ''}
                        </Typography.Text>
                        <pre className="quality-workbench-chunk-source">{selectedChunk.text}</pre>
                      </>
                    ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('admin.qualityWorkbench.selectChunk')} />}
                  </section>
                  <section className="quality-workbench-chunk-actions">
                    <Tabs
                      items={[
                        {
                          key: 'correction',
                          label: t('admin.qualityWorkbench.correctionTab'),
                          children: selectedChunk ? (
                            <Space direction="vertical" size="small" className="quality-workbench-action-content">
                              <Alert type="info" showIcon message={t('admin.qualityWorkbench.sourceReadOnly')} />
                              <label className="quality-workbench-field">
                                <span>{t('admin.qualityWorkbench.editedChunkText')}</span>
                                <Input.TextArea
                                  value={editText}
                                  onChange={(event) => setEditText(event.target.value)}
                                  autoSize={{ minRows: 8, maxRows: 16 }}
                                  aria-label={t('admin.qualityWorkbench.editedChunkText')}
                                />
                              </label>
                              <label className="quality-workbench-field">
                                <span>{t('admin.qualityWorkbench.boostKeywords')}</span>
                                <Input value={editBoost} onChange={(event) => setEditBoost(event.target.value)} aria-label={t('admin.qualityWorkbench.boostKeywords')} />
                              </label>
                              <div className="quality-workbench-correction-diff">
                                <div>
                                  <Typography.Text type="secondary">{t('admin.qualityWorkbench.originalChunk')}</Typography.Text>
                                  <pre>{selectedChunk.text}</pre>
                                </div>
                                <div>
                                  <Typography.Text type="secondary">{t('admin.qualityWorkbench.editedChunk')}</Typography.Text>
                                  <pre>{editText}</pre>
                                </div>
                              </div>
                              <Button type="primary" loading={savingChunk} onClick={() => void saveChunkCorrection()}>
                                {t('admin.qualityWorkbench.saveCorrection')}
                              </Button>
                            </Space>
                          ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('admin.qualityWorkbench.selectChunk')} />,
                        },
                        {
                          key: 'retrieval',
                          label: t('admin.qualityWorkbench.retrievalTestTab'),
                          children: (
                            <Space direction="vertical" size="small" className="quality-workbench-action-content">
                              <Typography.Text type="secondary">{t('admin.qualityWorkbench.retrievalTestHint')}</Typography.Text>
                              <Input
                                value={searchQuery}
                                onChange={(event) => setSearchQuery(event.target.value)}
                                placeholder={t('admin.qualityWorkbench.retrievalTestQuery')}
                                aria-label={t('admin.qualityWorkbench.retrievalTestQuery')}
                                onPressEnter={() => void runRetrievalTest()}
                              />
                              <Button type="primary" loading={searchLoading} disabled={!searchQuery.trim()} onClick={() => void runRetrievalTest()}>
                                {t('admin.qualityWorkbench.runRetrievalTest')}
                              </Button>
                              {searchError && <Alert type="error" showIcon message={searchError} />}
                              {searchResult && (
                                <div className="quality-workbench-search-results">
                                  <Typography.Text type="secondary">{t('admin.qualityWorkbench.retrievalResultCount', { count: searchResult.items.length })}</Typography.Text>
                                  {searchResult.meta?.debug_funnel && (
                                    <Typography.Text type="secondary" className="quality-workbench-funnel">
                                      {t('admin.qualityWorkbench.funnel')}: {Object.entries(searchResult.meta.debug_funnel).map(([key, value]) => `${key}=${value}`).join(' · ')}
                                    </Typography.Text>
                                  )}
                                  {searchResult.items.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('admin.qualityWorkbench.noRetrievalResults')} /> : searchResult.items.map((item, index) => (
                                    <div className="quality-workbench-search-result" key={`${item.chunk_id ?? 'result'}-${index}`}>
                                      <div><Tag color="processing">{item.score.toFixed(3)}</Tag><Typography.Text strong>Chunk #{(item.chunk_index ?? 0) + 1}</Typography.Text></div>
                                      <Typography.Text type="secondary">{item.citation_label || item.source || t('admin.qualityWorkbench.unknownLocation')}</Typography.Text>
                                      <Typography.Paragraph ellipsis={{ rows: 3 }} className="quality-workbench-result-text">{item.text.slice(0, 480)}</Typography.Paragraph>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </Space>
                          ),
                        },
                        {
                          key: 'status',
                          label: t('admin.qualityWorkbench.statusTab'),
                          children: (
                            <Space direction="vertical" size="small" className="quality-workbench-action-content">
                              <Typography.Text strong>{t('admin.qualityWorkbench.changeStatus')}</Typography.Text>
                              <Typography.Text type="secondary">{t('admin.qualityWorkbench.statusScope', { fileId, chunkId: selectedChunk?.id ?? t('admin.qualityWorkbench.notAvailable') })}</Typography.Text>
                              <div className="quality-workbench-status-grid">
                                <Tag color={selectedChunk && editText.trim() !== selectedChunk.text.trim() ? 'warning' : 'default'}>
                                  {selectedChunk && editText.trim() !== selectedChunk.text.trim() ? t('admin.qualityWorkbench.unsavedChanges') : t('admin.qualityWorkbench.noPendingChanges')}
                                </Tag>
                                <Tag color={searchResult ? 'success' : 'default'}>{searchResult ? t('admin.qualityWorkbench.retrievalTested') : t('admin.qualityWorkbench.retrievalNotRun')}</Tag>
                              </div>
                              <Typography.Text type="secondary" className="quality-workbench-versions">
                                {t('admin.qualityWorkbench.versionsTitle')}: {VERSION_NAMES.map((versionName) => `${t(`admin.qualityWorkbench.versions.${versionName}`)}=${data.correlation.versions[versionName] ?? t('admin.qualityWorkbench.notAvailable')}`).join(' · ')}
                              </Typography.Text>
                            </Space>
                          ),
                        },
                      ]}
                    />
                  </section>
                </div>
              </Card>
              <div className="quality-workbench-projections">
                {PROJECTION_NAMES.map((name) => (
                  <ProjectionCard key={name} name={name} projection={data[name]} t={t} />
                ))}
              </div>
              <Card
                size="small"
                className="quality-workbench-card quality-workbench-failures"
                title={t('admin.qualityWorkbench.failuresTitle', { count: data.failures.length })}
              >
                {data.failures.length === 0 ? (
                  <Typography.Text type="secondary">{t('admin.qualityWorkbench.noFailures')}</Typography.Text>
                ) : (
                  <Space direction="vertical" size="small" className="quality-workbench-failure-list">
                    {data.failures.map((failure) => (
                      <Alert
                        key={failure.event_key}
                        type="error"
                        showIcon
                        message={t('admin.qualityWorkbench.failureLabel', {
                          stage: t(`admin.qualityWorkbench.stages.${failure.stage}`, { defaultValue: failure.stage }),
                          reason: t(`admin.qualityWorkbench.reasons.${failure.reason}`, { defaultValue: failure.reason }),
                        })}
                        description={failure.summary}
                      />
                    ))}
                  </Space>
                )}
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
