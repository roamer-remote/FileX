import type { TFunction } from 'i18next'
import type { FileItem } from '@/api/files'

export type ExtractEngineDisplay = {
  rawEngine: string | null
  summary: string
  detail: string
  extractStatusLabel?: string
  extractedAtLabel?: string
}

const ENGINE_I18N_KEYS: Record<string, string> = {
  markitdown: 'markitdown',
  'libreoffice+markitdown': 'libreofficeMarkitdown',
  'python-docx': 'pythonDocx',
  'python-pptx': 'pythonPptx',
  openpyxl: 'openpyxl',
  'libreoffice+python-docx': 'libreofficePythonDocx',
  'libreoffice+python-pptx': 'libreofficePythonPptx',
  'libreoffice+openpyxl': 'libreofficeOpenpyxl',
  pymupdf: 'pymupdf',
  'pymupdf+rapidocr': 'pymupdfRapidocr',
  rapidocr: 'rapidocr',
  'liteparse+rapidocr': 'liteparseRapidocr',
  docling: 'docling',
  mineru: 'mineru',
  'pdf-inspector': 'pdfInspector',
  'markdown-copy': 'markdownCopy',
}

function extractStatusKey(status: string | undefined): string | null {
  if (!status) return null
  const map: Record<string, string> = {
    pending: 'extractEngine.statusPending',
    extracting: 'extractEngine.statusExtracting',
    ready: 'extractEngine.statusReady',
    failed: 'extractEngine.statusFailed',
    skipped: 'extractEngine.statusSkipped',
    not_needed: 'extractEngine.statusNotNeeded',
  }
  return map[status] ?? null
}

export function getExtractEngineDisplay(
  file: Pick<FileItem, 'extract_engine' | 'extract_status' | 'extracted_at' | 'has_md'>,
  t: TFunction,
  formatDateFn: (iso: string) => string,
): ExtractEngineDisplay | null {
  const inFlight =
    file.extract_status === 'pending' || file.extract_status === 'extracting'
  if (!file.has_md && !inFlight) return null

  const raw = file.extract_engine?.trim() || null
  const statusKey = extractStatusKey(file.extract_status)
  const extractStatusLabel = statusKey ? t(statusKey) : undefined

  if (inFlight && !file.has_md) return null

  const extractedAtLabel =
    file.extracted_at?.trim() ? t('extractEngine.extractedAt', { time: formatDateFn(file.extracted_at) }) : undefined

  const metaLines = [extractStatusLabel, extractedAtLabel].filter(Boolean) as string[]
  const metaBlock = metaLines.length ? metaLines.join('\n') : ''

  if (!raw) {
    if (!file.has_md) return null
    const detail = [t('extractEngine.manualDetail'), metaBlock].filter(Boolean).join('\n\n')
    return {
      rawEngine: null,
      summary: t('extractEngine.manualSummary'),
      detail,
      extractStatusLabel,
      extractedAtLabel,
    }
  }

  const engineKey = ENGINE_I18N_KEYS[raw.toLowerCase()]
  if (engineKey) {
    const label = t(`extractEngine.engines.${engineKey}.label`)
    const engineDetail = t(`extractEngine.engines.${engineKey}.detail`)
    const summary = t('extractEngine.footerSummary', { engine: label, raw })
    const detail = [engineDetail, t('extractEngine.rawEngine', { raw }), metaBlock].filter(Boolean).join('\n\n')
    return {
      rawEngine: raw,
      summary,
      detail,
      extractStatusLabel,
      extractedAtLabel,
    }
  }

  const summary = t('extractEngine.footerSummaryUnknown', { raw })
  const detail = [t('extractEngine.unknownDetail', { raw }), metaBlock].filter(Boolean).join('\n\n')
  return {
    rawEngine: raw,
    summary,
    detail,
    extractStatusLabel,
    extractedAtLabel,
  }
}
