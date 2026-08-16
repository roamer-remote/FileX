import type { WorkshopHealth, WorkshopKey } from '../mqFactoryMetrics'

export type FigmaWorkshopTheme = {
  workshopIndex: number
  titleKey: string
  routeKey: string
  hexFill: string
  hexStroke: string
  healthTagClass: string
  healthTextFill: string
  routeTagClass: string
  routeTextFill: string
  factorySymbol: 'factoryBlue' | 'factoryGreen' | 'factoryCyan'
  robotStatusBg: string
  robotStatusColor: string
  stationCounterFill: string
  armCounterFill: string
  chevronClass: string
}

export const FIGMA_WORKSHOP_THEMES: Record<WorkshopKey, FigmaWorkshopTheme> = {
  extract: {
    workshopIndex: 1,
    titleKey: 'admin.mq.groupExtract',
    routeKey: 'kb.extract',
    hexFill: '#2f8cff',
    hexStroke: '#b9dcff',
    healthTagClass: 'mq-figma-tag',
    healthTextFill: '#1677ff',
    routeTagClass: 'mq-figma-tag',
    routeTextFill: '#0067ff',
    factorySymbol: 'factoryBlue',
    robotStatusBg: '#eef7ff',
    robotStatusColor: '#1677ff',
    stationCounterFill: '#314463',
    armCounterFill: '#1677ff',
    chevronClass: 'mq-figma-blue',
  },
  index: {
    workshopIndex: 2,
    titleKey: 'admin.mq.groupIndex',
    routeKey: 'kb.index',
    hexFill: '#31aa63',
    hexStroke: '#bee9c9',
    healthTagClass: 'mq-figma-tagg',
    healthTextFill: '#1f9952',
    routeTagClass: 'mq-figma-tagg',
    routeTextFill: '#087e3b',
    factorySymbol: 'factoryGreen',
    robotStatusBg: '#f0fbf5',
    robotStatusColor: '#16a34a',
    stationCounterFill: '#15803d',
    armCounterFill: '#1677ff',
    chevronClass: 'mq-figma-green',
  },
  post: {
    workshopIndex: 3,
    titleKey: 'admin.mq.groupPost',
    routeKey: 'kb.post',
    hexFill: '#15b8d8',
    hexStroke: '#b5edfa',
    healthTagClass: 'mq-figma-tag-run',
    healthTextFill: '#0891b2',
    routeTagClass: 'mq-figma-tag-run-route',
    routeTextFill: '#0284c7',
    factorySymbol: 'factoryCyan',
    robotStatusBg: '#ecfbff',
    robotStatusColor: '#0891b2',
    stationCounterFill: '#0891b2',
    armCounterFill: '#1677ff',
    chevronClass: 'mq-figma-cyan',
  },
}

export const HEALTH_LABEL: Record<WorkshopHealth, string> = {
  idle: 'admin.mq.factoryHealthIdle',
  running: 'admin.mq.factoryHealthRunning',
  backlog: 'admin.mq.factoryHealthBacklog',
  attention: 'admin.mq.factoryHealthAttention',
}

export const ILLUSTRATED_WORKSHOP_BACKGROUNDS: Record<WorkshopKey, string> = {
  extract: '/assets/mq-factory/illustrated/workshop-extract.png',
  index: '/assets/mq-factory/illustrated/workshop-index.png',
  post: '/assets/mq-factory/illustrated/workshop-post.png',
}

export const ILLUSTRATED_WORKSHOP_ROW = { width: 2142, height: 532 } as const

/** 车间行 SVG 画布（Figma row 1508×220；实际行高由 figmaWorkshopRowLayout 计算） */
export const FIGMA_ROW = { width: 1508, height: 220 } as const

/** factory 符号组在车间行内的偏移 */
export const FIGMA_FACTORY_ORIGIN = { x: 280, y: 14 } as const

/** 站台白底 platform 顶边 / 中心（factory 内 y，由 symbol 几何推导） */
export const FIGMA_STATION_PLATFORM = {
  stationLocalTop: 62,
  stationLocalHeight: 70,
  armLocalTop: 72,
  armLocalHeight: 72,
  topY: 101,
  centerY: 136,
  bottomY: 171,
} as const

/** 兼容旧引用 */
export const FIGMA_STATION_PLATFORM_CENTER_Y = FIGMA_STATION_PLATFORM.centerY

function figmaStationUnitY(localPlatformTop: number) {
  return FIGMA_STATION_PLATFORM.topY - localPlatformTop
}

/** 站台布局：四站 platform 顶边共线 @ factory y=101 */
export const FIGMA_STATION_LAYOUT = {
  queue: { x: 95, y: figmaStationUnitY(FIGMA_STATION_PLATFORM.stationLocalTop) },
  process: { x: 345, y: figmaStationUnitY(FIGMA_STATION_PLATFORM.armLocalTop) },
  retry: { x: 580, y: figmaStationUnitY(FIGMA_STATION_PLATFORM.stationLocalTop) },
  dlq: { x: 825, y: figmaStationUnitY(FIGMA_STATION_PLATFORM.stationLocalTop) },
} as const

export const FIGMA_STATION_LABELS = {
  queue: { x: 150, y: 22, text: '主队列' },
  process: { x: 394, y: 22, text: '加工台' },
  retry: { x: 638, y: 22, text: '返工线' },
  dlq: { x: 884, y: 22, text: '回收站' },
} as const

/** 主队列工位下方排队 preview panel（factory 组内坐标） */
export const FIGMA_QUEUE_PREVIEW = {
  width: 210,
  height: 92,
  offsetX: 95,
  offsetY: 168,
} as const

/** robot 符号几何（#robot bbox） */
export const FIGMA_ROBOT_SYMBOL = {
  useX: 18,
  symbolHeight: 128,
  visualCenterOffsetY: 72,
  glowOffsetY: 119,
} as const

/** 机器人内容区：垂直中心与四站台 platform 中心共线 */
export const FIGMA_ROBOT_SLOT = {
  x: 1292,
  width: 194,
  height: FIGMA_ROBOT_SYMBOL.symbolHeight,
} as const

/** 四站台 + 机器人内容区共线（inline / expanded 一致） */
export const FIGMA_PIPELINE_MIDLINE_Y =
  FIGMA_FACTORY_ORIGIN.y + FIGMA_STATION_PLATFORM.centerY

export const FIGMA_ROBOT_STATUS_BADGE = {
  x: 106,
  width: 54,
  height: 54,
  /** 相对 slot 垂直居中再上移，避免遮住机器人右臂 */
  offsetY: -42,
} as const

export function figmaRobotPanelInnerLayout(slotHeight: number) {
  const midY = slotHeight / 2
  const robotUseY = midY - FIGMA_ROBOT_SYMBOL.visualCenterOffsetY
  const badgeY = midY - FIGMA_ROBOT_STATUS_BADGE.height / 2 + FIGMA_ROBOT_STATUS_BADGE.offsetY
  return {
    robotUseX: FIGMA_ROBOT_SYMBOL.useX,
    robotUseY,
    glowCy: robotUseY + FIGMA_ROBOT_SYMBOL.glowOffsetY,
    badgeY,
  }
}

export type FigmaWorkshopRowLayout = {
  rowWidth: number
  rowHeight: number
  robotPanel: { x: number; y: number; width: number; height: number }
}

export function figmaWorkshopRowLayout(_display: 'inline' | 'expanded'): FigmaWorkshopRowLayout {
  const robotY = FIGMA_PIPELINE_MIDLINE_Y - FIGMA_ROBOT_SLOT.height / 2
  const queuePreviewBottom =
    FIGMA_FACTORY_ORIGIN.y + FIGMA_QUEUE_PREVIEW.offsetY + FIGMA_QUEUE_PREVIEW.height
  const contentBottom = Math.max(
    FIGMA_FACTORY_ORIGIN.y + FIGMA_STATION_PLATFORM.bottomY,
    robotY + FIGMA_ROBOT_SLOT.height,
    queuePreviewBottom,
  )
  return {
    rowWidth: FIGMA_ROW.width,
    rowHeight: Math.max(FIGMA_ROW.height, contentBottom + 8),
    robotPanel: {
      x: FIGMA_ROBOT_SLOT.x,
      y: robotY,
      width: FIGMA_ROBOT_SLOT.width,
      height: FIGMA_ROBOT_SLOT.height,
    },
  }
}

export function figmaBeltSymbolKey(workshopKey: WorkshopKey): 'beltBlue' | 'beltGreen' {
  return workshopKey === 'index' ? 'beltGreen' : 'beltBlue'
}

export function figmaWorkshopColorVariant(workshopKey: WorkshopKey): 'blue' | 'green' | 'cyan' {
  if (workshopKey === 'index') return 'green'
  if (workshopKey === 'post') return 'cyan'
  return 'blue'
}

export function figmaBeltColorVariant(workshopKey: WorkshopKey): 'blue' | 'green' {
  return figmaBeltSymbolKey(workshopKey) === 'beltGreen' ? 'green' : 'blue'
}

export function figmaStationRoleSymbolKey(
  workshopKey: WorkshopKey,
  role: 'queue' | 'retry' | 'dlq',
): `stationQueueBlue` | `stationQueueGreen` | `stationQueueCyan` | `stationRetryBlue` | `stationRetryGreen` | `stationRetryCyan` | `stationDlqBlue` | `stationDlqGreen` | `stationDlqCyan` {
  const color = workshopKey === 'index' ? 'Green' : workshopKey === 'post' ? 'Cyan' : 'Blue'
  const roleCap = role === 'queue' ? 'Queue' : role === 'retry' ? 'Retry' : 'Dlq'
  return `station${roleCap}${color}` as ReturnType<typeof figmaStationRoleSymbolKey>
}

/** @deprecated 三站已分角色符号，请用 figmaStationRoleSymbolKey */
export function figmaStationSymbolKey(
  workshopKey: WorkshopKey,
): 'stationUnitBlue' | 'stationUnitGreen' | 'stationUnitCyan' {
  if (workshopKey === 'index') return 'stationUnitGreen'
  if (workshopKey === 'post') return 'stationUnitCyan'
  return 'stationUnitBlue'
}

export const FIGMA_STATION_COUNTERS = {
  queue: { x: 165, y: 152 },
  process: { x: 430, y: 152 },
  retry: { x: 650, y: 152 },
  dlq: { x: 895, y: 152 },
} as const

/** 站台 symbol 宽度（与 MqFigmaSvgDefs stationUnit / armUnit 一致） */
const FIGMA_STATION_WIDTHS = { station: 150, arm: 170 } as const

/** 点击热区：由 factory 原点 + 站台 x 推导，避免与视觉错位 */
const FIGMA_HIT_PAD = { x: 10, y: 14, wExtra: 20, hExtra: 28 } as const
const FIGMA_STATION_HIT_FACTORY_Y = {
  top: FIGMA_STATION_LAYOUT.process.y,
  bottom: FIGMA_STATION_PLATFORM.bottomY,
} as const

function figmaStationHitArea(factoryX: number, width: number) {
  return {
    x: FIGMA_FACTORY_ORIGIN.x + factoryX - FIGMA_HIT_PAD.x,
    y: FIGMA_FACTORY_ORIGIN.y + FIGMA_STATION_HIT_FACTORY_Y.top - FIGMA_HIT_PAD.y,
    width: width + FIGMA_HIT_PAD.wExtra,
    height:
      FIGMA_STATION_HIT_FACTORY_Y.bottom -
      FIGMA_STATION_HIT_FACTORY_Y.top +
      FIGMA_HIT_PAD.hExtra,
  }
}

export const FIGMA_HIT_AREAS = {
  queue: figmaStationHitArea(FIGMA_STATION_LAYOUT.queue.x, FIGMA_STATION_WIDTHS.station),
  process: figmaStationHitArea(FIGMA_STATION_LAYOUT.process.x, FIGMA_STATION_WIDTHS.arm),
  retry: figmaStationHitArea(FIGMA_STATION_LAYOUT.retry.x, FIGMA_STATION_WIDTHS.station),
  dlq: figmaStationHitArea(FIGMA_STATION_LAYOUT.dlq.x, FIGMA_STATION_WIDTHS.station),
} as const

/** 支线设施区 SVG 布局（四卡等分宽度，左右留白一致） */
export const FIGMA_SIDECAR = {
  viewWidth: 1508,
  viewHeight: 228,
  headerOffsetY: 14,
  /** 卡片行顶边：低于 hex 序号标（headerY + 39 + 9） */
  branchRowY: 62,
  cardHeight: 148,
  /** 左右对称内边距 */
  padInline: 20,
  /** 卡片之间的间距 */
  cardGap: 16,
  branchCount: 4,
} as const

export function figmaSidecarCardWidth(): number {
  const { viewWidth, padInline, cardGap, branchCount } = FIGMA_SIDECAR
  return (viewWidth - 2 * padInline - (branchCount - 1) * cardGap) / branchCount
}

export function figmaSidecarCardX(index: number): number {
  const cardWidth = figmaSidecarCardWidth()
  return FIGMA_SIDECAR.padInline + index * (cardWidth + FIGMA_SIDECAR.cardGap)
}

/** 状态 tag 右对齐留白（相对卡片宽度） */
export function figmaSidecarTagX(cardWidth: number): number {
  return Math.max(cardWidth - 111, 160)
}

/** 支线卡片底部指标行（对齐 figma branchBase：未完成 | 排队 | 处理中） */
export const FIGMA_BRANCH_METRICS = {
  rowY: 124,
  refCardWidth: 356,
  columns: [
    { designX: 34, i18nKey: 'admin.mq.backlogTotal' as const },
    { designX: 126, i18nKey: 'admin.mq.backlogQueued' as const, separator: '|  ' },
    { designX: 246, i18nKey: 'admin.mq.backlogRunning' as const, separator: '|  ' },
  ],
} as const

export function figmaBranchMetricX(cardWidth: number, designX: number): number {
  return Math.round((designX / FIGMA_BRANCH_METRICS.refCardWidth) * cardWidth)
}

export type FigmaBranchCardKey =
  | 'branchCardBlue'
  | 'branchCardGreen'
  | 'branchCardPurple'
  | 'branchCardOrange'

export type FigmaBranchTheme = {
  card: FigmaBranchCardKey
  label: string
  tagClass: string
  healthTextFill: string
  runningTagClass?: string
  runningTextFill?: string
}

export const FIGMA_BRANCH_LAYOUT: FigmaBranchTheme[] = [
  {
    card: 'branchCardBlue',
    label: 'index_notify',
    tagClass: 'mq-figma-tag',
    healthTextFill: '#1677ff',
  },
  {
    card: 'branchCardGreen',
    label: 'post_notify',
    tagClass: 'mq-figma-tagg',
    healthTextFill: '#1f9952',
  },
  {
    card: 'branchCardPurple',
    label: 'mineru_main',
    tagClass: 'mq-figma-tag-purple',
    healthTextFill: '#7c5cff',
    runningTagClass: 'mq-figma-tag-purple-run',
    runningTextFill: '#7c5cff',
  },
  {
    card: 'branchCardOrange',
    label: 'docling_main',
    tagClass: 'mq-figma-tago',
    healthTextFill: '#f97316',
  },
]
