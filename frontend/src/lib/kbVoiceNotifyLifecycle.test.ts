import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createKbVoiceNotifyState } from '@/lib/kbVoiceNotify'
import {
  registerKbVoiceNotifyState,
  teardownKbVoiceNotify,
} from '@/lib/kbVoiceNotifyLifecycle'
import { kbVoiceSpeakTestState, resetKbVoiceSpeakForTest, speakText } from '@/lib/kbVoiceSpeak'

function installSpeechMock() {
  class MockSpeechSynthesisUtterance {
    text: string
    lang = 'zh-CN'
    rate = 1
    onend: (() => void) | null = null
    onerror: (() => void) | null = null

    constructor(text: string) {
      this.text = text
    }
  }

  const synth = {
    speak(utterance: MockSpeechSynthesisUtterance) {
      queueMicrotask(() => utterance.onend?.())
    },
    cancel: vi.fn(),
    getVoices: () => [{ lang: 'zh-CN', name: 'mock' }],
    get pending() {
      return false
    },
    get speaking() {
      return false
    },
    resume: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }

  vi.stubGlobal('SpeechSynthesisUtterance', MockSpeechSynthesisUtterance)
  vi.stubGlobal('window', { speechSynthesis: synth })
}

describe('kbVoiceNotifyLifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    resetKbVoiceSpeakForTest()
    installSpeechMock()
  })

  afterEach(() => {
    teardownKbVoiceNotify()
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('teardown clears speech queue and pending debounce timers', () => {
    const onSpeak = vi.fn()
    const state = createKbVoiceNotifyState({ onSpeak })
    const unregister = registerKbVoiceNotifyState(state)

    state.handleEvent({
      file_id: 1,
      extract_status: 'pending',
      index_status: 'pending',
    })
    state.handleEvent({
      file_id: 1,
      extract_status: 'extracting',
      index_status: 'pending',
      notify_type: 'kb_extract_updated',
    })

    speakText('待播', 'zh-CN')
    teardownKbVoiceNotify()

    expect(kbVoiceSpeakTestState().queueLength).toBe(0)
    vi.advanceTimersByTime(10_000)
    expect(onSpeak).not.toHaveBeenCalled()

    unregister()
  })
})
