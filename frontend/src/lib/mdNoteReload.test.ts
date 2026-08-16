import { describe, expect, it } from 'vitest'
import { mdNoteContentLoadKey, shouldReloadMdOnHasMdReady } from './mdNoteReload'

describe('shouldReloadMdOnHasMdReady', () => {
  it('reloads when has_md becomes true and editor is clean', () => {
    expect(shouldReloadMdOnHasMdReady(false, true, false)).toBe(true)
    expect(shouldReloadMdOnHasMdReady(null, true, false)).toBe(false)
  })

  it('skips reload while user has unsaved edits', () => {
    expect(shouldReloadMdOnHasMdReady(false, true, true)).toBe(false)
  })

  it('skips when has_md unchanged', () => {
    expect(shouldReloadMdOnHasMdReady(true, true, false)).toBe(false)
  })
})

describe('mdNoteContentLoadKey', () => {
  it('returns null when closed or missing file id', () => {
    expect(
      mdNoteContentLoadKey({
        open: false,
        fileId: 1,
        hasMd: true,
        reloadToken: 0,
        scrollToAnchorId: null,
        adminMdApi: false,
        effectiveReadOnly: false,
      }),
    ).toBeNull()
    expect(
      mdNoteContentLoadKey({
        open: true,
        fileId: undefined,
        hasMd: true,
        reloadToken: 0,
        scrollToAnchorId: null,
        adminMdApi: false,
        effectiveReadOnly: false,
      }),
    ).toBeNull()
  })

  it('changes only when file, has_md, reload token, or view mode changes', () => {
    const base = {
      open: true,
      fileId: 42,
      hasMd: true,
      reloadToken: 0,
      scrollToAnchorId: null as string | null,
      adminMdApi: false,
      effectiveReadOnly: false,
    }
    expect(mdNoteContentLoadKey(base)).toBe('42:true:0::0:0')
    expect(mdNoteContentLoadKey({ ...base, reloadToken: 1 })).toBe('42:true:1::0:0')
    expect(mdNoteContentLoadKey({ ...base, hasMd: false })).toBe('42:false:0::0:0')
    expect(mdNoteContentLoadKey({ ...base, scrollToAnchorId: 'fta-1' })).toBe('42:true:0:fta-1:0:0')
  })
})
