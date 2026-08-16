import { describe, expect, it } from 'vitest'
import { LEGACY_KB_INDEX_REBUILD_TAB, resolveKbIndexTabs } from '@/lib/kbIndexUiState'

describe('resolveKbIndexTabs', () => {
  it('maps legacy rebuild tab to preview', () => {
    expect(
      resolveKbIndexTabs({ active_tab: LEGACY_KB_INDEX_REBUILD_TAB as never }),
    ).toEqual({
      active_tab: 'preview',
      preview_sub_tab: 'auto',
    })
  })

  it('falls back invalid main tab to preview', () => {
    expect(resolveKbIndexTabs({ active_tab: 'invalid' as 'preview' })).toEqual({
      active_tab: 'preview',
      preview_sub_tab: 'auto',
    })
  })

  it('maps okf tab to preview when OKF UI is disabled', () => {
    expect(resolveKbIndexTabs({ active_tab: 'okf', preview_sub_tab: 'wiki' })).toEqual({
      active_tab: 'preview',
      preview_sub_tab: 'wiki',
    })
  })
})
