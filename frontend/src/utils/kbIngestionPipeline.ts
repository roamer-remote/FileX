export type PipelineRouteRow = {
  key: string
  matchKind: 'mime_prefix' | 'ext'
  mimePrefix: string
  extensions: string
  extractProvider: string
}

export type PipelineStages = {
  entity_extract: boolean
  wiki_lint_on_index: boolean
}

const ROUTE_PROVIDERS = ['legacy', 'docling', 'mineru', 'liteparse', 'markitdown', 'insavlo'] as const

export function defaultPipelineStages(): PipelineStages {
  return { entity_extract: false, wiki_lint_on_index: false }
}

export function emptyPipelineJson(): string {
  return ''
}

export function parsePipelineJson(raw: string | undefined | null): {
  routes: PipelineRouteRow[]
  stages: PipelineStages
  advancedJson: string
} {
  const trimmed = (raw ?? '').trim()
  if (!trimmed) {
    return { routes: [], stages: defaultPipelineStages(), advancedJson: '' }
  }
  const data = JSON.parse(trimmed) as {
    version?: number
    routes?: Array<{ match?: { mime_prefix?: string; ext?: string[] }; extract_provider?: string }>
    stages?: Partial<PipelineStages>
  }
  if (data.version !== 1) {
    throw new Error('pipeline version 须为 1')
  }
  const routes: PipelineRouteRow[] = (data.routes ?? []).map((r, i) => {
    const match = r.match ?? {}
    if (match.mime_prefix) {
      return {
        key: `r-${i}`,
        matchKind: 'mime_prefix',
        mimePrefix: String(match.mime_prefix),
        extensions: '',
        extractProvider: String(r.extract_provider ?? 'legacy'),
      }
    }
    return {
      key: `r-${i}`,
      matchKind: 'ext',
      mimePrefix: '',
      extensions: (match.ext ?? []).join(', '),
      extractProvider: String(r.extract_provider ?? 'legacy'),
    }
  })
  const stages = { ...defaultPipelineStages(), ...(data.stages ?? {}) }
  return { routes, stages, advancedJson: JSON.stringify(data, null, 2) }
}

export function serializePipelineFromTable(
  routes: PipelineRouteRow[],
  stages: PipelineStages,
): string {
  if (routes.length === 0 && !stages.entity_extract && !stages.wiki_lint_on_index) {
    return ''
  }
  const payload = {
    version: 1,
    routes: routes.map((row) => {
      if (row.matchKind === 'mime_prefix') {
        return {
          match: { mime_prefix: row.mimePrefix.trim().toLowerCase() },
          extract_provider: row.extractProvider,
        }
      }
      const ext = row.extensions
        .split(',')
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean)
        .map((s) => (s.startsWith('.') ? s : `.${s}`))
      return { match: { ext }, extract_provider: row.extractProvider }
    }),
    stages,
  }
  return JSON.stringify(payload)
}

export { ROUTE_PROVIDERS }
