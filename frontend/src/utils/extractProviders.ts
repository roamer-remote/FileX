/** 与 backend KB_EXTRACT_PROVIDERS / registry.VALID_PROVIDERS 保持一致 */
export const EXTRACT_PROVIDERS = ['legacy', 'liteparse', 'docling', 'mineru', 'insavlo'] as const
export const BASE_EXTRACT_PROVIDERS = ['legacy', 'liteparse', 'docling', 'mineru'] as const

export type ExtractProvider = (typeof EXTRACT_PROVIDERS)[number]

export function getSelectableExtractProviders(insavloReady?: boolean): ExtractProvider[] {
  return insavloReady ? [...BASE_EXTRACT_PROVIDERS, 'insavlo'] : [...BASE_EXTRACT_PROVIDERS]
}

export function parseExtractProvider(name?: string | null): ExtractProvider {
  const normalized = (name || 'legacy').trim().toLowerCase()
  return (EXTRACT_PROVIDERS as readonly string[]).includes(normalized)
    ? (normalized as ExtractProvider)
    : 'legacy'
}
