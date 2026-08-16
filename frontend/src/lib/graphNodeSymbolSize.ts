/** 节点直径 = 计数 × 显示比例 × 单资料基准（系统参数 tag_graph_*），限制 8–160 px */
export function graphNodeDiameter(count: number, singleBase: number, displayRatio: number): number {
  const c = Math.max(1, Math.floor(count))
  const raw = c * displayRatio * singleBase
  return Math.max(8, Math.min(160, Math.round(raw)))
}

/** vis-network 节点 `size` 为半径（像素） */
export function graphNodeVisRadius(count: number, singleBase: number, displayRatio: number): number {
  return graphNodeDiameter(count, singleBase, displayRatio) / 2
}
