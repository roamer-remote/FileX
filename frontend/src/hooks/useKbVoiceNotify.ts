import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { KbIndexWsEvent } from '@/hooks/useKbIndexWebSocket'
import {
  createKbVoiceNotifyState,
  START_INTENTS,
  TERMINAL_INTENTS,
  type VoiceIntentKey,
} from '@/lib/kbVoiceNotify'
import { kbVoiceDebugPush } from '@/lib/kbVoiceDebug'
import {
  cancelKbVoice,
  expireStaleKbVoice,
  isSpeechSynthesisAvailable,
  KB_VOICE_PLAYBACK_DEFAULT_TTL_SECONDS,
  registerKbVoiceUnlockListeners,
  speakText,
} from '@/lib/kbVoiceSpeak'
import { getUserPreferences } from '@/api/settings'
import { registerKbVoiceNotifyState, teardownKbVoiceNotify } from '@/lib/kbVoiceNotifyLifecycle'
import { useSystemSettingsStore } from '@/stores/systemSettingsStore'
import { useFilesStore } from '@/stores/filesStore'

function parseVoiceNotifyEnabled(raw: unknown): boolean | null {
  if (raw === undefined || raw === null) return null
  return raw === true || String(raw).toLowerCase() === 'true'
}

const SINGLE_KEYS: Record<VoiceIntentKey, string> = {
  extract_start: 'voiceNotify.extractStart',
  extract_done: 'voiceNotify.extractDone',
  extract_failed: 'voiceNotify.extractFailed',
  index_start: 'voiceNotify.indexStart',
  index_done: 'voiceNotify.indexDone',
  index_failed: 'voiceNotify.indexFailed',
}

const MANY_KEYS: Record<VoiceIntentKey, string> = {
  extract_start: 'voiceNotify.extractStartMany',
  extract_done: 'voiceNotify.extractDoneMany',
  extract_failed: 'voiceNotify.extractFailedMany',
  index_start: 'voiceNotify.indexStartMany',
  index_done: 'voiceNotify.indexDoneMany',
  index_failed: 'voiceNotify.indexFailedMany',
}

function voiceDurationSeconds(avgDurationMs: number): number {
  return Math.max(1, Math.round(avgDurationMs / 1000))
}

const SINGLE_DURATION_KEYS: Partial<Record<VoiceIntentKey, string>> = {
  extract_done: 'voiceNotify.extractDoneDuration',
  extract_failed: 'voiceNotify.extractFailedDuration',
  index_done: 'voiceNotify.indexDoneDuration',
  index_failed: 'voiceNotify.indexFailedDuration',
}

const MANY_DURATION_KEYS: Partial<Record<VoiceIntentKey, string>> = {
  extract_done: 'voiceNotify.extractDoneManyDuration',
  extract_failed: 'voiceNotify.extractFailedManyDuration',
  index_done: 'voiceNotify.indexDoneManyDuration',
  index_failed: 'voiceNotify.indexFailedManyDuration',
}

export function useKbVoiceNotify() {
  const { i18n, t } = useTranslation()
  const storeEnabled = useSystemSettingsStore((s) => s.kb_voice_notify_enabled ?? true)
  const storePlaybackTtl = useSystemSettingsStore(
    (s) => s.kb_voice_notify_playback_ttl_seconds ?? KB_VOICE_PLAYBACK_DEFAULT_TTL_SECONDS,
  )
  const [prefEnabled, setPrefEnabled] = useState<boolean | null>(null)
  const [prefPlaybackTtl, setPrefPlaybackTtl] = useState<number | null>(null)
  const enabled = prefEnabled ?? storeEnabled
  const enabledRef = useRef(enabled)
  enabledRef.current = enabled
  const tRef = useRef(t)
  tRef.current = t
  const langRef = useRef(i18n.language)
  langRef.current = i18n.language
  const playbackTtlSecondsRef = useRef<number>(storePlaybackTtl)
  playbackTtlSecondsRef.current = prefPlaybackTtl ?? storePlaybackTtl

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const res = await getUserPreferences({ skipErrorToast: true })
        if (!cancelled) {
          setPrefEnabled(parseVoiceNotifyEnabled(res.data.effective.kb_voice_notify_enabled))
          const ttlRaw = res.data.effective.kb_voice_notify_playback_ttl_seconds
          const ttlNum = typeof ttlRaw === 'number' ? ttlRaw : Number(ttlRaw)
          setPrefPlaybackTtl(
            Number.isFinite(ttlNum) && ttlNum >= 1 && ttlNum <= 3600 ? Math.round(ttlNum) : null,
          )
        }
      } catch {
        if (!cancelled) {
          setPrefEnabled(null)
          setPrefPlaybackTtl(null)
        }
      }
    }
    void load()
    const onChanged = () => {
      void load()
    }
    window.addEventListener('filex:user-settings-changed', onChanged)
    window.addEventListener('filex:system-settings-changed', onChanged)
    return () => {
      cancelled = true
      window.removeEventListener('filex:user-settings-changed', onChanged)
      window.removeEventListener('filex:system-settings-changed', onChanged)
    }
  }, [])

  const stateRef = useRef<ReturnType<typeof createKbVoiceNotifyState> | null>(null)
  if (!stateRef.current) {
    stateRef.current = createKbVoiceNotifyState({
      onSpeak: (payload) => {
        if (!enabledRef.current || !isSpeechSynthesisAvailable()) return
        kbVoiceDebugPush('debounce_fire', {
          key: payload.key,
          count: payload.count,
          avgDurationMs: payload.avgDurationMs,
        })
        const useDuration =
          payload.avgDurationMs != null && TERMINAL_INTENTS.has(payload.key)
        const seconds = useDuration ? voiceDurationSeconds(payload.avgDurationMs!) : undefined
        let i18nKey: string
        if (useDuration) {
          i18nKey =
            payload.count > 1
              ? MANY_DURATION_KEYS[payload.key] ?? MANY_KEYS[payload.key]
              : SINGLE_DURATION_KEYS[payload.key] ?? SINGLE_KEYS[payload.key]
        } else {
          i18nKey = payload.count > 1 ? MANY_KEYS[payload.key] : SINGLE_KEYS[payload.key]
        }
        speakText(tRef.current(i18nKey, { count: payload.count, seconds }), langRef.current, {
          queueKind: START_INTENTS.has(payload.key) ? 'start' : 'default',
          ttlSeconds: playbackTtlSecondsRef.current,
        })
      },
    })
  }

  useEffect(() => {
    const unregister = registerKbVoiceNotifyState(stateRef.current!)
    return () => {
      unregister()
      teardownKbVoiceNotify()
    }
  }, [])

  useEffect(() => {
    if (!enabled) {
      cancelKbVoice()
      stateRef.current?.reset()
      return
    }
    const files = useFilesStore.getState().files
    for (const file of files) {
      stateRef.current?.seedSnapshot({
        file_id: file.id,
        extract_status: file.extract_status,
        index_status: file.index_status,
      })
    }
    const unsubscribe = useFilesStore.subscribe((state, prev) => {
      const prevById = new Map(prev.files.map((file) => [file.id, file]))
      for (const file of state.files) {
        const prevFile = prevById.get(file.id)
        if (!prevFile) {
          stateRef.current?.seedSnapshot({
            file_id: file.id,
            extract_status: file.extract_status,
            index_status: file.index_status,
          })
          kbVoiceDebugPush('voice_seed_file', {
            file_id: file.id,
            extract_status: file.extract_status,
            index_status: file.index_status,
          })
          continue
        }
        if (
          prevFile.extract_status !== file.extract_status ||
          prevFile.index_status !== file.index_status
        ) {
          stateRef.current?.syncSnapshotFromStore({
            file_id: file.id,
            extract_status: file.extract_status,
            index_status: file.index_status,
          })
        }
      }
    })
    const removeUnlock = registerKbVoiceUnlockListeners()
    return () => {
      unsubscribe()
      removeUnlock()
    }
  }, [enabled])

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        // Drop any speech that aged out while the tab was hidden before we resume the
        // debounce timers; otherwise the browser-native TTS queue can replay old utterances.
        expireStaleKbVoice()
      }
      stateRef.current?.setDocumentHidden(document.hidden)
    }
    onVisibility()
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])

  const dispatchVoiceEvent = useCallback((event: KbIndexWsEvent) => {
    if (!enabledRef.current || !isSpeechSynthesisAvailable()) return
    kbVoiceDebugPush('voice_dispatch', {
      file_id: event.file_id,
      extract_status: event.extract_status,
      index_status: event.index_status,
      processing_duration_ms: event.processing_duration_ms,
    })
    stateRef.current?.handleEvent({
      file_id: event.file_id,
      extract_status: event.extract_status,
      index_status: event.index_status,
      processing_duration_ms: event.processing_duration_ms,
      notify_type: event.type,
    })
  }, [])

  const handleKbIndexWsEvent = useCallback(
    (event: KbIndexWsEvent) => {
      dispatchVoiceEvent(event)
    },
    [dispatchVoiceEvent],
  )

  return handleKbIndexWsEvent
}
