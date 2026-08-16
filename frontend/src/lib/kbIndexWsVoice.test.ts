import { describe, expect, it } from 'vitest'
import { shouldVoiceNotifyKbWsEvent } from '@/lib/kbIndexWsVoice'

describe('shouldVoiceNotifyKbWsEvent', () => {
  it('allows live WS events through to voice notify', () => {
    expect(shouldVoiceNotifyKbWsEvent({})).toBe(true)
    expect(shouldVoiceNotifyKbWsEvent({ _replay: false })).toBe(true)
  })

  it('blocks 054 connect replay events from voice notify', () => {
    expect(shouldVoiceNotifyKbWsEvent({ _replay: true })).toBe(false)
  })
})
