import { useEffect, useRef } from 'react'
import { getStorageToken } from '@/api/index'
import type { FileItem } from '@/api/files'
import { useFilesStore } from '@/stores/filesStore'
import { handleWebSocketClose } from '@/utils/wsClient'
import { useKbVoiceNotify } from '@/hooks/useKbVoiceNotify'
import { wsApiUrl, wsAuthFrame } from '@/utils/wsAuth'
import { kbVoiceDebugPush } from '@/lib/kbVoiceDebug'
import { shouldVoiceNotifyKbWsEvent } from '@/lib/kbIndexWsVoice'
import { listNeedsKbStatusPoll } from '@/lib/kbStatusPoll'

export type KbIndexWsEvent = {
  type: 'kb_index_updated' | 'kb_extract_updated' | 'kb_post_updated'
  file_id: number
  /** 054 连接补发；仅 UI patch，不触发语音 */
  _replay?: boolean
  index_status?: string
  chunk_count?: number
  index_error?: string | null
  kb_post_status?: string
  kb_post_error?: string | null
  extract_status?: string
  extract_error?: string | null
  extracted_at?: string | null
  extract_engine?: string | null
  has_md?: boolean
  md_has_content?: boolean
  preview_mime_type?: string | null
  processing_duration_ms?: number
}

const KB_WS_EVENT_TYPES = new Set(['kb_index_updated', 'kb_extract_updated', 'kb_post_updated'])

function pickDefinedPatch<K extends keyof FileItem>(
  patch: Partial<Pick<FileItem, K>>,
): Partial<Pick<FileItem, K>> {
  const out: Partial<Pick<FileItem, K>> = {}
  for (const key of Object.keys(patch) as K[]) {
    const value = patch[key]
    if (value !== undefined) {
      out[key] = value
    }
  }
  return out
}

export function useKbIndexWebSocket(enabled: boolean) {
  const patchFileIndex = useFilesStore((s) => s.patchFileIndex)
  const handleVoiceNotify = useKbVoiceNotify()
  const retryMs = useRef(1000)

  useEffect(() => {
    if (!enabled) return
    const token = getStorageToken()
    if (!token) return

    let ws: WebSocket | null = null
    let closed = false
    let retryTimer: ReturnType<typeof setTimeout> | undefined

    const connect = () => {
      if (closed) return
      const url = wsApiUrl('/api/ws/kb-index')
      ws = new WebSocket(url)
      ws.onopen = () => {
        ws?.send(wsAuthFrame(token))
        retryMs.current = 1000
        const files = useFilesStore.getState().files
        if (listNeedsKbStatusPoll(files)) {
          void useFilesStore.getState().loadFiles({ silent: true })
        }
      }
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(String(ev.data)) as KbIndexWsEvent
          if (!data?.type || !KB_WS_EVENT_TYPES.has(data.type) || typeof data.file_id !== 'number') return
          kbVoiceDebugPush('ws_received', {
            file_id: data.file_id,
            type: data.type,
            index_status: data.index_status,
            extract_status: data.extract_status,
            processing_duration_ms: data.processing_duration_ms,
            replay: data._replay === true,
          })
          // 必须先走语音状态机，再 patch store；否则 subscribe 里的 syncSnapshotFromStore
          // 会抢先更新快照，handleEvent 看到 prev===next 而漏掉后续 intent。
          if (shouldVoiceNotifyKbWsEvent(data)) {
            handleVoiceNotify(data)
          }
          patchFileIndex(
            data.file_id,
            pickDefinedPatch({
              index_status: data.index_status,
              chunk_count: data.chunk_count,
              index_error: data.index_error ?? null,
              kb_post_status: data.kb_post_status,
              kb_post_error: data.kb_post_error ?? null,
              extract_status: data.extract_status,
              extract_error: data.extract_error ?? null,
              extracted_at: data.extracted_at,
              extract_engine: data.extract_engine,
              has_md: data.has_md,
              md_has_content: data.md_has_content,
              preview_mime_type: data.preview_mime_type,
            }),
          )
        } catch {
          /* ignore */
        }
      }
      ws.onclose = (ev) => {
        if (closed) return
        if (handleWebSocketClose(ev.code) !== 'retry') return
        retryTimer = setTimeout(() => {
          retryMs.current = Math.min(retryMs.current * 2, 30_000)
          connect()
        }, retryMs.current)
      }
      ws.onerror = () => {
        ws?.close()
      }
    }

    connect()
    return () => {
      closed = true
      if (retryTimer) clearTimeout(retryTimer)
      ws?.close()
    }
  }, [enabled, patchFileIndex, handleVoiceNotify])
}
