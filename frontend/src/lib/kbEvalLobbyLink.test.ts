import { describe, expect, it } from 'vitest'
import {
  KB_EVAL_PREFILL_QUERY_PARAM,
  buildKbEvalLobbyPath,
  buildKbEvalLobbySearchParams,
  deriveChunkTrialSearchQuery,
  parseKbEvalDeepLink,
} from './kbEvalLobbyLink'

describe('kbEvalLobbyLink FR-C-301', () => {
  it('deriveChunkTrialSearchQuery 优先 boost 首词', () => {
    expect(
      deriveChunkTrialSearchQuery({ boostKeywords: 'alpha, beta', text: 'long body' }),
    ).toBe('alpha')
  })

  it('deriveChunkTrialSearchQuery 无 boost 时截取正文', () => {
    expect(deriveChunkTrialSearchQuery({ text: '  hello   world  ', maxTextLen: 5 })).toBe('hello')
  })

  it('buildKbEvalLobbySearchParams 含 panel/prefill/workspace', () => {
    const params = buildKbEvalLobbySearchParams({
      prefillQuery: '测试 query',
      workspaceId: 42,
    })
    expect(params.get('panel')).toBe('eval')
    expect(params.get(KB_EVAL_PREFILL_QUERY_PARAM)).toBe('测试 query')
    expect(params.get('workspace_id')).toBe('42')
  })

  it('trial_clip 无 prefill 时标记剪贴板降级', () => {
    const params = buildKbEvalLobbySearchParams({ trialClip: true, workspaceId: 1 })
    expect(params.get(KB_EVAL_PREFILL_QUERY_PARAM)).toBeNull()
    expect(params.get('trial_clip')).toBe('1')
    expect(buildKbEvalLobbyPath({ trialClip: true })).toBe('/?panel=eval&trial_clip=1')
  })

  it('parseKbEvalDeepLink 往返', () => {
    const params = buildKbEvalLobbySearchParams({ prefillQuery: 'q', workspaceId: 3, trialClip: false })
    const parsed = parseKbEvalDeepLink(params)
    expect(parsed).toEqual({ prefillQuery: 'q', workspaceId: 3, trialClip: false })
  })
})
