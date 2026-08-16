import { getStorageToken } from '@/api/index'

export type FetchEventSourceHandlers = {
  onEvent: (data: unknown) => void
  onClose?: () => void
  onError?: (error: unknown) => void
}

/**
 * Fetch-based SSE reader with Authorization header (107: no native EventSource).
 */
export async function fetchEventSource(
  url: string,
  handlers: FetchEventSourceHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = getStorageToken()
  const headers: Record<string, string> = {
    Accept: 'text/event-stream',
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const response = await fetch(url, { headers, signal })
  if (!response.ok || !response.body) {
    throw new Error(`stream_failed:${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let splitAt = buffer.indexOf('\n\n')
      while (splitAt >= 0) {
        const chunk = buffer.slice(0, splitAt)
        buffer = buffer.slice(splitAt + 2)
        const dataLine = chunk
          .split('\n')
          .find((line) => line.startsWith('data:'))
        if (dataLine) {
          const raw = dataLine.slice(5).trim()
          if (raw) {
            try {
              handlers.onEvent(JSON.parse(raw))
            } catch (e) {
              handlers.onError?.(e)
            }
          }
        }
        if (chunk.includes('event: close')) {
          handlers.onClose?.()
          return
        }
        splitAt = buffer.indexOf('\n\n')
      }
    }
    handlers.onClose?.()
  } catch (e) {
    handlers.onError?.(e)
    throw e
  }
}
