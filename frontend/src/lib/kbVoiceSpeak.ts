import { kbVoiceDebugPush } from '@/lib/kbVoiceDebug'

let unlocked = false
let unlockListenerAttached = false

const UNLOCK_EVENTS = ['pointerdown', 'keydown', 'click', 'touchstart'] as const
const QUEUE_MAX = 5
const VOICES_TIMEOUT_MS = 3000
const CHROME_RESUME_MS = 800
export const KB_VOICE_PLAYBACK_DEFAULT_TTL_SECONDS = 120
export const KB_VOICE_PLAYBACK_TTL_SECONDS_MIN = 1
export const KB_VOICE_PLAYBACK_TTL_SECONDS_MAX = 3600

export type SpeakTextOptions = {
  queueKind?: 'start' | 'default'
  ttlSeconds?: number
}

type QueueItem = {
  text: string
  locale: string
  queueKind: 'start' | 'default'
  createdAt: number
  expiresAt: number
  ttlSeconds: number
}

let queue: QueueItem[] = []
let browserItems: QueueItem[] = []
let browserPendingCount = 0
let resumeInterval: ReturnType<typeof setInterval> | null = null
let cancelGeneration = 0
let expireTimer: ReturnType<typeof setTimeout> | null = null

function clampTtlSeconds(raw: number | undefined): number {
  if (!Number.isFinite(raw)) return KB_VOICE_PLAYBACK_DEFAULT_TTL_SECONDS
  const n = Math.round(Number(raw))
  if (n < KB_VOICE_PLAYBACK_TTL_SECONDS_MIN) return KB_VOICE_PLAYBACK_TTL_SECONDS_MIN
  if (n > KB_VOICE_PLAYBACK_TTL_SECONDS_MAX) return KB_VOICE_PLAYBACK_TTL_SECONDS_MAX
  return n
}

function clearExpireTimer(): void {
  if (expireTimer != null) {
    clearTimeout(expireTimer)
    expireTimer = null
  }
}

function earliestExpiresAt(): number | null {
  let min: number | null = null
  for (const item of queue) {
    if (min === null || item.expiresAt < min) min = item.expiresAt
  }
  for (const item of browserItems) {
    if (min === null || item.expiresAt < min) min = item.expiresAt
  }
  return min
}

function scheduleExpireTimer(): void {
  clearExpireTimer()
  const target = earliestExpiresAt()
  if (target === null) return
  const delay = Math.max(0, target - Date.now())
  expireTimer = setTimeout(() => {
    expireTimer = null
    expireStaleKbVoice()
  }, delay)
}

export function isSpeechSynthesisAvailable(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

function primeSpeechSynthesis(): void {
  const synth = window.speechSynthesis
  synth.getVoices()
  if (typeof synth.resume === 'function') {
    synth.resume()
  }
}

function clearChromeResumeLoop(): void {
  if (resumeInterval != null) {
    clearInterval(resumeInterval)
    resumeInterval = null
  }
}

/** Chrome 会在后台暂停 speechSynthesis，周期性 resume 避免队列卡住 */
function ensureChromeResumeLoop(): void {
  if (resumeInterval != null || !isSpeechSynthesisAvailable()) return
  resumeInterval = setInterval(() => {
    if (!isSpeechSynthesisAvailable()) {
      clearChromeResumeLoop()
      return
    }
    const synth = window.speechSynthesis
    if (browserPendingCount <= 0 && queue.length === 0 && !synth.speaking && !synth.pending) {
      clearChromeResumeLoop()
      return
    }
    try {
      synth.resume()
    } catch {
      /* ignore */
    }
  }, CHROME_RESUME_MS)
}

export function unlockKbVoice(): void {
  if (unlocked || !isSpeechSynthesisAvailable()) return
  unlocked = true
  try {
    primeSpeechSynthesis()
    const utterance = new SpeechSynthesisUtterance('.')
    utterance.volume = 0
    window.speechSynthesis.speak(utterance)
  } catch {
    /* ignore */
  }
}

export function registerKbVoiceUnlockListeners(): () => void {
  if (unlockListenerAttached || typeof window === 'undefined') {
    return () => {}
  }
  unlockListenerAttached = true

  const onUnlock = () => {
    unlockKbVoice()
    if (unlocked) {
      for (const ev of UNLOCK_EVENTS) {
        window.removeEventListener(ev, onUnlock, true)
      }
    }
  }

  for (const ev of UNLOCK_EVENTS) {
    window.addEventListener(ev, onUnlock, { capture: true, once: false })
  }

  return () => {
    for (const ev of UNLOCK_EVENTS) {
      window.removeEventListener(ev, onUnlock, true)
    }
    unlockListenerAttached = false
  }
}

function onBrowserUtteranceDone(
  generation: number,
  item: QueueItem,
  kind: 'end' | 'error',
): void {
  if (generation !== cancelGeneration) return
  const idx = browserItems.indexOf(item)
  if (idx >= 0) browserItems.splice(idx, 1)
  browserPendingCount = Math.max(0, browserPendingCount - 1)
  kbVoiceDebugPush(kind === 'end' ? 'speak_end' : 'speak_error', { len: item.text.length })
  scheduleExpireTimer()
}

/** 将内部队列一次性交给浏览器 speechSynthesis 原生队列，不再等 onend 再 drain */
function flushToBrowser(): void {
  if (!isSpeechSynthesisAvailable() || queue.length === 0) return
  primeSpeechSynthesis()
  ensureChromeResumeLoop()
  const synth = window.speechSynthesis

  while (queue.length > 0) {
    const item = queue.shift()!
    const generation = cancelGeneration
    browserItems.push(item)
    browserPendingCount += 1

    const utterance = new SpeechSynthesisUtterance(item.text)
    utterance.lang = item.locale.startsWith('zh') ? 'zh-CN' : 'en-US'
    utterance.rate = 1.05

    const onDone = () => onBrowserUtteranceDone(generation, item, 'end')
    const onErr = () => onBrowserUtteranceDone(generation, item, 'error')
    utterance.onend = onDone
    utterance.onerror = onErr

    kbVoiceDebugPush('speak_start', { len: item.text.length, queueKind: item.queueKind })
    synth.speak(utterance)
  }
  scheduleExpireTimer()
}

function enqueueSpeak(
  text: string,
  locale: string,
  queueKind: 'start' | 'default',
  ttlSeconds?: number,
): void {
  while (queue.length + browserPendingCount >= QUEUE_MAX) {
    const startIdx = queue.findIndex((item) => item.queueKind === 'start')
    if (startIdx >= 0) {
      queue.splice(startIdx, 1)
      kbVoiceDebugPush('queue_overflow', { dropped: 'start' })
      continue
    }
    if (queue.length > 0) {
      queue.shift()
      kbVoiceDebugPush('queue_overflow', { dropped: 'oldest' })
      continue
    }
    kbVoiceDebugPush('queue_overflow', { dropped: 'incoming' })
    return
  }
  const ttl = clampTtlSeconds(ttlSeconds)
  const now = Date.now()
  const item: QueueItem = {
    text,
    locale,
    queueKind,
    createdAt: now,
    expiresAt: now + ttl * 1000,
    ttlSeconds: ttl,
  }
  queue.push(item)
  kbVoiceDebugPush('speak_enqueue', {
    queueKind,
    waiting: queue.length,
    browserPending: browserPendingCount,
    ttlSeconds: ttl,
  })
  scheduleExpireTimer()
  flushToBrowser()
}

function speakWithVoices(
  text: string,
  locale: string,
  queueKind: 'start' | 'default',
  ttlSeconds?: number,
): void {
  const synth = window.speechSynthesis
  const voices = synth.getVoices()
  if (voices.length === 0) {
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      synth.removeEventListener('voiceschanged', onVoicesChanged)
      clearTimeout(fallbackTimer)
      enqueueSpeak(text, locale, queueKind, ttlSeconds)
    }
    const onVoicesChanged = () => finish()
    const fallbackTimer = setTimeout(finish, VOICES_TIMEOUT_MS)
    synth.addEventListener('voiceschanged', onVoicesChanged)
    synth.getVoices()
    return
  }
  enqueueSpeak(text, locale, queueKind, ttlSeconds)
}

export function speakText(text: string, locale: string, options?: SpeakTextOptions): void {
  if (!text.trim() || !isSpeechSynthesisAvailable()) return
  try {
    if (!unlocked) {
      unlockKbVoice()
    }
    const queueKind = options?.queueKind === 'start' ? 'start' : 'default'
    speakWithVoices(text, locale, queueKind, options?.ttlSeconds)
  } catch {
    /* ignore */
  }
}

export function expireStaleKbVoice(): void {
  const now = Date.now()
  const hasStale =
    queue.some((item) => item.expiresAt <= now) ||
    browserItems.some((item) => item.expiresAt <= now)
  if (!hasStale) return
  const waiting = queue.length + browserItems.length
  const browserPending = browserPendingCount
  const sample = queue[0] ?? browserItems[0]
  const ttl = sample?.ttlSeconds ?? KB_VOICE_PLAYBACK_DEFAULT_TTL_SECONDS
  cancelKbVoice()
  kbVoiceDebugPush('speak_expired_drop', {
    waiting,
    browserPending,
    ttlSeconds: ttl,
  })
}

export function cancelKbVoice(): void {
  cancelGeneration += 1
  browserPendingCount = 0
  queue = []
  browserItems = []
  clearChromeResumeLoop()
  clearExpireTimer()
  if (!isSpeechSynthesisAvailable()) return
  try {
    window.speechSynthesis.cancel()
  } catch {
    /* ignore */
  }
}

export function resetKbVoiceSpeakForTest(): void {
  unlocked = true
  unlockListenerAttached = false
  cancelKbVoice()
}

export function kbVoiceSpeakTestState(): {
  queueLength: number
  speaking: boolean
  browserPending: number
} {
  const synthSpeaking =
    isSpeechSynthesisAvailable() &&
    (window.speechSynthesis.speaking || window.speechSynthesis.pending)
  return {
    queueLength: queue.length,
    speaking: browserPendingCount > 0 || synthSpeaking,
    browserPending: browserPendingCount,
  }
}
