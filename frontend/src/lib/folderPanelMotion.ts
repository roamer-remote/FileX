/** 侧栏目录触发器在视口中的矩形，用于浮动面板开闭动画锚点 */
export type FolderPanelAnchor = {
  x: number
  y: number
  width: number
  height: number
}

export type FolderPanelMotion = 'idle' | 'enter' | 'exit'

export function anchorFromElement(el: Element | null): FolderPanelAnchor | null {
  if (!el) return null
  const r = el.getBoundingClientRect()
  return { x: r.x, y: r.y, width: r.width, height: r.height }
}

/** 首次从触发器打开时，面板默认落在触发器右侧 */
export function posBesideAnchor(
  anchor: FolderPanelAnchor,
  panelWidth: number,
  panelHeight: number,
  edge = 12,
): { x: number; y: number } {
  if (typeof window === 'undefined') {
    return { x: anchor.x + anchor.width + 10, y: anchor.y }
  }
  const x = anchor.x + anchor.width + 10
  const y = anchor.y - 4
  const maxX = Math.max(edge, window.innerWidth - panelWidth - edge)
  const maxY = Math.max(edge, window.innerHeight - panelHeight - edge)
  return {
    x: Math.min(Math.max(edge, x), maxX),
    y: Math.min(Math.max(edge, y), maxY),
  }
}

/** 面板开闭动画：从触发器左上角 (anchor) 平移至面板左上角 (panelLeft/Top) 的偏移 */
export function panelMotionDelta(
  anchor: FolderPanelAnchor,
  panelLeft: number,
  panelTop: number,
): { dx: number; dy: number } {
  return {
    dx: anchor.x - panelLeft,
    dy: anchor.y - panelTop,
  }
}
