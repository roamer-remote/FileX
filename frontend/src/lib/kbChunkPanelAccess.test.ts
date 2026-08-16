import { describe, expect, it } from 'vitest'
import {
  kbChunkDrawerFieldState,
  resolveKbChunkPanelAccess,
  shouldShowReindexActions,
} from './kbChunkPanelAccess'

describe('resolveKbChunkPanelAccess', () => {
  it('owner 可编辑且可 reindex', () => {
    expect(resolveKbChunkPanelAccess({ fileOwnerId: 1, currentUserId: 1, isAdmin: false })).toEqual({
      canEdit: true,
      canReindex: true,
    })
  })

  it('admin 非 owner 可 PATCH 但不可 reindex', () => {
    expect(resolveKbChunkPanelAccess({ fileOwnerId: 1, currentUserId: 2, isAdmin: true })).toEqual({
      canEdit: true,
      canReindex: false,
    })
    expect(shouldShowReindexActions(false)).toBe(false)
  })

  it('非 owner 非 admin 只读', () => {
    expect(resolveKbChunkPanelAccess({ fileOwnerId: 1, currentUserId: 3, isAdmin: false })).toEqual({
      canEdit: false,
      canReindex: false,
    })
  })
})

describe('kbChunkDrawerFieldState KbChunkPanel 多模态', () => {
  it('figure/table 正文只读、boost 仍可编辑', () => {
    expect(kbChunkDrawerFieldState(true, 'figure')).toEqual({
      textEditable: false,
      boostEditable: true,
    })
    expect(kbChunkDrawerFieldState(true, 'table')).toEqual({
      textEditable: false,
      boostEditable: true,
    })
  })

  it('普通段落正文与 boost 均可编辑', () => {
    expect(kbChunkDrawerFieldState(true, 'paragraph')).toEqual({
      textEditable: true,
      boostEditable: true,
    })
  })

  it('无编辑权限时字段均不可编辑', () => {
    expect(kbChunkDrawerFieldState(false, 'figure')).toEqual({
      textEditable: false,
      boostEditable: false,
    })
  })
})
