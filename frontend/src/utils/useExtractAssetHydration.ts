import { useLayoutEffect, type RefObject } from 'react'
import { hydrateExtractAssetImages } from '@/utils/extractAssetHydration'

type UseExtractAssetHydrationOptions = {
  fileId?: number
  /** 预览 HTML 或等价 content key；变化时重新 hydration */
  contentKey?: string
  enabled?: boolean
}

/** 笔记预览挂载 extract 图片 hydration；ref 晚于 effect 时自动重试（Modal/Tabs）。 */
export function useExtractAssetHydration(
  rootRef: RefObject<HTMLElement | null>,
  options: UseExtractAssetHydrationOptions,
) {
  const { fileId, contentKey, enabled = true } = options

  useLayoutEffect(() => {
    if (!enabled || !fileId || !contentKey) return

    let cleanup: (() => void) | undefined
    let cancelled = false
    let layoutObserver: ResizeObserver | null = null

    const attach = () => {
      const root = rootRef.current
      if (!root || cancelled) return false
      cleanup?.()
      cleanup = hydrateExtractAssetImages(root, { fileId })
      return true
    }

    if (attach()) {
      return () => {
        cancelled = true
        layoutObserver?.disconnect()
        cleanup?.()
      }
    }

    let raf = 0
    raf = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (cancelled) return
        if (attach()) return
        if (typeof ResizeObserver === 'undefined') return
        const watchTarget = rootRef.current?.closest('.ant-modal-body') ?? document.body
        layoutObserver = new ResizeObserver(() => {
          if (attach()) layoutObserver?.disconnect()
        })
        layoutObserver.observe(watchTarget)
      })
    })

    return () => {
      cancelled = true
      if (raf) cancelAnimationFrame(raf)
      layoutObserver?.disconnect()
      cleanup?.()
    }
  }, [rootRef, fileId, contentKey, enabled])
}
