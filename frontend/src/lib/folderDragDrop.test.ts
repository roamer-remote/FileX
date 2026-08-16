import { describe, expect, it } from 'vitest'
import type { FolderItem } from '@/api/folders'
import {
  computeFolderDropHint,
  resolveDropPosition,
  DROP_EDGE_PX,
} from './folderDragDrop'

const VIRTUAL = 'folder-drop-virtual-root'

function f(id: number, name: string, parent_id: number | null = null): FolderItem {
  return { id, name, parent_id, sort_order: id, user_id: 1, created_at: '' }
}

describe('resolveDropPosition', () => {
  const top = 100
  const height = 36

  it('uses middle band as inside for reparent', () => {
    expect(resolveDropPosition(top + 18, top, height)).toBe('inside')
    expect(resolveDropPosition(top + DROP_EDGE_PX + 1, top, height)).toBe('inside')
    expect(resolveDropPosition(top + height - DROP_EDGE_PX - 1, top, height)).toBe('inside')
  })

  it('uses top/bottom edges for before/after reorder', () => {
    expect(resolveDropPosition(top + 2, top, height)).toBe('before')
    expect(resolveDropPosition(top + height - 2, top, height)).toBe('after')
  })
})

describe('computeFolderDropHint', () => {
  it('marks inside on folder row center', () => {
    const folders = [f(1, 'A'), f(2, 'B', 1)]
    const hint = computeFolderDropHint(folders, 2, 1, 118, { top: 100, height: 36 }, VIRTUAL)
    expect(hint?.position).toBe('inside')
    expect(hint?.target).toEqual({ kind: 'folder', folderId: 1 })
    expect(hint?.invalid).toBe(false)
  })

  it('rejects drop into descendant', () => {
    const folders = [f(1, 'A'), f(2, 'B', 1)]
    const hint = computeFolderDropHint(folders, 1, 2, 118, { top: 100, height: 36 }, VIRTUAL)
    expect(hint?.position).toBe('inside')
    expect(hint?.invalid).toBe(true)
  })
})
