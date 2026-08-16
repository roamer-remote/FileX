/** MinerU / Docling 笔记预览：extract-assets 懒加载 + batch signed URL，避免每张图 ACL 查库。 */

import { signExtractAssets } from '@/api/files'
import {
  EXTRACT_ASSET_PLACEHOLDER_SRC,
  parseExtractAssetFileIdFromApiSrc,
  parseExtractAssetKeyFromApiSrc,
} from '@/utils/extractAssetHtml'

export {
  EXTRACT_ASSET_PLACEHOLDER_SRC,
  parseExtractAssetFileIdFromApiSrc,
  parseExtractAssetKeyFromApiSrc,
  preprocessExtractAssetImgTags,
} from '@/utils/extractAssetHtml'

export const DEFAULT_EXTRACT_ASSET_HYDRATE_CONCURRENCY = 6
export const DEFAULT_EXTRACT_ASSET_SIGN_BATCH_SIZE = 64
/** MinerU 笔记图通常较少；弹窗 flex 首帧 0 高时 IO/可见性不可靠，<= 此值则 eager 签全部 */
export const DEFAULT_EXTRACT_ASSET_EAGER_MAX = 64

export type ExtractAssetHydrateOptions = {
  fileId: number
  maxConcurrent?: number
  signBatchSize?: number
  /** IntersectionObserver rootMargin，默认预加载视口外 200px */
  rootMargin?: string
  /** <= 此数量时跳过 IO 一次签全部；0 表示始终懒加载 */
  eagerMax?: number
}

type SignedUrlCacheEntry = {
  url: string
  expiresAt: number
}

const signedUrlCache = new Map<string, SignedUrlCacheEntry>()

export function getExtractAssetHydrateConcurrency(): number {
  const raw = import.meta.env.VITE_EXTRACT_ASSET_HYDRATE_CONCURRENCY
  if (raw == null || raw === '') return DEFAULT_EXTRACT_ASSET_HYDRATE_CONCURRENCY
  const parsed = Number.parseInt(String(raw), 10)
  if (!Number.isFinite(parsed) || parsed < 1) return DEFAULT_EXTRACT_ASSET_HYDRATE_CONCURRENCY
  return parsed
}

export function getExtractAssetSignBatchSize(): number {
  const raw = import.meta.env.VITE_EXTRACT_ASSET_SIGN_BATCH_SIZE
  if (raw == null || raw === '') return DEFAULT_EXTRACT_ASSET_SIGN_BATCH_SIZE
  const parsed = Number.parseInt(String(raw), 10)
  if (!Number.isFinite(parsed) || parsed < 1) return DEFAULT_EXTRACT_ASSET_SIGN_BATCH_SIZE
  return parsed
}

/** 有限并发任务队列（信号量） */
export function createConcurrencyLimiter(maxConcurrent: number) {
  let active = 0
  const pending: Array<() => Promise<void>> = []

  const pump = () => {
    while (active < maxConcurrent && pending.length > 0) {
      const task = pending.shift()!
      active += 1
      void task().finally(() => {
        active -= 1
        pump()
      })
    }
  }

  return {
    enqueue(task: () => Promise<void>) {
      pending.push(task)
      pump()
    },
    get activeCount() {
      return active
    },
    get pendingCount() {
      return pending.length
    },
  }
}

function cacheKey(fileId: number, assetKey: string): string {
  return `${fileId}:${assetKey}`
}

function isCachedSignedUrlValid(entry: SignedUrlCacheEntry | undefined): entry is SignedUrlCacheEntry {
  if (!entry) return false
  const now = Math.floor(Date.now() / 1000)
  return entry.expiresAt > now + 30
}

function rememberSignedUrls(fileId: number, items: Array<{ asset_key: string; url: string; expires_at: number }>) {
  for (const item of items) {
    signedUrlCache.set(cacheKey(fileId, item.asset_key), {
      url: item.url,
      expiresAt: item.expires_at,
    })
  }
}

async function signAssetKeys(
  fileId: number,
  assetKeys: string[],
  batchSize: number,
  signal?: AbortSignal,
): Promise<Map<string, string>> {
  const result = new Map<string, string>()
  const needSign: string[] = []

  for (const key of assetKeys) {
    const cached = signedUrlCache.get(cacheKey(fileId, key))
    if (isCachedSignedUrlValid(cached)) {
      result.set(key, cached.url)
    } else {
      needSign.push(key)
    }
  }

  for (let i = 0; i < needSign.length; i += batchSize) {
    if (signal?.aborted) {
      throw new DOMException('Aborted', 'AbortError')
    }
    const chunk = needSign.slice(i, i + batchSize)
    const res = await signExtractAssets(fileId, chunk, { signal })
    rememberSignedUrls(fileId, res.data.items)
    for (const item of res.data.items) {
      result.set(item.asset_key, item.url)
    }
  }

  return result
}

function findIntersectionRoot(contentRoot: HTMLElement): Element | null {
  let node: HTMLElement | null = contentRoot.parentElement
  while (node && node !== document.body) {
    const { overflowY } = getComputedStyle(node)
    if (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay') {
      // Modal/flex 首帧 scroll 容器常为 0 高，IO 永远不触发；回退 viewport。
      if (node.clientHeight > 0 && node.clientWidth > 0) {
        return node
      }
      return null
    }
    node = node.parentElement
  }
  return null
}

function isVisibleInScrollRoot(img: HTMLElement, scrollRoot: Element | null): boolean {
  const rect = img.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return false
  if (!scrollRoot) {
    return (
      rect.bottom > 0 &&
      rect.top < window.innerHeight &&
      rect.right > 0 &&
      rect.left < window.innerWidth
    )
  }
  const rootRect = scrollRoot.getBoundingClientRect()
  if (rootRect.height <= 0 || rootRect.width <= 0) return false
  return (
    rect.bottom > rootRect.top &&
    rect.top < rootRect.bottom &&
    rect.right > rootRect.left &&
    rect.left < rootRect.right
  )
}

function scheduleInitialVisibleLoad(
  images: Array<{ img: HTMLImageElement; key: string }>,
  scrollRoot: Element | null,
  loadBatch: (targets: HTMLImageElement[]) => void,
  disposed: () => boolean,
) {
  const run = () => {
    if (disposed()) return
    const visible = images.filter(({ img }) => isVisibleInScrollRoot(img, scrollRoot)).map(({ img }) => img)
    loadBatch(visible)
  }
  requestAnimationFrame(() => {
    requestAnimationFrame(run)
  })
}

function scheduleOnNextPaint(run: () => void) {
  requestAnimationFrame(() => {
    requestAnimationFrame(run)
  })
}

function prepareExtractAssetImage(img: HTMLImageElement): string | null {
  const existingKey = img.dataset.extractAssetKey
  if (existingKey) return existingKey

  const src = img.getAttribute('src') || ''
  const key = parseExtractAssetKeyFromApiSrc(src)
  if (!key) return null

  img.dataset.extractAssetKey = key
  const assetFileId = parseExtractAssetFileIdFromApiSrc(src)
  if (assetFileId) img.dataset.extractAssetFileId = String(assetFileId)
  return key
}

function isPendingExtractAssetImage(img: HTMLImageElement): boolean {
  return Boolean(
    img.dataset.extractAssetKey &&
      img.dataset.extractAssetSigned !== '1' &&
      img.dataset.extractAssetFailed !== '1',
  )
}

function forgetSignedUrl(fileId: number, assetKey: string | undefined, signedUrl: string) {
  if (!assetKey) return
  const key = cacheKey(fileId, assetKey)
  const cached = signedUrlCache.get(key)
  if (cached?.url === signedUrl) signedUrlCache.delete(key)
}

function setSignedAssetSrc(img: HTMLImageElement, signedUrl: string, fileId: number, assetKey: string) {
  const fallbackSrc = img.dataset.extractAssetFallbackSrc || img.getAttribute('src') || ''
  const onError = () => {
    img.removeEventListener('error', onError)
    if (img.getAttribute('src') === signedUrl && fallbackSrc && fallbackSrc !== signedUrl) {
      forgetSignedUrl(fileId, assetKey, signedUrl)
      img.src = fallbackSrc
      delete img.dataset.extractAssetSigned
      img.dataset.extractAssetFailed = '1'
    }
  }
  img.addEventListener('error', onError, { once: true })
  delete img.dataset.extractAssetFailed
  img.src = signedUrl
  img.dataset.extractAssetSigned = '1'
}

function extractAssetFileIdForImage(img: HTMLImageElement, fallbackFileId: number): number {
  const raw = img.dataset.extractAssetFileId
  if (!raw) return fallbackFileId
  const parsed = Number.parseInt(raw, 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallbackFileId
}

/** 视口内 batch sign，将 img[src] 设为短期 signed URL（无 Bearer blob 中转）。 */
export function hydrateExtractAssetImages(
  root: HTMLElement,
  options: ExtractAssetHydrateOptions,
): () => void {
  const fileId = options.fileId
  const maxConcurrent = options.maxConcurrent ?? getExtractAssetHydrateConcurrency()
  const batchSize = options.signBatchSize ?? getExtractAssetSignBatchSize()
  const rootMargin = options.rootMargin ?? '200px'
  const eagerMax = options.eagerMax ?? DEFAULT_EXTRACT_ASSET_EAGER_MAX
  const limiter = createConcurrencyLimiter(maxConcurrent)
  const controllers = new Map<HTMLImageElement, AbortController>()
  let disposed = false
  let observer: IntersectionObserver | null = null
  let layoutObserver: ResizeObserver | null = null
  let mutationObserver: MutationObserver | null = null
  const observedImages = new WeakSet<HTMLImageElement>()
  const scrollRoot = findIntersectionRoot(root)

  const collectImages = () =>
    Array.from(root.querySelectorAll<HTMLImageElement>('img'))
      .map((img) => ({ img, key: prepareExtractAssetImage(img) }))
      .filter((entry): entry is { img: HTMLImageElement; key: string } => Boolean(entry.key))

  const loadBatch = (targets: HTMLImageElement[]) => {
    if (disposed || targets.length === 0) return
    const pending = targets.filter(isPendingExtractAssetImage)
    if (pending.length === 0) return

    limiter.enqueue(async () => {
      if (disposed) return
      const controller = new AbortController()
      for (const img of pending) controllers.set(img, controller)
      try {
        const groups = new Map<number, string[]>()
        for (const img of pending) {
          const key = img.dataset.extractAssetKey
          if (!key) continue
          const assetFileId = extractAssetFileIdForImage(img, fileId)
          const keys = groups.get(assetFileId) ?? []
          keys.push(key)
          groups.set(assetFileId, keys)
        }
        const signedByFileId = new Map<number, Map<string, string>>()
        for (const [assetFileId, keys] of groups) {
          signedByFileId.set(
            assetFileId,
            await signAssetKeys(assetFileId, keys, batchSize, controller.signal),
          )
        }
        if (disposed || controller.signal.aborted) return
        for (const img of pending) {
          const key = img.dataset.extractAssetKey
          if (!key) continue
          const assetFileId = extractAssetFileIdForImage(img, fileId)
          const url = signedByFileId.get(assetFileId)?.get(key)
          if (url) {
            setSignedAssetSrc(img, url, assetFileId, key)
          }
        }
      } catch {
        // 失败静默，不无限重试
      } finally {
        for (const img of pending) controllers.delete(img)
      }
    })
  }

  const kickVisibleLoad = () => {
    if (disposed) return
    const images = collectImages()
    const eagerLoadAll = eagerMax > 0 && images.length > 0 && images.length <= eagerMax
    if (eagerLoadAll) {
      loadBatch(images.map((entry) => entry.img))
      return
    }
    scheduleInitialVisibleLoad(images, scrollRoot, loadBatch, () => disposed)
  }

  const observeCurrentImages = () => {
    if (disposed) return
    const images = collectImages()
    const eagerLoadAll = eagerMax > 0 && images.length > 0 && images.length <= eagerMax
    if (typeof IntersectionObserver === 'undefined' || eagerLoadAll) {
      loadBatch(images.map((entry) => entry.img))
      return
    }
    for (const { img } of images) {
      if (observedImages.has(img)) continue
      observedImages.add(img)
      observer?.observe(img)
    }
    kickVisibleLoad()
  }

  const installMutationObserver = () => {
    if (typeof MutationObserver === 'undefined') return
    mutationObserver = new MutationObserver(() => {
      scheduleOnNextPaint(observeCurrentImages)
    })
    mutationObserver.observe(root, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['src', 'data-extract-asset-signed', 'data-extract-asset-failed'],
    })
  }

  const initialImages = collectImages()
  const initialEagerLoadAll = eagerMax > 0 && initialImages.length > 0 && initialImages.length <= eagerMax

  if (typeof IntersectionObserver === 'undefined') {
    loadBatch(initialImages.map((entry) => entry.img))
    installMutationObserver()
  } else if (initialEagerLoadAll) {
    scheduleOnNextPaint(() => loadBatch(collectImages().map((entry) => entry.img)))
    if (typeof ResizeObserver !== 'undefined') {
      layoutObserver = new ResizeObserver(() => kickVisibleLoad())
      layoutObserver.observe(root)
      if (scrollRoot instanceof Element) {
        layoutObserver.observe(scrollRoot)
      }
    }
    installMutationObserver()
  } else {
    observer = new IntersectionObserver(
      (entries) => {
        const visible: HTMLImageElement[] = []
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          observer?.unobserve(entry.target)
          visible.push(entry.target as HTMLImageElement)
        }
        loadBatch(visible)
      },
      {
        root: scrollRoot,
        rootMargin,
        threshold: 0.01,
      },
    )
    for (const { img } of initialImages) {
      observedImages.add(img)
      observer.observe(img)
    }
    kickVisibleLoad()
    if (typeof ResizeObserver !== 'undefined') {
      layoutObserver = new ResizeObserver(() => kickVisibleLoad())
      layoutObserver.observe(root)
      if (scrollRoot instanceof Element) {
        layoutObserver.observe(scrollRoot)
      }
    }
    installMutationObserver()
  }

  return () => {
    disposed = true
    observer?.disconnect()
    layoutObserver?.disconnect()
    mutationObserver?.disconnect()
    controllers.forEach((controller) => controller.abort())
    controllers.clear()
  }
}
