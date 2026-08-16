/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  DEFAULT_EXTRACT_ASSET_HYDRATE_CONCURRENCY,
  EXTRACT_ASSET_PLACEHOLDER_SRC,
  createConcurrencyLimiter,
  hydrateExtractAssetImages,
  parseExtractAssetKeyFromApiSrc,
} from '@/utils/extractAssetHydration'

vi.mock('@/api/files', () => ({
  signExtractAssets: vi.fn(),
}))

import { signExtractAssets } from '@/api/files'

const signExtractAssetsMock = vi.mocked(signExtractAssets)

class MockResizeObserver {
  static lastInstance: MockResizeObserver | null = null
  private readonly callback: ResizeObserverCallback
  private readonly targets = new Set<Element>()

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
    MockResizeObserver.lastInstance = this
  }

  observe(target: Element) {
    this.targets.add(target)
  }

  disconnect() {
    this.targets.clear()
  }

  trigger() {
    const entries = Array.from(this.targets).map(
      (target) =>
        ({
          target,
          contentRect: target.getBoundingClientRect(),
        }) as ResizeObserverEntry,
    )
    if (entries.length > 0) {
      this.callback(entries, this as unknown as ResizeObserver)
    }
  }
}

class MockIntersectionObserver {
  static lastInstance: MockIntersectionObserver | null = null
  private readonly callback: IntersectionObserverCallback
  private readonly targets = new Set<Element>()

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback
    MockIntersectionObserver.lastInstance = this
  }

  observe(target: Element) {
    this.targets.add(target)
  }

  unobserve(target: Element) {
    this.targets.delete(target)
  }

  disconnect() {
    this.targets.clear()
  }

  flushAllVisible() {
    this.flushVisible(Array.from(this.targets))
  }

  flushVisible(targets: Element[]) {
    const visible = new Set(targets)
    const entries = Array.from(this.targets)
      .filter((target) => visible.has(target))
      .map(
        (target) =>
          ({
            target,
            isIntersecting: true,
            intersectionRatio: 1,
          }) as IntersectionObserverEntry,
      )
    if (entries.length > 0) {
      this.callback(entries, this as unknown as IntersectionObserver)
    }
  }
}

class MockMutationObserver {
  static instances: MockMutationObserver[] = []
  private readonly callback: MutationCallback
  private readonly targets = new Set<Node>()

  constructor(callback: MutationCallback) {
    this.callback = callback
    MockMutationObserver.instances.push(this)
  }

  observe(target: Node) {
    this.targets.add(target)
  }

  disconnect() {
    this.targets.clear()
  }

  trigger(target: Node) {
    if (!this.targets.has(target)) return
    this.callback(
      [
        {
          type: 'childList',
          target,
          addedNodes: target.childNodes,
          removedNodes: [] as unknown as NodeList,
          previousSibling: null,
          nextSibling: null,
          attributeName: null,
          attributeNamespace: null,
          oldValue: null,
        } as MutationRecord,
      ],
      this as unknown as MutationObserver,
    )
  }
}

function makeExtractAssetImg(fileId: number, index: number): HTMLImageElement {
  const img = document.createElement('img')
  img.src = `/api/files/${fileId}/extract-assets/img-${index}.jpg`
  return img
}

function mockSignResponse(fileId: number, keys: string[]) {
  const expiresAt = Math.floor(Date.now() / 1000) + 1800
  return {
    data: {
      expires_at: expiresAt,
      items: keys.map((key) => ({
        asset_key: key,
        url: `/api/files/signed-extract-assets/mock.${key}`,
        expires_at: expiresAt,
      })),
    },
  } as Awaited<ReturnType<typeof signExtractAssets>>
}

describe('parseExtractAssetKeyFromApiSrc', () => {
  it('extracts asset key from legacy preview URL', () => {
    expect(parseExtractAssetKeyFromApiSrc('/api/files/347/extract-assets/foo%20bar.jpg')).toBe(
      'foo bar.jpg',
    )
  })
})

describe('createConcurrencyLimiter', () => {
  it('limits concurrent executions', async () => {
    const limiter = createConcurrencyLimiter(2)
    let inFlight = 0
    let maxInFlight = 0
    const gate = { open: false }

    for (let i = 0; i < 4; i += 1) {
      limiter.enqueue(async () => {
        inFlight += 1
        maxInFlight = Math.max(maxInFlight, inFlight)
        while (!gate.open) {
          await new Promise((r) => window.setTimeout(r, 5))
        }
        inFlight -= 1
      })
    }

    await vi.waitFor(() => expect(limiter.activeCount).toBe(2))
    expect(maxInFlight).toBe(2)
    gate.open = true
    await vi.waitFor(() => expect(limiter.activeCount).toBe(0))
    expect(maxInFlight).toBeLessThanOrEqual(2)
  })
})

describe('hydrateExtractAssetImages', () => {
  beforeEach(() => {
    vi.stubGlobal('IntersectionObserver', MockIntersectionObserver)
    vi.stubGlobal('ResizeObserver', MockResizeObserver)
    vi.stubGlobal('MutationObserver', MockMutationObserver)
    MockMutationObserver.instances = []
    signExtractAssetsMock.mockReset()
    signExtractAssetsMock.mockImplementation(async (_fileId, keys) => mockSignResponse(347, keys))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('eager-loads all images when count is within eagerMax (modal flex layout)', async () => {
    const root = document.createElement('div')
    for (let i = 0; i < 15; i += 1) root.appendChild(makeExtractAssetImg(389, i))
    document.body.appendChild(root)

    const cleanup = hydrateExtractAssetImages(root, { fileId: 389, maxConcurrent: 6 })
    await vi.waitFor(() => expect(signExtractAssetsMock).toHaveBeenCalled(), { timeout: 3000 })
    await vi.waitFor(
      () =>
        expect(
          Array.from(root.querySelectorAll('img')).every((img) =>
            (img.getAttribute('src') || '').includes('/signed-extract-assets/'),
          ),
        ).toBe(true),
      { timeout: 3000 },
    )
    cleanup()
    document.body.removeChild(root)
  })

  it('replaces placeholder with signed src and keeps sign in-flight bounded', async () => {
    let inFlight = 0
    let maxInFlight = 0
    signExtractAssetsMock.mockImplementation(async (_fileId, keys) => {
      inFlight += 1
      maxInFlight = Math.max(maxInFlight, inFlight)
      await new Promise((r) => window.setTimeout(r, 20))
      inFlight -= 1
      return mockSignResponse(347, keys)
    })

    const root = document.createElement('div')
    for (let i = 0; i < 20; i += 1) root.appendChild(makeExtractAssetImg(347, i))
    document.body.appendChild(root)

    const cleanup = hydrateExtractAssetImages(root, { fileId: 347, maxConcurrent: 6, eagerMax: 0 })
    for (const img of root.querySelectorAll('img')) {
      expect(img.getAttribute('src')).toContain('/api/files/347/extract-assets/')
    }

    MockIntersectionObserver.lastInstance?.flushAllVisible()
    await vi.waitFor(() => expect(signExtractAssetsMock.mock.calls.length).toBeGreaterThan(0), {
      timeout: 3000,
    })
    await vi.waitFor(
      () =>
        expect(
          Array.from(root.querySelectorAll('img')).every((img) =>
            (img.getAttribute('src') || '').includes('/signed-extract-assets/'),
          ),
        ).toBe(true),
      { timeout: 3000 },
    )
    expect(maxInFlight).toBeLessThanOrEqual(6)
    cleanup()
    document.body.removeChild(root)
  })

  it('keeps already visible legacy image src when signing fails', async () => {
    signExtractAssetsMock.mockRejectedValueOnce(new Error('sign failed'))
    const root = document.createElement('div')
    const img = makeExtractAssetImg(777, 0)
    const originalSrc = img.getAttribute('src')
    root.appendChild(img)
    document.body.appendChild(root)

    const cleanup = hydrateExtractAssetImages(root, { fileId: 777, maxConcurrent: 6, eagerMax: 0 })
    expect(img.getAttribute('src')).toBe(originalSrc)

    MockIntersectionObserver.lastInstance?.flushAllVisible()
    await vi.waitFor(() => expect(signExtractAssetsMock).toHaveBeenCalledTimes(1))
    await Promise.resolve()
    expect(img.getAttribute('src')).toBe(originalSrc)
    expect(img.dataset.extractAssetSigned).toBeUndefined()

    cleanup()
    document.body.removeChild(root)
  })

  it('falls back to visible legacy src when signed image load fails', async () => {
    const root = document.createElement('div')
    const img = makeExtractAssetImg(778, 0)
    const originalSrc = img.getAttribute('src')
    root.appendChild(img)
    document.body.appendChild(root)

    const cleanup = hydrateExtractAssetImages(root, { fileId: 778, maxConcurrent: 6, eagerMax: 0 })
    MockIntersectionObserver.lastInstance?.flushAllVisible()
    await vi.waitFor(() => expect(signExtractAssetsMock).toHaveBeenCalledTimes(1))
    await vi.waitFor(() =>
      expect(img.getAttribute('src')).toContain('/api/files/signed-extract-assets/'),
    )

    img.dispatchEvent(new Event('error'))

    expect(img.getAttribute('src')).toBe(originalSrc)
    expect(img.dataset.extractAssetSigned).toBeUndefined()

    cleanup()
    document.body.removeChild(root)
  })

  it('does not retry a signed url after it falls back to visible legacy src', async () => {
    const root = document.createElement('div')
    const img = makeExtractAssetImg(779, 0)
    const originalSrc = img.getAttribute('src')
    root.appendChild(img)
    document.body.appendChild(root)

    const cleanup = hydrateExtractAssetImages(root, { fileId: 779, maxConcurrent: 6, eagerMax: 0 })
    MockIntersectionObserver.lastInstance?.flushAllVisible()
    await vi.waitFor(() => expect(signExtractAssetsMock).toHaveBeenCalledTimes(1))
    await vi.waitFor(() =>
      expect(img.getAttribute('src')).toContain('/api/files/signed-extract-assets/'),
    )

    img.dispatchEvent(new Event('error'))
    expect(img.getAttribute('src')).toBe(originalSrc)
    expect(img.dataset.extractAssetFailed).toBe('1')

    MockResizeObserver.lastInstance?.trigger()
    await new Promise((resolve) => window.setTimeout(resolve, 20))

    expect(signExtractAssetsMock).toHaveBeenCalledTimes(1)
    expect(img.getAttribute('src')).toBe(originalSrc)

    cleanup()
    document.body.removeChild(root)
  })

  it('falls back to stored legacy src when placeholder signed image load fails', async () => {
    const root = document.createElement('div')
    const img = document.createElement('img')
    const fallbackSrc = '/api/files/367/extract-assets/invoice.jpg'
    img.src = EXTRACT_ASSET_PLACEHOLDER_SRC
    img.dataset.extractAssetKey = 'invoice.jpg'
    img.dataset.extractAssetFileId = '367'
    img.dataset.extractAssetFallbackSrc = fallbackSrc
    root.appendChild(img)
    document.body.appendChild(root)

    const cleanup = hydrateExtractAssetImages(root, { fileId: 389, maxConcurrent: 6, eagerMax: 0 })
    MockIntersectionObserver.lastInstance?.flushAllVisible()
    await vi.waitFor(() => expect(signExtractAssetsMock).toHaveBeenCalledTimes(1))
    await vi.waitFor(() =>
      expect(img.getAttribute('src')).toContain('/api/files/signed-extract-assets/'),
    )

    img.dispatchEvent(new Event('error'))

    expect(img.getAttribute('src')).toBe(fallbackSrc)
    expect(img.dataset.extractAssetSigned).toBeUndefined()
    expect(img.dataset.extractAssetFailed).toBe('1')

    cleanup()
    document.body.removeChild(root)
  })

  it('does not reuse a cached signed url after that url failed to load', async () => {
    const firstRoot = document.createElement('div')
    const firstImg = makeExtractAssetImg(780, 0)
    firstRoot.appendChild(firstImg)
    document.body.appendChild(firstRoot)

    const firstCleanup = hydrateExtractAssetImages(firstRoot, { fileId: 780, maxConcurrent: 6, eagerMax: 0 })
    MockIntersectionObserver.lastInstance?.flushAllVisible()
    await vi.waitFor(() => expect(signExtractAssetsMock).toHaveBeenCalledTimes(1))
    await vi.waitFor(() =>
      expect(firstImg.getAttribute('src')).toContain('/api/files/signed-extract-assets/'),
    )
    firstImg.dispatchEvent(new Event('error'))
    firstCleanup()
    document.body.removeChild(firstRoot)

    const secondRoot = document.createElement('div')
    const secondImg = makeExtractAssetImg(780, 0)
    secondRoot.appendChild(secondImg)
    document.body.appendChild(secondRoot)

    const secondCleanup = hydrateExtractAssetImages(secondRoot, { fileId: 780, maxConcurrent: 6, eagerMax: 0 })
    MockIntersectionObserver.lastInstance?.flushAllVisible()
    await vi.waitFor(() => expect(signExtractAssetsMock).toHaveBeenCalledTimes(2))

    secondCleanup()
    document.body.removeChild(secondRoot)
  })

  it('rehydrates images when React rewrites markdown DOM back to placeholders', async () => {
    const root = document.createElement('div')
    root.innerHTML =
      `<img src="${EXTRACT_ASSET_PLACEHOLDER_SRC}" data-extract-asset-file-id="367"` +
      ` data-extract-asset-fallback-src="/api/files/367/extract-assets/invoice.jpg"` +
      ` data-extract-asset-key="invoice.jpg" alt="invoice.jpg">`
    document.body.appendChild(root)

    const cleanup = hydrateExtractAssetImages(root, { fileId: 367, maxConcurrent: 6 })
    await vi.waitFor(() => expect(signExtractAssetsMock).toHaveBeenCalledTimes(1))
    await vi.waitFor(() =>
      expect(root.querySelector('img')?.getAttribute('src')).toContain(
        '/api/files/signed-extract-assets/',
      ),
    )

    root.innerHTML =
      `<img src="${EXTRACT_ASSET_PLACEHOLDER_SRC}" data-extract-asset-file-id="367"` +
      ` data-extract-asset-fallback-src="/api/files/367/extract-assets/invoice.jpg"` +
      ` data-extract-asset-key="invoice.jpg" alt="invoice.jpg">`
    MockMutationObserver.instances.forEach((observer) => observer.trigger(root))

    await vi.waitFor(() =>
      expect(root.querySelector('img')?.getAttribute('src')).toContain(
        '/api/files/signed-extract-assets/',
      ),
    )
    expect(signExtractAssetsMock).toHaveBeenCalledTimes(1)

    cleanup()
    document.body.removeChild(root)
  })

  it('signs each image with its embedded extract asset file id', async () => {
    const root = document.createElement('div')
    const img = makeExtractAssetImg(367, 0)
    img.dataset.extractAssetFileId = '367'
    root.appendChild(img)
    document.body.appendChild(root)

    const cleanup = hydrateExtractAssetImages(root, { fileId: 1001, maxConcurrent: 6, eagerMax: 0 })
    MockIntersectionObserver.lastInstance?.flushAllVisible()
    await vi.waitFor(() => expect(signExtractAssetsMock).toHaveBeenCalledTimes(1))

    expect(signExtractAssetsMock.mock.calls[0]?.[0]).toBe(367)

    cleanup()
    document.body.removeChild(root)
  })

  it('does not sign off-screen images until they intersect', async () => {
    const root = document.createElement('div')
    root.style.cssText = 'position:absolute;top:99999px;left:0;'
    const images = Array.from({ length: 10 }, (_, i) => makeExtractAssetImg(999, i))
    for (const img of images) root.appendChild(img)
    document.body.appendChild(root)

    const cleanup = hydrateExtractAssetImages(root, { fileId: 999, maxConcurrent: 6, eagerMax: 0 })
    expect(signExtractAssetsMock).not.toHaveBeenCalled()

    MockIntersectionObserver.lastInstance?.flushVisible([images[0], images[1]])
    await vi.waitFor(() => expect(signExtractAssetsMock).toHaveBeenCalledTimes(1))

    MockIntersectionObserver.lastInstance?.flushVisible([images[2]])
    await vi.waitFor(() => expect(signExtractAssetsMock).toHaveBeenCalledTimes(2))
    cleanup()
    document.body.removeChild(root)
  })

  it('aborts in-flight sign on cleanup', async () => {
    let finishSign: (() => void) | undefined
    signExtractAssetsMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          finishSign = () => resolve(mockSignResponse(1, ['img-0.jpg']))
        }),
    )

    const root = document.createElement('div')
    const img = makeExtractAssetImg(1, 0)
    root.appendChild(img)
    document.body.appendChild(root)

    const cleanup = hydrateExtractAssetImages(root, {
      fileId: 1,
      maxConcurrent: DEFAULT_EXTRACT_ASSET_HYDRATE_CONCURRENCY,
      eagerMax: 0,
    })
    MockIntersectionObserver.lastInstance?.flushAllVisible()
    await vi.waitFor(() => expect(signExtractAssetsMock).toHaveBeenCalledTimes(1))
    cleanup()
    finishSign?.()
    await Promise.resolve()
    expect(img.getAttribute('src')).toContain('/api/files/1/extract-assets/')
    document.body.removeChild(root)
  })
})
