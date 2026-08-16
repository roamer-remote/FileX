export type VoiceIntentKey =
  | 'extract_start'
  | 'extract_done'
  | 'extract_failed'
  | 'index_start'
  | 'index_done'
  | 'index_failed'

export type KbWsNotifyType = 'kb_extract_updated' | 'kb_index_updated' | 'kb_post_updated'

export type KbWsStatusSlice = {
  file_id: number
  extract_status?: string
  index_status?: string
  processing_duration_ms?: number
  notify_type?: KbWsNotifyType
}

export type SpeakPayload = {
  key: VoiceIntentKey
  count: number
  avgDurationMs?: number
}

export const VOICE_DEBOUNCE_MS = 2000
export const START_DEBOUNCE_MS = 400
/** 终态首包无 duration 时多等一会，等后续 WS 补录耗时 */
export const TERMINAL_DURATION_HOLD_MS = 1500
export const START_COOLDOWN_MS = 30_000

export const TERMINAL_INTENTS: ReadonlySet<VoiceIntentKey> = new Set([
  'extract_done',
  'extract_failed',
  'index_done',
  'index_failed',
])

export const START_INTENTS: ReadonlySet<VoiceIntentKey> = new Set([
  'extract_start',
  'index_start',
])

/** 播报固定顺序：1 开始提取 → 2 提取完成 → 3 开始索引 → 4 索引完成 */
export const VOICE_INTENT_PIPELINE_ORDER: readonly VoiceIntentKey[] = [
  'extract_start',
  'extract_done',
  'extract_failed',
  'index_start',
  'index_failed',
  'index_done',
]

export function pipelineRank(key: VoiceIntentKey): number {
  const rank = VOICE_INTENT_PIPELINE_ORDER.indexOf(key)
  return rank < 0 ? VOICE_INTENT_PIPELINE_ORDER.length : rank
}

export type FileSnapshot = {
  extract?: string
  index?: string
  extractDurationMs?: number
  indexDurationMs?: number
}

type DebounceBucket = {
  count: number
  durationTotalMs: number
  durationCount: number
  timerId: ReturnType<typeof setTimeout> | null
}

export type KbVoiceNotifyState = {
  handleEvent: (event: KbWsStatusSlice) => void
  seedSnapshot: (event: KbWsStatusSlice) => void
  syncSnapshotFromStore: (event: KbWsStatusSlice) => void
  setDocumentHidden: (hidden: boolean) => void
  reset: () => void
}

type CreateOptions = {
  debounceMs?: number
  startCooldownMs?: number
  onSpeak: (payload: SpeakPayload) => void
  now?: () => number
  schedule?: (fn: () => void, ms: number) => ReturnType<typeof setTimeout>
  cancelSchedule?: (id: ReturnType<typeof setTimeout>) => void
}

function mergeSnapshot(
  prev: FileSnapshot | undefined,
  event: KbWsStatusSlice,
): FileSnapshot {
  const next: FileSnapshot = {
    extract: event.extract_status ?? prev?.extract,
    index: event.index_status ?? prev?.index,
    extractDurationMs: prev?.extractDurationMs,
    indexDurationMs: prev?.indexDurationMs,
  }
  if (!isValidDurationMs(event.processing_duration_ms)) {
    return next
  }
  const ms = event.processing_duration_ms!
  if (event.notify_type === 'kb_extract_updated') {
    next.extractDurationMs = ms
  } else if (event.notify_type === 'kb_index_updated') {
    next.indexDurationMs = ms
  } else {
    next.extractDurationMs = ms
    next.indexDurationMs = ms
  }
  return next
}

function durationForIntent(intent: VoiceIntentKey, snapshot: FileSnapshot): number | undefined {
  if (intent === 'extract_done' || intent === 'extract_failed') {
    return snapshot.extractDurationMs
  }
  if (intent === 'index_done' || intent === 'index_failed') {
    return snapshot.indexDurationMs
  }
  return undefined
}

export function isAxisTerminal(status?: string): boolean {
  return status === 'ready' || status === 'skipped' || status === 'failed'
}

export function isValidDurationMs(ms: number | undefined): boolean {
  return typeof ms === 'number' && Number.isFinite(ms) && ms >= 0
}

export function detectVoiceIntents(
  prev: FileSnapshot | undefined,
  next: FileSnapshot,
): VoiceIntentKey[] {
  if (!prev) return []

  const intents: VoiceIntentKey[] = []
  const prevExtract = prev.extract
  const nextExtract = next.extract
  const prevIndex = prev.index
  const nextIndex = next.index

  if (prevExtract !== 'extracting' && nextExtract === 'extracting') {
    intents.push('extract_start')
  }
  if (prevExtract === 'extracting' && (nextExtract === 'ready' || nextExtract === 'skipped')) {
    intents.push('extract_done')
  }
  if (prevExtract === 'extracting' && nextExtract === 'failed') {
    intents.push('extract_failed')
  }

  if (prevIndex !== 'indexing' && nextIndex === 'indexing') {
    intents.push('index_start')
  }
  if (prevIndex === 'indexing' && (nextIndex === 'ready' || nextIndex === 'skipped')) {
    intents.push('index_done')
  }
  if (prevIndex === 'indexing' && nextIndex === 'failed') {
    intents.push('index_failed')
  }

  return intents
}

/** 快路径：跳过 extracting/indexing 中间态直接终态（无 duration 时也需播报） */
export function detectFastPathTerminalIntents(
  prev: FileSnapshot,
  next: FileSnapshot,
): VoiceIntentKey[] {
  const intents: VoiceIntentKey[] = []
  const prevExtract = prev.extract
  const nextExtract = next.extract
  const prevIndex = prev.index
  const nextIndex = next.index

  if (
    prevExtract !== 'extracting' &&
    !isAxisTerminal(prevExtract) &&
    isAxisTerminal(nextExtract)
  ) {
    intents.push(nextExtract === 'failed' ? 'extract_failed' : 'extract_done')
  }
  if (prevIndex !== 'indexing' && !isAxisTerminal(prevIndex) && isAxisTerminal(nextIndex)) {
    intents.push(nextIndex === 'failed' ? 'index_failed' : 'index_done')
  }
  return intents
}

export function detectDurationTerminalFallback(
  prev: FileSnapshot,
  next: FileSnapshot,
  durationMs: number | undefined,
  axis: 'extract' | 'index',
): VoiceIntentKey[] {
  if (!isValidDurationMs(durationMs)) return []

  if (axis === 'extract') {
    if (!isAxisTerminal(prev.extract) && isAxisTerminal(next.extract)) {
      return [next.extract === 'failed' ? 'extract_failed' : 'extract_done']
    }
    return []
  }

  if (!isAxisTerminal(prev.index) && isAxisTerminal(next.index)) {
    return [next.index === 'failed' ? 'index_failed' : 'index_done']
  }
  return []
}

function mergeVoiceIntents(prev: FileSnapshot, next: FileSnapshot): VoiceIntentKey[] {
  const merged = [...detectVoiceIntents(prev, next)]
  const append = (intent: VoiceIntentKey) => {
    if (!merged.includes(intent)) merged.push(intent)
  }
  for (const intent of detectFastPathTerminalIntents(prev, next)) {
    append(intent)
  }
  for (const intent of detectDurationTerminalFallback(
    prev,
    next,
    next.extractDurationMs,
    'extract',
  )) {
    append(intent)
  }
  for (const intent of detectDurationTerminalFallback(
    prev,
    next,
    next.indexDurationMs,
    'index',
  )) {
    append(intent)
  }
  return merged
}

function isStartIntent(key: VoiceIntentKey): boolean {
  return START_INTENTS.has(key)
}

function isTerminalIntent(key: VoiceIntentKey): boolean {
  return TERMINAL_INTENTS.has(key)
}

function terminalIntentForAxis(
  axis: 'extract' | 'index',
  status?: string,
): VoiceIntentKey | null {
  if (!isAxisTerminal(status)) return null
  if (axis === 'extract') {
    return status === 'failed' ? 'extract_failed' : 'extract_done'
  }
  return status === 'failed' ? 'index_failed' : 'index_done'
}

function isReextractReset(prev: FileSnapshot, next: FileSnapshot): boolean {
  const extractReset =
    isAxisTerminal(prev.extract) &&
    (next.extract === 'pending' || next.extract === 'extracting')
  const indexReset =
    isAxisTerminal(prev.index) && (next.index === 'pending' || next.index === 'indexing')
  return extractReset || indexReset
}

export function createKbVoiceNotifyState(options: CreateOptions): KbVoiceNotifyState {
  const debounceMs = options.debounceMs ?? VOICE_DEBOUNCE_MS
  const startCooldownMs = options.startCooldownMs ?? START_COOLDOWN_MS
  const onSpeak = options.onSpeak
  const now = options.now ?? (() => Date.now())
  const schedule = options.schedule ?? ((fn, ms) => setTimeout(fn, ms))
  const cancelSchedule = options.cancelSchedule ?? ((id) => clearTimeout(id))

  const fileSnapshots = new Map<number, FileSnapshot>()
  const debounceBuckets = new Map<VoiceIntentKey, DebounceBucket>()
  const lastStartAt = new Map<string, number>()
  let documentHidden = false

  const ensureBucket = (key: VoiceIntentKey): DebounceBucket => {
    let bucket = debounceBuckets.get(key)
    if (!bucket) {
      bucket = { count: 0, durationTotalMs: 0, durationCount: 0, timerId: null }
      debounceBuckets.set(key, bucket)
    }
    return bucket
  }

  const fireBucket = (key: VoiceIntentKey) => {
    const bucket = debounceBuckets.get(key)
    if (!bucket || bucket.count <= 0) return
    const count = bucket.count
    const avgDurationMs =
      bucket.durationCount > 0 ? bucket.durationTotalMs / bucket.durationCount : undefined
    bucket.count = 0
    bucket.durationTotalMs = 0
    bucket.durationCount = 0
    bucket.timerId = null
    onSpeak({
      key,
      count,
      ...(avgDurationMs != null ? { avgDurationMs } : {}),
    })
  }

  const bucketDelayMs = (key: VoiceIntentKey, bucket: DebounceBucket): number => {
    if (isStartIntent(key)) return START_DEBOUNCE_MS
    if (isTerminalIntent(key)) {
      if (bucket.durationCount > 0) return START_DEBOUNCE_MS
      if (bucket.count === 1) return TERMINAL_DURATION_HOLD_MS
    }
    return debounceMs
  }

  const scheduleBucket = (key: VoiceIntentKey, pipelineWaitMs = 0) => {
    if (documentHidden) return
    const bucket = ensureBucket(key)
    if (bucket.timerId != null) {
      cancelSchedule(bucket.timerId)
    }
    bucket.timerId = schedule(
      () => fireBucket(key),
      bucketDelayMs(key, bucket) + pipelineWaitMs,
    )
  }

  const pauseAllTimers = () => {
    for (const bucket of debounceBuckets.values()) {
      if (bucket.timerId != null) {
        cancelSchedule(bucket.timerId)
        bucket.timerId = null
      }
    }
  }

  const resumeAllTimers = () => {
    for (const [key, bucket] of debounceBuckets.entries()) {
      if (bucket.count > 0) {
        scheduleBucket(key)
      }
    }
  }

  /** @returns 后续 intent 须额外等待的毫秒数（prior 终态无 duration 时保留 hold 窗口） */
  const flushPendingIntent = (key: VoiceIntentKey, forPipeline: boolean): number => {
    const bucket = debounceBuckets.get(key)
    if (!bucket || bucket.count <= 0 || bucket.timerId == null) return 0
    cancelSchedule(bucket.timerId)
    bucket.timerId = null

    if (bucket.durationCount > 0) {
      fireBucket(key)
      return 0
    }

    if (forPipeline && isTerminalIntent(key)) {
      bucket.timerId = schedule(() => fireBucket(key), TERMINAL_DURATION_HOLD_MS)
      return TERMINAL_DURATION_HOLD_MS
    }

    fireBucket(key)
    return 0
  }

  /** 后续 intent 入队前，先处理 pipeline 中仍在 debounce 的前序 intent */
  const flushPriorPipelineIntents = (key: VoiceIntentKey): number => {
    let pipelineWaitMs = 0
    const rank = pipelineRank(key)
    for (let i = 0; i < rank; i += 1) {
      const waitMs = flushPendingIntent(VOICE_INTENT_PIPELINE_ORDER[i], true)
      pipelineWaitMs = Math.max(pipelineWaitMs, waitMs)
    }
    return pipelineWaitMs
  }

  const enqueueIntent = (key: VoiceIntentKey, durationMs?: number) => {
    const pipelineWaitMs = flushPriorPipelineIntents(key)
    const bucket = ensureBucket(key)
    bucket.count += 1
    if (isTerminalIntent(key) && isValidDurationMs(durationMs)) {
      bucket.durationTotalMs += durationMs!
      bucket.durationCount += 1
    }
    scheduleBucket(key, pipelineWaitMs)
  }

  /** 终态 intent 已入 debounce 桶但首包 WS 无 duration 时，后续 WS 补录 */
  const supplementPendingTerminalDuration = (
    key: VoiceIntentKey | null,
    durationMs?: number,
  ) => {
    if (!key || !isValidDurationMs(durationMs)) return
    const bucket = debounceBuckets.get(key)
    if (!bucket || bucket.count <= 0 || bucket.timerId == null) return
    if (bucket.durationCount > 0) return
    bucket.durationTotalMs += durationMs!
    bucket.durationCount += 1
    if (bucket.timerId != null) {
      cancelSchedule(bucket.timerId)
      bucket.timerId = schedule(() => fireBucket(key), START_DEBOUNCE_MS)
    }
  }

  const applySnapshot = (event: KbWsStatusSlice) => {
    if (typeof event.file_id !== 'number') return
    const prev = fileSnapshots.get(event.file_id)
    const next = mergeSnapshot(prev, event)
    if (!prev) {
      fileSnapshots.set(event.file_id, next)
      return null
    }
    fileSnapshots.set(event.file_id, next)
    return { prev, next }
  }

  const shouldSuppressStart = (fileId: number, key: VoiceIntentKey): boolean => {
    const mapKey = `${fileId}:${key}`
    const last = lastStartAt.get(mapKey)
    const ts = now()
    if (last != null && ts - last < startCooldownMs) {
      return true
    }
    lastStartAt.set(mapKey, ts)
    return false
  }

  const seedSnapshot = (event: KbWsStatusSlice) => {
    if (typeof event.file_id !== 'number') return
    if (fileSnapshots.has(event.file_id)) return
    fileSnapshots.set(event.file_id, mergeSnapshot(undefined, event))
  }

  const clearStartCooldownForFile = (fileId: number) => {
    lastStartAt.delete(`${fileId}:extract_start`)
    lastStartAt.delete(`${fileId}:index_start`)
  }

  const applyReextractSnapshotReset = (fileId: number, prev: FileSnapshot, next: FileSnapshot) => {
    clearStartCooldownForFile(fileId)
    if (isAxisTerminal(prev.extract) && (next.extract === 'pending' || next.extract === 'extracting')) {
      next.extractDurationMs = undefined
    }
    if (isAxisTerminal(prev.index) && (next.index === 'pending' || next.index === 'indexing')) {
      next.indexDurationMs = undefined
    }
    fileSnapshots.set(fileId, next)
  }

  return {
    handleEvent(event: KbWsStatusSlice) {
      const applied = applySnapshot(event)
      if (!applied) return

      const { prev, next } = applied
      const intents = mergeVoiceIntents(prev, next)
      for (const intent of intents) {
        if (isStartIntent(intent) && shouldSuppressStart(event.file_id, intent)) {
          continue
        }
        enqueueIntent(intent, durationForIntent(intent, next))
      }

      supplementPendingTerminalDuration(
        terminalIntentForAxis('extract', next.extract),
        next.extractDurationMs,
      )
      supplementPendingTerminalDuration(
        terminalIntentForAxis('index', next.index),
        next.indexDurationMs,
      )
    },

    seedSnapshot,

    syncSnapshotFromStore(event: KbWsStatusSlice) {
      if (typeof event.file_id !== 'number') return
      const prev = fileSnapshots.get(event.file_id)
      if (!prev) {
        fileSnapshots.set(event.file_id, mergeSnapshot(undefined, event))
        return
      }
      const next = mergeSnapshot(prev, event)
      if (
        (prev.extract !== next.extract || prev.index !== next.index) &&
        !isReextractReset(prev, next)
      ) {
        return
      }
      if (isReextractReset(prev, next)) {
        applyReextractSnapshotReset(event.file_id, prev, next)
        return
      }
      fileSnapshots.set(event.file_id, next)
    },

    setDocumentHidden(hidden: boolean) {
      if (documentHidden === hidden) return
      documentHidden = hidden
      if (hidden) {
        pauseAllTimers()
        return
      }
      resumeAllTimers()
    },

    reset() {
      pauseAllTimers()
      fileSnapshots.clear()
      debounceBuckets.clear()
      lastStartAt.clear()
    },
  }
}
