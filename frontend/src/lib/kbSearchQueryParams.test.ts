import { beforeEach, describe, expect, it, vi } from 'vitest'
import { kbSearchQueryParams } from './kbSearchQueryParams'

const wsState = vi.hoisted(() => ({
  activeId: 42 as number | null,
}))

const settingsState = vi.hoisted(() => ({
  loaded: true,
  shared_workspaces_enabled: true,
}))

vi.mock('@/stores/workspaceStore', () => ({
  getActiveWorkspaceId: () => wsState.activeId,
}))

vi.mock('@/stores/systemSettingsStore', () => ({
  useSystemSettingsStore: {
    getState: () => settingsState,
  },
}))

describe('kbSearchQueryParams', () => {
  beforeEach(() => {
    settingsState.loaded = true
    settingsState.shared_workspaces_enabled = true
    wsState.activeId = 42
  })

  it('共享开启时附带 workspace_id', () => {
    expect(kbSearchQueryParams()).toEqual({ workspace_id: 42 })
  })

  it('共享开启且 cross_workspace 时附带 cross_workspace', () => {
    expect(kbSearchQueryParams(true)).toEqual({ workspace_id: 42, cross_workspace: true })
  })

  it('共享关闭时不传 workspace_id 与 cross_workspace', () => {
    settingsState.shared_workspaces_enabled = false
    expect(kbSearchQueryParams(true)).toBeUndefined()
    expect(kbSearchQueryParams()).toBeUndefined()
  })

  it('设置未加载时不传参数', () => {
    settingsState.loaded = false
    expect(kbSearchQueryParams(true)).toBeUndefined()
  })

  it('无 active workspace 时仅 cross_workspace', () => {
    wsState.activeId = null
    expect(kbSearchQueryParams(true)).toEqual({ cross_workspace: true })
  })
})
