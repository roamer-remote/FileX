import api from './index'
import { downloadAuthenticatedFile } from './files'

export interface OkfValidateResponse {
  conformant: boolean
  errors: string[]
  warnings: string[]
  concept_count: number
}

export interface OkfImportResponse {
  concepts_created: number
  concepts_updated: number
  index_pages: number
  log_pages: number
  log_entries_imported: number
  warnings: string[]
  folder_id: number | null
  batches_committed: number
  dry_run: boolean
}

export async function validateOkfBundle(
  file: File,
  workspaceId: number | null,
): Promise<OkfValidateResponse> {
  const form = new FormData()
  form.append('bundle', file)
  if (workspaceId != null) {
    form.append('workspace_id', String(workspaceId))
  }
  const res = await api.post<OkfValidateResponse>('/knowledge-base/okf/validate', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return res.data
}

export async function importOkfBundle(
  file: File,
  options: {
    workspaceId: number | null
    folderId?: number
    dryRun?: boolean
  },
): Promise<OkfImportResponse> {
  const form = new FormData()
  form.append('bundle', file)
  if (options.workspaceId != null) {
    form.append('workspace_id', String(options.workspaceId))
  }
  if (options.folderId != null) {
    form.append('folder_id', String(options.folderId))
  }
  if (options.dryRun) {
    form.append('dry_run', 'true')
  }
  const res = await api.post<OkfImportResponse>('/knowledge-base/okf/import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300_000,
  })
  return res.data
}

export async function exportOkfBundle(options: {
  workspaceId: number | null
  folderId?: number
  includeSources?: boolean
}): Promise<void> {
  const params = new URLSearchParams()
  if (options.workspaceId != null) {
    params.set('workspace_id', String(options.workspaceId))
  }
  if (options.folderId != null) {
    params.set('folder_id', String(options.folderId))
  }
  if (options.includeSources) {
    params.set('include_sources', 'true')
  }
  const qs = params.toString()
  const url = `/api/knowledge-base/okf/export${qs ? `?${qs}` : ''}`
  await downloadAuthenticatedFile(url, 'workspace-okf.zip')
}
