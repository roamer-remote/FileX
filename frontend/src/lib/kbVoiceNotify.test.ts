import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createKbVoiceNotifyState,
  detectDurationTerminalFallback,
  detectFastPathTerminalIntents,
  detectVoiceIntents,
  START_COOLDOWN_MS,
  START_DEBOUNCE_MS,
  TERMINAL_DURATION_HOLD_MS,
  VOICE_DEBOUNCE_MS,
  type SpeakPayload,
} from './kbVoiceNotify'

describe('detectVoiceIntents', () => {
  it('detects extract and index transitions including skipped', () => {
    expect(
      detectVoiceIntents({ extract: 'pending' }, { extract: 'extracting' }),
    ).toEqual(['extract_start'])
    expect(
      detectVoiceIntents({ extract: 'extracting' }, { extract: 'ready' }),
    ).toEqual(['extract_done'])
    expect(
      detectVoiceIntents({ extract: 'extracting' }, { extract: 'skipped' }),
    ).toEqual(['extract_done'])
    expect(
      detectVoiceIntents({ index: 'indexing' }, { index: 'skipped' }),
    ).toEqual(['index_done'])
  })
})

describe('detectFastPathTerminalIntents', () => {
  it('fires index_done when pending to ready without duration', () => {
    expect(
      detectFastPathTerminalIntents({ index: 'pending' }, { index: 'ready' }),
    ).toEqual(['index_done'])
  })

  it('does not duplicate extracting to ready', () => {
    expect(
      detectFastPathTerminalIntents({ extract: 'extracting' }, { extract: 'ready' }),
    ).toEqual([])
  })
})

describe('detectDurationTerminalFallback', () => {
  it('fires index_done when pending to ready with duration', () => {
    expect(
      detectDurationTerminalFallback(
        { index: 'pending' },
        { index: 'ready' },
        1500,
        'index',
      ),
    ).toEqual(['index_done'])
  })

  it('does not fire without duration', () => {
    expect(
      detectDurationTerminalFallback({ index: 'pending' }, { index: 'ready' }, undefined, 'index'),
    ).toEqual([])
  })

  it('does not repeat when already terminal', () => {
    expect(
      detectDurationTerminalFallback(
        { index: 'ready' },
        { index: 'ready' },
        1500,
        'index',
      ),
    ).toEqual([])
  })
})

describe('createKbVoiceNotifyState', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function setup(onSpeak: (p: SpeakPayload) => void) {
    return createKbVoiceNotifyState({
      debounceMs: VOICE_DEBOUNCE_MS,
      startCooldownMs: START_COOLDOWN_MS,
      onSpeak,
    })
  }

  it('seeds first event without speaking', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, extract_status: 'extracting' })
    vi.advanceTimersByTime(START_DEBOUNCE_MS + 100)
    expect(speaks).toEqual([])
  })

  it('debounces merged counts for same intent', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, index_status: 'indexing' })
    state.handleEvent({ file_id: 1, index_status: 'ready' })
    state.handleEvent({ file_id: 2, index_status: 'indexing' })
    state.handleEvent({ file_id: 2, index_status: 'ready' })
    state.handleEvent({ file_id: 3, index_status: 'indexing' })
    state.handleEvent({ file_id: 3, index_status: 'ready' })
    vi.advanceTimersByTime(VOICE_DEBOUNCE_MS)
    expect(speaks).toEqual([{ key: 'index_done', count: 3 }])
  })

  it('suppresses repeated index_start within cooldown', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, index_status: 'pending' })
    state.handleEvent({ file_id: 1, index_status: 'indexing' })
    state.handleEvent({ file_id: 1, index_status: 'pending' })
    state.handleEvent({ file_id: 1, index_status: 'indexing' })
    vi.advanceTimersByTime(START_DEBOUNCE_MS)
    expect(speaks.filter((s) => s.key === 'index_start')).toEqual([{ key: 'index_start', count: 1 }])
  })

  it('suppresses repeated extract_start within cooldown', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, extract_status: 'pending' })
    state.handleEvent({ file_id: 1, extract_status: 'extracting' })
    state.handleEvent({ file_id: 1, extract_status: 'pending' })
    state.handleEvent({ file_id: 1, extract_status: 'extracting' })
    vi.advanceTimersByTime(START_DEBOUNCE_MS)
    expect(speaks.filter((s) => s.key === 'extract_start')).toEqual([
      { key: 'extract_start', count: 1 },
    ])
  })

  it('fires extract_done before index_start when both debounce in same batch', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, extract_status: 'pending', index_status: 'pending' })
    state.handleEvent({ file_id: 1, extract_status: 'extracting', index_status: 'pending' })
    vi.advanceTimersByTime(START_DEBOUNCE_MS)
    state.handleEvent({ file_id: 1, extract_status: 'ready', index_status: 'indexing' })
    expect(speaks.map((s) => s.key)).toEqual(['extract_start'])
    vi.advanceTimersByTime(TERMINAL_DURATION_HOLD_MS)
    expect(speaks.map((s) => s.key)).toEqual(['extract_start', 'extract_done'])
    vi.advanceTimersByTime(START_DEBOUNCE_MS)
    expect(speaks.map((s) => s.key)).toEqual(['extract_start', 'extract_done', 'index_start'])
  })

  it('fires extract_done and index_start in pipeline order', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, extract_status: 'extracting', index_status: 'pending' })
    state.handleEvent({ file_id: 1, extract_status: 'ready', index_status: 'indexing' })
    vi.advanceTimersByTime(TERMINAL_DURATION_HOLD_MS)
    expect(speaks.map((s) => s.key)).toEqual(['extract_done'])
    vi.advanceTimersByTime(START_DEBOUNCE_MS)
    expect(speaks.map((s) => s.key)).toEqual(['extract_done', 'index_start'])
  })

  it('keeps extract_done duration when pipeline flush waits for supplement', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, extract_status: 'extracting', index_status: 'pending' })
    state.handleEvent({
      file_id: 1,
      extract_status: 'ready',
      index_status: 'indexing',
      notify_type: 'kb_index_updated',
    })
    state.handleEvent({
      file_id: 1,
      extract_status: 'ready',
      index_status: 'indexing',
      processing_duration_ms: 6500,
      notify_type: 'kb_extract_updated',
    })
    vi.advanceTimersByTime(TERMINAL_DURATION_HOLD_MS)
    expect(speaks).toEqual([{ key: 'extract_done', count: 1, avgDurationMs: 6500 }])
    vi.advanceTimersByTime(START_DEBOUNCE_MS)
    expect(speaks.map((s) => s.key)).toEqual(['extract_done', 'index_start'])
  })

  it('pauses debounce while hidden and flushes after visible', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, extract_status: 'pending' })
    state.handleEvent({ file_id: 1, extract_status: 'extracting' })
    state.setDocumentHidden(true)
    vi.advanceTimersByTime(VOICE_DEBOUNCE_MS + 500)
    expect(speaks).toEqual([])
    state.setDocumentHidden(false)
    vi.advanceTimersByTime(START_DEBOUNCE_MS)
    expect(speaks).toEqual([{ key: 'extract_start', count: 1 }])
  })
  it('includes avgDurationMs for single done with duration', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, index_status: 'indexing' })
    state.handleEvent({ file_id: 1, index_status: 'ready', processing_duration_ms: 2500 })
    vi.advanceTimersByTime(START_DEBOUNCE_MS)
    expect(speaks).toEqual([{ key: 'index_done', count: 1, avgDurationMs: 2500 }])
  })

  it('averages duration across merged done events', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, index_status: 'indexing' })
    state.handleEvent({ file_id: 1, index_status: 'ready', processing_duration_ms: 2000 })
    state.handleEvent({ file_id: 2, index_status: 'indexing' })
    state.handleEvent({ file_id: 2, index_status: 'ready', processing_duration_ms: 4000 })
    vi.advanceTimersByTime(VOICE_DEBOUNCE_MS)
    expect(speaks).toEqual([{ key: 'index_done', count: 2, avgDurationMs: 3000 }])
  })

  it('omits avgDurationMs when duration missing', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, index_status: 'indexing' })
    state.handleEvent({ file_id: 1, index_status: 'ready' })
    vi.advanceTimersByTime(TERMINAL_DURATION_HOLD_MS)
    expect(speaks).toEqual([{ key: 'index_done', count: 1 }])
  })

  it('uses partial average when only some events have duration', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, index_status: 'indexing' })
    state.handleEvent({ file_id: 1, index_status: 'ready', processing_duration_ms: 2000 })
    state.handleEvent({ file_id: 2, index_status: 'indexing' })
    state.handleEvent({ file_id: 2, index_status: 'ready' })
    vi.advanceTimersByTime(VOICE_DEBOUNCE_MS)
    expect(speaks).toEqual([{ key: 'index_done', count: 2, avgDurationMs: 2000 }])
  })

  it('uses duration fallback when indexing ws was missed', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, index_status: 'pending' })
    state.handleEvent({
      file_id: 1,
      index_status: 'ready',
      processing_duration_ms: 1800,
    })
    vi.advanceTimersByTime(START_DEBOUNCE_MS)
    expect(speaks).toEqual([{ key: 'index_done', count: 1, avgDurationMs: 1800 }])
  })

  it('seedSnapshot does not trigger speak on unchanged status', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.seedSnapshot({ file_id: 1, index_status: 'indexing' })
    state.handleEvent({ file_id: 1, index_status: 'indexing' })
    vi.advanceTimersByTime(VOICE_DEBOUNCE_MS)
    expect(speaks).toEqual([])
  })

  it('supplements extract_done duration when index notify precedes extract notify', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, extract_status: 'extracting', index_status: 'pending' })
    state.handleEvent({
      file_id: 1,
      extract_status: 'ready',
      index_status: 'pending',
      notify_type: 'kb_index_updated',
    })
    state.handleEvent({
      file_id: 1,
      extract_status: 'ready',
      index_status: 'pending',
      processing_duration_ms: 8200,
      notify_type: 'kb_extract_updated',
    })
    vi.advanceTimersByTime(START_DEBOUNCE_MS)
    expect(speaks).toEqual([
      { key: 'extract_done', count: 1, avgDurationMs: 8200 },
    ])
  })

  it('supplements index_done duration when terminal index notify precedes duration notify', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.seedSnapshot({ file_id: 1, extract_status: 'ready', index_status: 'ready' })
    state.syncSnapshotFromStore({ file_id: 1, extract_status: 'ready', index_status: 'pending' })
    state.handleEvent({
      file_id: 1,
      extract_status: 'ready',
      index_status: 'indexing',
      notify_type: 'kb_index_updated',
    })
    state.handleEvent({
      file_id: 1,
      extract_status: 'ready',
      index_status: 'ready',
      notify_type: 'kb_index_updated',
    })
    state.handleEvent({
      file_id: 1,
      extract_status: 'ready',
      index_status: 'ready',
      processing_duration_ms: 5600,
      notify_type: 'kb_index_updated',
    })
    vi.advanceTimersByTime(START_DEBOUNCE_MS)
    expect(speaks.filter((s) => s.key === 'index_start')).toEqual([{ key: 'index_start', count: 1 }])
    expect(speaks.find((s) => s.key === 'index_done')).toEqual({
      key: 'index_done',
      count: 1,
      avgDurationMs: 5600,
    })
  })

  it('fires index_done on fast path when indexing ws was skipped and no duration', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, extract_status: 'pending', index_status: 'pending' })
    state.handleEvent({ file_id: 1, extract_status: 'extracting', index_status: 'pending' })
    state.handleEvent({ file_id: 1, extract_status: 'ready', index_status: 'ready' })
    vi.advanceTimersByTime(TERMINAL_DURATION_HOLD_MS * 2 + START_DEBOUNCE_MS)
    expect(speaks.find((s) => s.key === 'index_done')).toEqual({
      key: 'index_done',
      count: 1,
    })
  })

  it('syncSnapshotFromStore does not swallow forward progress before handleEvent', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.seedSnapshot({ file_id: 1, extract_status: 'pending', index_status: 'pending' })
    state.handleEvent({ file_id: 1, extract_status: 'extracting', index_status: 'pending' })
    state.syncSnapshotFromStore({
      file_id: 1,
      extract_status: 'ready',
      index_status: 'ready',
    })
    state.handleEvent({ file_id: 1, extract_status: 'ready', index_status: 'ready' })
    vi.advanceTimersByTime(START_DEBOUNCE_MS)
    expect(speaks.filter((s) => s.key === 'extract_start')).toEqual([
      { key: 'extract_start', count: 1 },
    ])
    vi.advanceTimersByTime(TERMINAL_DURATION_HOLD_MS)
    expect(speaks.find((s) => s.key === 'extract_done')).toEqual({
      key: 'extract_done',
      count: 1,
    })
    vi.advanceTimersByTime(TERMINAL_DURATION_HOLD_MS)
    expect(speaks.find((s) => s.key === 'index_done')).toEqual({
      key: 'index_done',
      count: 1,
    })
  })

  it('reextract reset clears start cooldown so extract_start can replay', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.handleEvent({ file_id: 1, extract_status: 'pending', index_status: 'pending' })
    state.handleEvent({ file_id: 1, extract_status: 'extracting', index_status: 'pending' })
    vi.advanceTimersByTime(START_DEBOUNCE_MS)
    state.handleEvent({ file_id: 1, extract_status: 'ready', index_status: 'ready' })
    state.syncSnapshotFromStore({
      file_id: 1,
      extract_status: 'pending',
      index_status: 'pending',
    })
    state.handleEvent({ file_id: 1, extract_status: 'extracting', index_status: 'pending' })
    vi.advanceTimersByTime(START_DEBOUNCE_MS)
    expect(speaks.filter((s) => s.key === 'extract_start')).toHaveLength(2)
  })

  it('syncSnapshotFromStore still applies reextract reset from store', () => {
    const speaks: SpeakPayload[] = []
    const state = setup((p) => speaks.push(p))
    state.seedSnapshot({ file_id: 1, extract_status: 'ready', index_status: 'ready' })
    state.syncSnapshotFromStore({
      file_id: 1,
      extract_status: 'ready',
      index_status: 'pending',
    })
    state.handleEvent({
      file_id: 1,
      extract_status: 'ready',
      index_status: 'indexing',
      notify_type: 'kb_index_updated',
    })
    state.handleEvent({
      file_id: 1,
      extract_status: 'ready',
      index_status: 'ready',
      notify_type: 'kb_index_updated',
    })
    vi.advanceTimersByTime(TERMINAL_DURATION_HOLD_MS + START_DEBOUNCE_MS)
    expect(speaks.filter((s) => s.key === 'index_start')).toEqual([{ key: 'index_start', count: 1 }])
    expect(speaks.find((s) => s.key === 'index_done')).toEqual({
      key: 'index_done',
      count: 1,
    })
  })

})

