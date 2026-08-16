/** OKF native upload / note metadata helpers (111). */

export const DEFAULT_OKF_TYPE = 'FileX Source'

export interface OkfMetadataDraft {
  title: string
  type: string
  description: string
  tags: string[]
  conceptPath: string
}

export interface OkfMetaApiResponse {
  okf_concept_path: string | null
  okf_type: string | null
  frontmatter: Record<string, unknown>
}

export function defaultOkfTitleFromFilename(filename: string): string {
  const trimmed = filename.trim()
  if (!trimmed) return ''
  const dot = trimmed.lastIndexOf('.')
  const base = dot > 0 ? trimmed.slice(0, dot) : trimmed
  return base.trim() || trimmed
}

export function emptyOkfMetadataDraft(): OkfMetadataDraft {
  return {
    title: '',
    type: DEFAULT_OKF_TYPE,
    description: '',
    tags: [],
    conceptPath: '',
  }
}

export function okfMetadataDraftFromFilename(filename: string): OkfMetadataDraft {
  return {
    ...emptyOkfMetadataDraft(),
    title: defaultOkfTitleFromFilename(filename),
  }
}

export function tagsFromFrontmatter(frontmatter: Record<string, unknown> | undefined): string[] {
  const raw = frontmatter?.tags
  if (!Array.isArray(raw)) return []
  return raw.map((t) => String(t).trim()).filter(Boolean)
}

export function okfMetadataDraftFromApi(
  meta: OkfMetaApiResponse,
  fallbackTitle = '',
): OkfMetadataDraft {
  const fm = meta.frontmatter ?? {}
  const title = typeof fm.title === 'string' ? fm.title : fallbackTitle
  const type = meta.okf_type ?? (typeof fm.type === 'string' ? fm.type : DEFAULT_OKF_TYPE)
  const description = typeof fm.description === 'string' ? fm.description : ''
  return {
    title,
    type: type || DEFAULT_OKF_TYPE,
    description,
    tags: tagsFromFrontmatter(fm),
    conceptPath: meta.okf_concept_path ?? '',
  }
}

export function okfMetadataDraftsEqual(a: OkfMetadataDraft, b: OkfMetadataDraft): boolean {
  return (
    a.title === b.title &&
    a.type === b.type &&
    a.description === b.description &&
    a.conceptPath === b.conceptPath &&
    a.tags.length === b.tags.length &&
    a.tags.every((tag, i) => tag === b.tags[i])
  )
}

/** Append optional OKF upload fields when user expanded metadata panel for a single file. */
export function appendOkfUploadFields(
  fd: FormData,
  draft: OkfMetadataDraft,
  options: { advancedPath: boolean },
): void {
  const title = draft.title.trim()
  const type = draft.type.trim() || DEFAULT_OKF_TYPE
  if (title) fd.append('okf_title', title)
  fd.append('okf_type', type)
  const desc = draft.description.trim()
  if (desc) fd.append('okf_description', desc)
  if (draft.tags.length) fd.append('okf_tags', JSON.stringify(draft.tags))
  if (options.advancedPath) {
    const path = draft.conceptPath.trim()
    if (path) fd.append('okf_concept_path', path)
  }
}

export function buildOkfMetaPutPayload(draft: OkfMetadataDraft): {
  type: string
  title: string
  description: string
  tags: string[]
  okf_concept_path?: string
} {
  const payload: {
    type: string
    title: string
    description: string
    tags: string[]
    okf_concept_path?: string
  } = {
    type: draft.type.trim() || DEFAULT_OKF_TYPE,
    title: draft.title.trim(),
    description: draft.description.trim(),
    tags: [...draft.tags],
  }
  const path = draft.conceptPath.trim()
  if (path) payload.okf_concept_path = path
  return payload
}
