import type { TFunction } from 'i18next'

const DETAIL_KEY_LABELS: Record<string, string> = {
  gpu_used: 'admin.logs.detailFields.gpuUsed',
  index_job_id: 'admin.logs.detailFields.indexJobId',
  job_id: 'admin.logs.detailFields.jobId',
  llm_gpu_used: 'admin.logs.detailFields.llmGpuUsed',
  llm_gpu_evidence: 'admin.logs.detailFields.llmGpuEvidence',
  llm_model_path_resolved: 'admin.logs.detailFields.llmModelPathResolved',
  llm_model_path_scopes: 'admin.logs.detailFields.llmModelPathScopes',
  llm_model_paths: 'admin.logs.detailFields.llmModelPaths',
  llm_models: 'admin.logs.detailFields.llmModels',
  llm_providers: 'admin.logs.detailFields.llmProviders',
  llm_purposes: 'admin.logs.detailFields.llmPurposes',
  model: 'admin.logs.detailFields.model',
  model_path: 'admin.logs.detailFields.modelPath',
  post_entity_ms: 'admin.logs.detailFields.postEntityMs',
  post_index_ms: 'admin.logs.detailFields.postIndexMs',
  post_raptor_ms: 'admin.logs.detailFields.postRaptorMs',
  post_sag_ms: 'admin.logs.detailFields.postSagMs',
  provider: 'admin.logs.detailFields.provider',
}

export function formatAdminLogDetail(detail: string | null | undefined, t: TFunction): string {
  if (!detail) return '—'
  const decodeValue = (value: string): string => {
    try {
      return decodeURIComponent(value)
    } catch {
      return value
    }
  }
  return detail
    .split(' ')
    .map((part) => {
      const separator = part.indexOf('=')
      if (separator <= 0) return part
      const key = part.slice(0, separator)
      const value = decodeValue(part.slice(separator + 1))
      const labelKey = DETAIL_KEY_LABELS[key]
      if (!labelKey) return part
      const renderedValue = key === 'llm_gpu_used'
        ? value.replace(/\btrue\b/g, t('admin.logs.values.true')).replace(/\bfalse\b/g, t('admin.logs.values.false')).replace(/\bunknown\b/g, t('admin.logs.values.unknown'))
        : value
      return `${t(labelKey)}=${renderedValue}`
    })
    .join(' ')
}
