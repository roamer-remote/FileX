import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchEventSource } from './fetchEventSource'

vi.mock('@/api/index', () => ({
  getStorageToken: () => 'jwt-test-token',
}))

describe('fetchEventSource', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses fetch with Authorization header instead of EventSource', async () => {
    const encoder = new TextEncoder()
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"type":"event"}\n\n'))
        controller.close()
      },
    })

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      body,
    })
    vi.stubGlobal('fetch', fetchMock)

    const seen: unknown[] = []
    await fetchEventSource('/api/agent-runs/run-1/stream', {
      onEvent: (data) => seen.push(data),
    })

    expect(fetchMock).toHaveBeenCalledOnce()
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init?.headers).toMatchObject({
      Authorization: 'Bearer jwt-test-token',
      Accept: 'text/event-stream',
    })
    expect(seen).toEqual([{ type: 'event' }])
  })
})
