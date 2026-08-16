import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  cancelKbVoice,
  expireStaleKbVoice,
  kbVoiceSpeakTestState,
  resetKbVoiceSpeakForTest,
  speakText,
} from './kbVoiceSpeak'

type MockUtterance = {
  text: string
  lang: string
  rate: number
  onend: (() => void) | null
  onerror: (() => void) | null
}

function installSpeechMock(options?: { utteranceMs?: number }) {
  const utteranceMs = options?.utteranceMs ?? 0
  const speakCalls: string[] = []
  let cancelCalls = 0
  let browserSpeaking = false
  let pending = false

  class MockSpeechSynthesisUtterance {
    text: string
    lang = 'zh-CN'
    rate = 1
    volume = 1
    onend: (() => void) | null = null
    onerror: (() => void) | null = null

    constructor(text: string) {
      this.text = text
    }
  }

  const synth = {
    speak(utterance: MockUtterance) {
      speakCalls.push(utterance.text)
      browserSpeaking = true
      pending = false
      const finish = () => {
        browserSpeaking = false
        pending = false
        utterance.onend?.()
      }
      if (utteranceMs <= 0) {
        queueMicrotask(finish)
        return
      }
      setTimeout(finish, utteranceMs)
    },
    cancel() {
      cancelCalls += 1
      browserSpeaking = false
      pending = false
    },
    getVoices: () => [{ lang: 'zh-CN', name: 'mock' }],
    get pending() {
      return pending
    },
    get speaking() {
      return browserSpeaking
    },
    resume: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }

  vi.stubGlobal('SpeechSynthesisUtterance', MockSpeechSynthesisUtterance)
  vi.stubGlobal('window', { speechSynthesis: synth })

  return {
    get speakCalls() {
      return speakCalls
    },
    get cancelCalls() {
      return cancelCalls
    },
  }
}

describe('kbVoiceSpeak queue', () => {
  let mock: ReturnType<typeof installSpeechMock>

  beforeEach(() => {
    resetKbVoiceSpeakForTest()
    mock = installSpeechMock()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('hands consecutive utterances to browser synth without cancel', async () => {
    speakText('第一句', 'zh-CN')
    speakText('第二句', 'zh-CN')
    await Promise.resolve()
    expect(mock.speakCalls).toEqual(['第一句', '第二句'])
    expect(mock.cancelCalls).toBe(0)
  })

  it('does not wait for onend before speaking the next item', async () => {
    vi.useFakeTimers()
    resetKbVoiceSpeakForTest()
    const longMock = installSpeechMock({ utteranceMs: 2000 })

    speakText('笔记生成完成，耗时 12 秒', 'zh-CN')
    speakText('开始建立检索', 'zh-CN', { queueKind: 'start' })

    expect(longMock.speakCalls).toEqual(['笔记生成完成，耗时 12 秒', '开始建立检索'])
    expect(longMock.cancelCalls).toBe(0)

    vi.useRealTimers()
  })

  it('clears queue on cancelKbVoice', async () => {
    speakText('待播', 'zh-CN')
    cancelKbVoice()
    expect(kbVoiceSpeakTestState().queueLength).toBe(0)
    expect(kbVoiceSpeakTestState().browserPending).toBe(0)
  })

  it('drops oldest start item when queue overflows', () => {
    for (let i = 1; i <= 6; i += 1) {
      speakText(`start-${i}`, 'zh-CN', { queueKind: 'start' })
    }
    expect(mock.speakCalls.length).toBeLessThanOrEqual(5)
  })

  it('cancels all waiting speech when ttl expires', () => {
    vi.useFakeTimers()
    resetKbVoiceSpeakForTest()
    const ttlMock = installSpeechMock({ utteranceMs: 10_000 })
    speakText('第一句', 'zh-CN', { ttlSeconds: 2 })
    speakText('第二句', 'zh-CN', { ttlSeconds: 2 })
    vi.advanceTimersByTime(2_001)
    expect(ttlMock.cancelCalls).toBe(1)
    expect(kbVoiceSpeakTestState().queueLength).toBe(0)
    expect(kbVoiceSpeakTestState().browserPending).toBe(0)
    vi.useRealTimers()
  })

  it('drops stale browser speech on visible cleanup', () => {
    vi.useFakeTimers()
    resetKbVoiceSpeakForTest()
    const ttlMock = installSpeechMock({ utteranceMs: 10_000 })
    speakText('待播', 'zh-CN', { ttlSeconds: 2 })
    vi.advanceTimersByTime(2_001)
    expireStaleKbVoice()
    expect(ttlMock.cancelCalls).toBeGreaterThanOrEqual(1)
    expect(kbVoiceSpeakTestState().browserPending).toBe(0)
    vi.useRealTimers()
  })

  it('does not cancel a fresh utterance before its ttl', () => {
    vi.useFakeTimers()
    resetKbVoiceSpeakForTest()
    const freshMock = installSpeechMock({ utteranceMs: 10_000 })
    speakText('仍在 TTL 内', 'zh-CN', { ttlSeconds: 5 })
    vi.advanceTimersByTime(1_000)
    expect(freshMock.cancelCalls).toBe(0)
    expect(kbVoiceSpeakTestState().browserPending).toBe(1)
    vi.useRealTimers()
  })
})
