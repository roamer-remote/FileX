import { useEffect, useRef, useState } from "react"
import { Trans, useTranslation } from "react-i18next"
import { App, Button, Empty, Input, Select, Spin, Switch, Tag, Tooltip } from "antd"
import { EyeOutlined, SearchOutlined } from "@ant-design/icons"
import { getFileById, type FileItem } from "@/api/files"
import { searchKnowledgeBase, type KbChunkHit, type KbChunkSnippet } from "@/api/knowledgeBase"
import { formatApiError } from "@/api/index"
import { useFilesStore } from "@/stores/filesStore"
import { useSystemSettingsStore } from "@/stores/systemSettingsStore"
import { useAuthStore } from "@/stores/authStore"
import type { KbSearchMeta } from "@/api/knowledgeBase"
import { useWorkspaceStore } from "@/stores/workspaceStore"

const KB_CROSS_WS_KEY = 'filex_kb_search_cross_workspace'
const KB_SAG_EXPAND_KEY = 'filex_kb_search_sag_expand'
const KB_SAG_MODE_KEY = 'filex_kb_search_sag_mode'

type SagSearchMode = 'fast' | 'standard'

function loadBoolPref(key: string, defaultValue = false): boolean {
  try {
    const raw = localStorage.getItem(key)
    if (raw === null) return defaultValue
    return raw === '1'
  } catch {
    return defaultValue
  }
}

function saveBoolPref(key: string, enabled: boolean) {
  try {
    localStorage.setItem(key, enabled ? '1' : '0')
  } catch {
    /* ignore */
  }
}

function loadSagModePref(): SagSearchMode {
  try {
    const raw = localStorage.getItem(KB_SAG_MODE_KEY)
    return raw === 'standard' ? 'standard' : 'fast'
  } catch {
    return 'fast'
  }
}

function saveSagModePref(mode: SagSearchMode) {
  try {
    localStorage.setItem(KB_SAG_MODE_KEY, mode)
  } catch {
    /* ignore */
  }
}

function loadCrossWorkspacePref(): boolean {
  try {
    const raw = localStorage.getItem(KB_CROSS_WS_KEY)
    if (raw === null) return true
    return raw === '1'
  } catch {
    return true
  }
}

function saveCrossWorkspacePref(enabled: boolean) {
  try {
    localStorage.setItem(KB_CROSS_WS_KEY, enabled ? '1' : '0')
  } catch {
    /* ignore */
  }
}

function snippetPreview(text: string, maxLen = 160): string {
  const one = text.replace(/\s+/g, " ").trim()
  if (one.length <= maxLen) return one
  return `${one.slice(0, maxLen)}…`
}

function showSnippetCitation(hit: KbChunkHit, snip: KbChunkSnippet): boolean {
  const label = snip.citation_label?.trim()
  if (!label) return false
  const snippets = hit.snippets ?? []
  if (snippets.length >= 2) return true
  const hitLabel = hit.citation_label?.trim()
  return hitLabel !== label
}

type Props = {
  files: FileItem[]
  onPreview: (file: FileItem) => void
}

export default function KbSemanticSearch({ files, onPreview }: Props) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const tagFilter = useFilesStore((s) => s.tagFilter)
  const tagFilter2 = useFilesStore((s) => s.tagFilter2)
  const sharedEnabled = useSystemSettingsStore((s) => s.shared_workspaces_enabled ?? true)
  const sagExtractEnabled = useSystemSettingsStore((s) => s.kb_sag_event_extract_enabled ?? false)
  const settingsLoaded = useSystemSettingsStore((s) => s.loaded)
  const settingsRevision = useSystemSettingsStore((s) => s.revision)
  const loadSettings = useSystemSettingsStore((s) => s.load)
  const workspaces = useWorkspaceStore((s) => s.workspaces)
  const crossWorkspaceSearch =
    settingsLoaded && sharedEnabled && workspaces.some((w) => w.kind === "shared")
  const [query, setQuery] = useState("")
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<KbChunkHit[] | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [crossWorkspace, setCrossWorkspace] = useState(loadCrossWorkspacePref)
  const isAdmin = useAuthStore((s) => s.user?.is_admin === true)
  const [debugMode, setDebugMode] = useState(false)
  const [sagExpand, setSagExpand] = useState(() => loadBoolPref(KB_SAG_EXPAND_KEY, false))
  const [sagSearchMode, setSagSearchMode] = useState<SagSearchMode>(() => loadSagModePref())
  const [searchMeta, setSearchMeta] = useState<KbSearchMeta | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)

  const closeResults = () => {
    setExpanded(false)
  }

  useEffect(() => {
    void loadSettings()
  }, [loadSettings])

  useEffect(() => {
    const onSettingsChanged = () => {
      void loadSettings()
    }
    window.addEventListener("filex:system-settings-changed", onSettingsChanged)
    return () => window.removeEventListener("filex:system-settings-changed", onSettingsChanged)
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

  const runSearch = async () => {
    const q = query.trim()
    if (!q) {
      message.warning(t("kbSearch.queryRequired"))
      return
    }
    setLoading(true)
    setExpanded(true)
    try {
      const res = await searchKnowledgeBase({
        query: q,
        top_k: 8,
        tags: tagFilter ? [tagFilter] : undefined,
        context_chunks: 1,
        group_by_file: true,
        cross_workspace: crossWorkspaceSearch && crossWorkspace ? true : undefined,
        debug: debugMode && isAdmin,
        expand_sag_events: sagExtractEnabled && sagExpand ? true : undefined,
        sag_search_mode: sagExtractEnabled && sagExpand ? sagSearchMode : undefined,
      })
      setResults(res.items)
      setSearchMeta(res.meta ?? null)
    } catch (e) {
      message.error(formatApiError(e))
      setResults([])
      setSearchMeta(null)
    } finally {
      setLoading(false)
    }
  }

  const openHit = async (hit: KbChunkHit) => {
    try {
      let file = files.find((f) => f.id === hit.file_id)
      if (!file) {
        const res = await getFileById(hit.file_id)
        file = res.data
      }
      onPreview(file)
    } catch {
      message.error(t("kbSearch.fileOpenFailed"))
    }
  }

  const showResults = expanded && results !== null

  useEffect(() => {
    if (!showResults) return
    const onPointerDown = (e: PointerEvent) => {
      const root = rootRef.current
      if (!root || root.contains(e.target as Node)) return
      closeResults()
    }
    document.addEventListener("pointerdown", onPointerDown, true)
    return () => document.removeEventListener("pointerdown", onPointerDown, true)
  }, [showResults])

  const onQueryChange = (value: string) => {
    setQuery(value)
    if (!value.trim()) {
      setResults(null)
      setExpanded(false)
    }
  }

  const displaySnippets = (hit: KbChunkHit): KbChunkSnippet[] => {
    if (hit.snippets?.length) {
      return hit.snippets
    }
    return [
      {
        chunk_index: hit.chunk_index,
        text: hit.context_text || hit.text,
        score: hit.score,
        heading_path: hit.heading_path,
      },
    ]
  }

  return (
    <div className="fl-kb-search" ref={rootRef}>
      <div className="fl-kb-search-bar">
        <Input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder={t("kbSearch.placeholder")}
          size="small"
          allowClear
          disabled={loading}
          onPressEnter={() => void runSearch()}
          prefix={<SearchOutlined />}
          className="fl-kb-search-input"
        />
        <Button
          type="primary"
          size="small"
          className="fl-kb-search-btn"
          loading={loading}
          icon={<SearchOutlined />}
          onClick={() => void runSearch()}
        >
          {t("kbSearch.search")}
        </Button>
        {crossWorkspaceSearch ? (
          <label className="fl-kb-search-cross-switch">
            <Switch
              size="small"
              checked={crossWorkspace}
              onChange={(checked) => {
                setCrossWorkspace(checked)
                saveCrossWorkspacePref(checked)
              }}
            />
            <span>{t("kbSearch.crossWorkspaceSwitch")}</span>
          </label>
        ) : null}
        {tagFilter ? (
          <Tag className="fl-kb-search-tag-hint" color="processing">
            {tagFilter2
              ? t("kbSearch.tagFilterDualHint", { tag: tagFilter, tag2: tagFilter2 })
              : t("kbSearch.tagFilterHint", { tag: tagFilter })}
          </Tag>
        ) : null}
        {isAdmin ? (
          <label className="fl-kb-search-cross-switch">
            <Switch size="small" checked={debugMode} onChange={setDebugMode} />
            <span>{t("kbSearch.debugMode")}</span>
          </label>
        ) : null}
        <Tooltip title={sagExtractEnabled ? undefined : t("kbSearch.sagDisabledHint")}>
          <label className="fl-kb-search-cross-switch">
            <Switch
              size="small"
              checked={sagExtractEnabled && sagExpand}
              disabled={!sagExtractEnabled || loading}
              onChange={(checked) => {
                setSagExpand(checked)
                saveBoolPref(KB_SAG_EXPAND_KEY, checked)
              }}
            />
            <span>{t("kbRetrievalEval.sagExpandSwitch")}</span>
          </label>
        </Tooltip>
        {sagExtractEnabled && sagExpand ? (
          <label className="fl-kb-search-cross-switch">
            <span>{t("kbRetrievalEval.sagModeSwitch")}</span>
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
      </div>
      {debugMode && searchMeta ? (
        <div className="fl-kb-search-debug-meta">
          <span>
            {t("kbSearch.debugMeta", {
              hybrid: searchMeta.hybrid_enabled ? "on" : "off",
              rerank: searchMeta.rerank_applied ? "on" : "off",
              rerankAvail: searchMeta.rerank_enabled ? "yes" : "no",
            })}
          </span>
        </div>
      ) : null}
      {searchMeta?.sag_expanded ? (
        <div className="fl-kb-search-debug-meta">
          <span>
            {t("kbRetrievalEval.metaSagExpand", {
              count: searchMeta.sag_added_hits ?? 0,
              mode: searchMeta.sag_mode_effective ?? searchMeta.sag_mode_requested ?? 'fast',
              degraded: searchMeta.sag_mode_degraded ? 'yes' : 'no',
            })}
          </span>
        </div>
      ) : null}
      {showResults ? (
        <div className="fl-kb-search-results">
          {loading ? (
            <div className="fl-kb-search-loading">
              <Spin size="small" />
            </div>
          ) : results!.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("kbSearch.noResults")} />
          ) : (
            <>
              <div className="fl-kb-search-summary">
                <Trans
                  i18nKey="kbSearch.fileCount"
                  values={{ count: results!.length }}
                  components={{
                    count: <span className="fl-kb-search-summary-count" />,
                  }}
                />
              </div>
              <ul className="fl-kb-search-list">
                {results!.map((hit) => (
                  <li key={hit.file_id} className="fl-kb-search-hit">
                    <div className="fl-kb-search-hit-meta">
                      <span className="fl-kb-search-hit-name" title={hit.original_name}>
                        {hit.original_name}
                      </span>
                      <span className="fl-kb-search-hit-score">
                        {t("kbSearch.score", { score: (hit.score * 100).toFixed(0) })}
                        {hit.source === "sidecar_md"
                          ? ` · ${t("kbSearch.sourceSidecar")}`
                          : hit.source === "main_md"
                            ? ` · ${t("kbSearch.sourceMain")}`
                            : ""}
                        {(hit.matched_chunks ?? 1) > 1
                          ? ` · ${t("kbSearch.matchedChunks", { count: hit.matched_chunks })}`
                          : ""}
                        {debugMode && hit.chunk_id != null ? ` · #${hit.chunk_id}` : ""}
                        {debugMode && hit.vector_score != null
                          ? ` · vec ${(hit.vector_score * 100).toFixed(0)}%`
                          : ""}
                        {debugMode && hit.rerank_score != null
                          ? ` · rr ${(hit.rerank_score * 100).toFixed(0)}%`
                          : ""}
                      </span>
                    </div>
                    {hit.citation_label?.trim() ? (
                      <span className="fl-kb-search-hit-citation" title={hit.citation_label}>
                        {hit.citation_label}
                      </span>
                    ) : null}
                    <div className="fl-kb-search-hit-snippets">
                      {displaySnippets(hit).map((snip) => (
                        <div
                          key={`${hit.file_id}-${snip.chunk_index}`}
                          className="fl-kb-search-hit-snippet-block"
                        >
                          {showSnippetCitation(hit, snip) ? (
                            <span
                              className="fl-kb-search-hit-snippet-citation"
                              title={snip.citation_label ?? undefined}
                            >
                              {t("kbSearch.citationLabel", { label: snip.citation_label })}
                            </span>
                          ) : null}
                          {snip.heading_path ? (
                            <span className="fl-kb-search-hit-heading">{snip.heading_path}</span>
                          ) : null}
                          <p className="fl-kb-search-hit-snippet">
                            {snippetPreview(snip.text)}
                          </p>
                        </div>
                      ))}
                    </div>
                    <Button
                      type="link"
                      size="small"
                      className="fl-kb-search-hit-open"
                      icon={<EyeOutlined />}
                      onClick={() => void openHit(hit)}
                    >
                      {t("kbSearch.openFile")}
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      ) : null}
    </div>
  )
}
