/** 等距几何辅助（2:1 等角投影） */

export type IsoCubePaths = {
  top: string
  left: string
  right: string
  edge: string
}

/** 等距立方体路径，cx/cy 为顶面菱形中心 */
export function isoCubePaths(cx: number, cy: number, size: number): IsoCubePaths {
  const hw = size * 0.866
  const hh = size * 0.5
  const topY = cy - hh
  const midY = cy
  const botY = cy + hh
  const depth = size * 0.55
  return {
    top: `M${cx - hw} ${midY} L${cx} ${topY} L${cx + hw} ${midY} L${cx} ${botY} Z`,
    left: `M${cx - hw} ${midY} L${cx - hw} ${midY + depth} L${cx} ${botY + depth} L${cx} ${botY} Z`,
    right: `M${cx} ${botY} L${cx} ${botY + depth} L${cx + hw} ${midY + depth} L${cx + hw} ${midY} Z`,
    edge: `M${cx - hw} ${midY} L${cx} ${topY} L${cx + hw} ${midY} L${cx + hw} ${midY + depth} L${cx} ${botY + depth} L${cx - hw} ${midY + depth} Z`,
  }
}

export type IsoPedestalPaths = {
  top: string
  left: string
  right: string
}

export function isoPedestalPaths(cx: number, baseY: number, w: number, h: number): IsoPedestalPaths {
  const hw = w * 0.5
  return {
    top: `M${cx - hw} ${baseY} L${cx} ${baseY - h * 0.35} L${cx + hw} ${baseY} L${cx} ${baseY + h * 0.35} Z`,
    left: `M${cx - hw} ${baseY} L${cx - hw} ${baseY + h * 0.45} L${cx} ${baseY + h * 0.8} L${cx} ${baseY + h * 0.35} Z`,
    right: `M${cx} ${baseY + h * 0.35} L${cx} ${baseY + h * 0.8} L${cx + hw} ${baseY + h * 0.45} L${cx + hw} ${baseY} Z`,
  }
}

export function glassGradientIds(idPrefix: string) {
  return {
    top: `${idPrefix}GlassTop`,
    left: `${idPrefix}GlassLeft`,
    right: `${idPrefix}GlassRight`,
    glow: `${idPrefix}Glow`,
  }
}
