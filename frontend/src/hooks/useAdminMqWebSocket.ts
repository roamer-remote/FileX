import { useCallback, useEffect, useRef, useState } from 'react'
import { getStorageToken } from '@/api/index'
import { handleWebSocketClose } from '@/utils/wsClient'
import { wsApiUrl, wsAuthFrame } from '@/utils/wsAuth'
import type { MqStatusPayload } from '@/api/admin'

export type MqStatusWsEvent = MqStatusPayload & {
  type: 'mq_status_updated'
}

function stripEvent(event: MqStatusWsEvent): MqStatusPayload {
  const { type: _t, ...rest } = event
  return rest
}

export function useAdminMqWebSocket(enabled: boolean) {
  const [data, setData] = useState<MqStatusPayload | null>(null)
  const [lastReceivedAt, setLastReceivedAt] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const retryMs = useRef(1000)

  const requestRefresh = useCallback(() => {
    const ws = wsRef.current
    if (ws?.readyState === WebSocket.OPEN) {
      setRefreshing(true)
      ws.send('refresh')
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    const token = getStorageToken()
    if (!token) {
      setLoading(false)
      return
    }

    let closed = false
    let retryTimer: ReturnType<typeof setTimeout> | undefined

    const connect = () => {
      if (closed) return
      setLoading(true)
      const url = wsApiUrl('/api/ws/mq-status')
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        ws.send(wsAuthFrame(token))
        retryMs.current = 1000
      }

      ws.onmessage = (ev) => {
        try {
          const parsed = JSON.parse(String(ev.data)) as MqStatusWsEvent
          if (parsed?.type !== 'mq_status_updated') return
          setData(stripEvent(parsed))
          setLastReceivedAt(parsed.updated_at || new Date().toISOString())
          setLoading(false)
          setRefreshing(false)
        } catch {
          /* ignore */
        }
      }

      ws.onclose = (ev) => {
        wsRef.current = null
        if (closed) return
        if (handleWebSocketClose(ev.code) !== 'retry') return
        retryTimer = setTimeout(() => {
          retryMs.current = Math.min(retryMs.current * 2, 30_000)
          connect()
        }, retryMs.current)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      closed = true
      if (retryTimer) clearTimeout(retryTimer)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [enabled])

  return { data, loading, refreshing, requestRefresh, lastReceivedAt }
}
