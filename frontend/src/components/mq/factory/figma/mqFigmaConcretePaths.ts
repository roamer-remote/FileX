import { isoPedestalPaths } from '../svg/mqIsometry'

/** 站台共用底座（local platform 顶 y≈62） */
export const FIGMA_STATION_PEDESTAL = {
  cx: 75,
  baseY: 102,
  w: 132,
  h: 28,
  shadow: { cx: 75, cy: 120, rx: 54, ry: 7 },
} as const

export const FIGMA_ARM_PEDESTAL = {
  cx: 85,
  baseY: 108,
  w: 150,
  h: 28,
  shadow: { cx: 85, cy: 126, rx: 62, ry: 8 },
} as const

export function figmaStationPedestalPaths() {
  const s = FIGMA_STATION_PEDESTAL
  return {
    pedestal: isoPedestalPaths(s.cx, s.baseY, s.w, s.h),
    shadow: s.shadow,
  }
}

export function figmaArmPedestalPaths() {
  const a = FIGMA_ARM_PEDESTAL
  return {
    pedestal: isoPedestalPaths(a.cx, a.baseY, a.w, a.h),
    shadow: a.shadow,
  }
}

/** 等距纸张（主队列堆叠） */
export function figmaIsoPaperSheet(cx: number, top: number, depth: number) {
  const ox = cx - depth * 3
  const oy = top + depth * 2.5
  return {
    top: `M${ox - 16} ${oy + 6} L${ox} ${oy} L${ox + 16} ${oy + 6} L${ox} ${oy + 12} Z`,
    left: `M${ox - 16} ${oy + 6} L${ox - 16} ${oy + 18} L${ox} ${oy + 24} L${ox} ${oy + 12} Z`,
    right: `M${ox} ${oy + 12} L${ox} ${oy + 24} L${ox + 16} ${oy + 18} L${ox + 16} ${oy + 6} Z`,
    fold: `M${ox + 4} ${oy + 2} L${ox + 14} ${oy + 2} L${ox + 14} ${oy + 8} L${ox + 4} ${oy + 8} Z`,
  }
}

/** 传送带几何（factory 坐标） */
export const FIGMA_CONVEYOR = {
  leftRoller: { cx: 134, cy: 118, r: 16 },
  rightRoller: { cx: 942, cy: 118, r: 16 },
  top: 'M122 103 L954 103 L954 118 L122 118 Z',
  front: 'M122 118 L954 118 L954 142 L122 142 Z',
  railLeft: 'M122 103 L122 118',
  railRight: 'M954 103 L954 118',
  lip: 'M122 103 L954 103',
  slotY: 124,
  packages: [
    { x: 198, y: 106 },
    { x: 318, y: 106 },
    { x: 438, y: 106 },
  ],
} as const

/** 迷你包裹块（等距） */
export function figmaIsoPackage(x: number, y: number, size = 12) {
  const hw = size * 0.866
  const hh = size * 0.5
  const d = size * 0.45
  const cx = x + size
  const cy = y + size * 0.6
  return {
    top: `M${cx - hw} ${cy} L${cx} ${cy - hh} L${cx + hw} ${cy} L${cx} ${cy + hh} Z`,
    left: `M${cx - hw} ${cy} L${cx - hw} ${cy + d} L${cx} ${cy + hh + d} L${cx} ${cy + hh} Z`,
    right: `M${cx} ${cy + hh} L${cx} ${cy + hh + d} L${cx + hw} ${cy + d} L${cx + hw} ${cy} Z`,
  }
}
