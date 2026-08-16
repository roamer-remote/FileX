import type { FlowNodePlacement } from '@/utils/agentRunFlowLayout'

const CORNER_GAP = 26
const L1_L2_GUTTER = 24
const OBSTACLE_PAD = 6

export type FlowEdgeObstacle = {
  id: string
  placement: FlowNodePlacement
}

type Point = { x: number; y: number }

function pointsToPath(points: Point[]): string {
  if (points.length === 0) return ''
  const [first, ...rest] = points
  return `M ${first.x} ${first.y}${rest.map((p) => ` L ${p.x} ${p.y}`).join('')}`
}

function isSameRow(source: FlowNodePlacement, target: FlowNodePlacement): boolean {
  return Math.abs(source.top - target.top) < 18
}

function columnsOverlap(source: FlowNodePlacement, target: FlowNodePlacement): boolean {
  const sourceCenter = source.left + source.width / 2
  const targetCenter = target.left + target.width / 2
  return Math.abs(sourceCenter - targetCenter) < Math.min(source.width, target.width) / 2 + 8
}

function rectOf(placement: FlowNodePlacement) {
  return {
    left: placement.left,
    top: placement.top,
    right: placement.left + placement.width,
    bottom: placement.top + placement.height,
  }
}

function segmentHitsRect(x1: number, y1: number, x2: number, y2: number, rect: ReturnType<typeof rectOf>): boolean {
  const pad = OBSTACLE_PAD
  const left = rect.left - pad
  const right = rect.right + pad
  const top = rect.top - pad
  const bottom = rect.bottom + pad

  if (y1 === y2) {
    const minX = Math.min(x1, x2)
    const maxX = Math.max(x1, x2)
    return y1 >= top && y1 <= bottom && maxX >= left && minX <= right
  }
  if (x1 === x2) {
    const minY = Math.min(y1, y2)
    const maxY = Math.max(y1, y2)
    return x1 >= left && x1 <= right && maxY >= top && minY <= bottom
  }
  return false
}

function pathHitsObstacles(points: Point[], obstacles: ReturnType<typeof rectOf>[]): boolean {
  for (let i = 0; i < points.length - 1; i += 1) {
    const a = points[i]
    const b = points[i + 1]
    for (const rect of obstacles) {
      if (segmentHitsRect(a.x, a.y, b.x, b.y, rect)) return true
    }
  }
  return false
}

function obstacleRects(
  obstacles: FlowEdgeObstacle[] | undefined,
  sourceId: string | undefined,
  targetId: string | undefined,
) {
  return (obstacles ?? [])
    .filter((item) => item.id !== sourceId && item.id !== targetId)
    .map((item) => rectOf(item.placement))
}

function pickHorizontalLaneY(
  x1: number,
  x2: number,
  source: FlowNodePlacement,
  target: FlowNodePlacement,
  obstacles: ReturnType<typeof rectOf>[],
): number {
  const minX = Math.min(x1, x2)
  const maxX = Math.max(x1, x2)
  const candidates = [
    source.top + source.height / 2,
    target.top + target.height / 2,
    Math.min(source.top, target.top) - CORNER_GAP,
    Math.max(source.top + source.height, target.top + target.height) + CORNER_GAP,
  ]

  for (const y of candidates) {
    let blocked = false
    for (const rect of obstacles) {
      if (segmentHitsRect(minX, y, maxX, y, rect)) {
        blocked = true
        break
      }
    }
    if (!blocked) return y
  }

  return Math.max(source.top + source.height, target.top + target.height) + CORNER_GAP + 24
}

function routeBelowSource(source: FlowNodePlacement, target: FlowNodePlacement): string {
  const srcBottom = {
    x: source.left + source.width / 2,
    y: source.top + source.height,
  }
  const tgtTop = {
    x: target.left + target.width / 2,
    y: target.top,
  }
  if (Math.abs(srcBottom.x - tgtTop.x) < 8) {
    return pointsToPath([srcBottom, tgtTop])
  }
  const midY = srcBottom.y + Math.max(CORNER_GAP, (tgtTop.y - srcBottom.y) / 2)
  return pointsToPath([
    srcBottom,
    { x: srcBottom.x, y: midY },
    { x: tgtTop.x, y: midY },
    tgtTop,
  ])
}

function routeForwardOrthogonal(
  source: FlowNodePlacement,
  target: FlowNodePlacement,
  obstacles: ReturnType<typeof rectOf>[],
): string {
  const srcRight = {
    x: source.left + source.width,
    y: source.top + source.height / 2,
  }
  const tgtLeft = {
    x: target.left,
    y: target.top + target.height / 2,
  }
  const laneY = pickHorizontalLaneY(srcRight.x, tgtLeft.x, source, target, obstacles)
  const midX = srcRight.x + Math.max(CORNER_GAP, (tgtLeft.x - srcRight.x) / 2)

  if (laneY === srcRight.y && laneY === tgtLeft.y) {
    return pointsToPath([srcRight, { x: midX, y: laneY }, tgtLeft])
  }

  return pointsToPath([
    srcRight,
    { x: srcRight.x + CORNER_GAP, y: srcRight.y },
    { x: srcRight.x + CORNER_GAP, y: laneY },
    { x: midX, y: laneY },
    { x: midX, y: tgtLeft.y },
    tgtLeft,
  ])
}

/** Orthogonal polyline only — no Bézier curves; routes avoid third-party node boxes when provided. */
export function computeEdgePolyline(
  source: FlowNodePlacement,
  target: FlowNodePlacement,
  options?: {
    sourceId?: string
    targetId?: string
    obstacles?: FlowEdgeObstacle[]
  },
): string {
  const obstacles = obstacleRects(options?.obstacles, options?.sourceId, options?.targetId)

  const srcRight = {
    x: source.left + source.width,
    y: source.top + source.height / 2,
  }
  const tgtLeft = {
    x: target.left,
    y: target.top + target.height / 2,
  }

  if (
    target.top >= source.top + source.height - 8 &&
    tgtLeft.x >= source.left - 8 &&
    tgtLeft.x <= srcRight.x + 48
  ) {
    return routeBelowSource(source, target)
  }

  if (columnsOverlap(source, target) && target.top >= source.top + source.height - 4) {
    return pointsToPath([
      { x: source.left + source.width / 2, y: source.top + source.height },
      { x: target.left + target.width / 2, y: target.top },
    ])
  }

  if (source.lane === 'L1' && target.lane === 'L2') {
    const gutterY = source.top + source.height + L1_L2_GUTTER
    return pointsToPath([
      { x: srcRight.x, y: srcRight.y },
      { x: srcRight.x + CORNER_GAP, y: srcRight.y },
      { x: srcRight.x + CORNER_GAP, y: gutterY },
      { x: tgtLeft.x - CORNER_GAP, y: gutterY },
      { x: tgtLeft.x - CORNER_GAP, y: tgtLeft.y },
      tgtLeft,
    ])
  }

  if (isSameRow(source, target) && tgtLeft.x > srcRight.x) {
    const laneY = pickHorizontalLaneY(srcRight.x, tgtLeft.x, source, target, obstacles)
    if (laneY === srcRight.y) {
      return pointsToPath([srcRight, tgtLeft])
    }
    return pointsToPath([
      srcRight,
      { x: srcRight.x + CORNER_GAP, y: srcRight.y },
      { x: srcRight.x + CORNER_GAP, y: laneY },
      { x: tgtLeft.x - CORNER_GAP, y: laneY },
      { x: tgtLeft.x - CORNER_GAP, y: tgtLeft.y },
      tgtLeft,
    ])
  }

  if (tgtLeft.x >= srcRight.x) {
    return routeForwardOrthogonal(source, target, obstacles)
  }

  const corridorY =
    Math.max(source.top + source.height, target.top + target.height) +
    (source.lane === 'L1' || target.lane === 'L1' ? 16 : 48)
  return pointsToPath([
    srcRight,
    { x: srcRight.x + CORNER_GAP, y: srcRight.y },
    { x: srcRight.x + CORNER_GAP, y: corridorY },
    { x: tgtLeft.x - CORNER_GAP, y: corridorY },
    { x: tgtLeft.x - CORNER_GAP, y: tgtLeft.y },
    tgtLeft,
  ])
}

export function polylineIntersectsObstacles(
  path: string,
  obstacles: FlowEdgeObstacle[],
  excludeIds: string[] = [],
): boolean {
  const coords = path.match(/-?\d+(?:\.\d+)?/g)?.map(Number) ?? []
  const points: Point[] = []
  for (let i = 0; i < coords.length; i += 2) {
    points.push({ x: coords[i], y: coords[i + 1] })
  }
  const rects = obstacleRects(obstacles, excludeIds[0], excludeIds[1])
  return pathHitsObstacles(points, rects)
}
