import { describe, expect, it } from 'vitest'
import { getSelectableExtractProviders, parseExtractProvider } from './extractProviders'

describe('extract provider options', () => {
  it('parses insavlo as a valid provider', () => {
    expect(parseExtractProvider('insavlo')).toBe('insavlo')
  })

  it('hides insavlo when runtime config is not ready', () => {
    expect(getSelectableExtractProviders(false)).toEqual(['legacy', 'liteparse', 'docling', 'mineru'])
  })

  it('shows insavlo when runtime config is ready', () => {
    expect(getSelectableExtractProviders(true)).toEqual(['legacy', 'liteparse', 'docling', 'mineru', 'insavlo'])
  })
})
