import { useLayoutEffect, useState, type RefObject } from 'react'

type Options = {
  /** 指向 .fl-body 容器 */
  bodyRef: RefObject<HTMLElement | null>
  /** 为 false 时不测量（如 grid 模式） */
  enabled?: boolean
  /** 表格宿主选择器，默认 .fl-table-host */
  hostSelector?: string
  /** 最小 scroll.y */
  minScrollY?: number
  /** 表头与 body 间距扣减 */
  headerGap?: number
}

/**
 * 在 flex 列布局中测量 .fl-body 剩余高度，供 Ant Table scroll.y 使用。
 * 与资料页 FileList 同源逻辑。
 */
export function useFlexTableBodyScrollY(
  deps: unknown[],
  {
    bodyRef,
    enabled = true,
    hostSelector = '.fl-table-host',
    minScrollY = 120,
    headerGap = 10,
  }: Options,
): number {
  const [scrollY, setScrollY] = useState(minScrollY)

  useLayoutEffect(() => {
    if (!enabled) return
    const body = bodyRef.current
    if (!body) return

    const measure = () => {
      const host = body.querySelector(hostSelector) as HTMLElement | null
      if (!host) return
      const pane = body.closest('.ant-tabs-tabpane') as HTMLElement | null
      if (
        pane &&
        (pane.classList.contains('ant-tabs-tabpane-hidden') || pane.getAttribute('aria-hidden') === 'true')
      ) {
        return
      }
      const header =
        (host.querySelector('.ant-table-header') as HTMLElement | null) ??
        (host.querySelector('.ant-table-thead') as HTMLElement | null)
      const headerH = header ? Math.ceil(header.getBoundingClientRect().height) : 40
      const bodySlot = body.clientHeight
      const nextY = Math.max(minScrollY, Math.floor(bodySlot - headerH - headerGap))
      setScrollY(nextY)
    }

    const run = () => {
      requestAnimationFrame(() => {
        requestAnimationFrame(measure)
      })
    }

    run()
    const ro = new ResizeObserver(run)
    ro.observe(body)
    const hostEl = body.querySelector(hostSelector)
    if (hostEl instanceof HTMLElement) ro.observe(hostEl)
    window.addEventListener('resize', run)
    document.addEventListener('fullscreenchange', run)
    const t1 = window.setTimeout(run, 80)
    const t2 = window.setTimeout(run, 280)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', run)
      document.removeEventListener('fullscreenchange', run)
      window.clearTimeout(t1)
      window.clearTimeout(t2)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps 由调用方传入以在数据/分页变化时重测
  }, [enabled, bodyRef, hostSelector, minScrollY, headerGap, ...deps])

  return scrollY
}
