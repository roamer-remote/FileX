import { describe, expect, it } from 'vitest'
import { shouldAbortWechatPoll, WECHAT_POLL_FAIL_THRESHOLD } from '@/lib/wechatPollFailure'

describe('wechatPollFailure', () => {
  it('aborts at threshold', () => {
    expect(WECHAT_POLL_FAIL_THRESHOLD).toBe(5)
    expect(shouldAbortWechatPoll(4)).toBe(false)
    expect(shouldAbortWechatPoll(5)).toBe(true)
    expect(shouldAbortWechatPoll(6)).toBe(true)
  })
})
