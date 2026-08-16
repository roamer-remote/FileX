import type { ReactNode } from 'react'
import {
  FIGMA_CONVEYOR,
  figmaArmPedestalPaths,
  figmaIsoPackage,
  figmaIsoPaperSheet,
  figmaStationPedestalPaths,
} from './mqFigmaConcretePaths'
import { FIGMA_SIDECAR, figmaSidecarCardWidth } from './mqFigmaTheme'

type ColorVariant = 'blue' | 'green' | 'cyan'

const PEDESTAL_CLASS: Record<ColorVariant, string> = {
  blue: 'mq-figma-pedestal',
  green: 'mq-figma-pedestalG',
  cyan: 'mq-figma-pedestalC',
}

const ACCENT_CLASS: Record<ColorVariant, string> = {
  blue: 'mq-figma-blue',
  green: 'mq-figma-green',
  cyan: 'mq-figma-cyan',
}

const PAPER_CLASS: Record<ColorVariant, string> = {
  blue: 'mq-figma-paper',
  green: 'mq-figma-paperG',
  cyan: 'mq-figma-paperC',
}

export function FigmaPedestal({ variant }: { variant: ColorVariant }) {
  const { pedestal, shadow } = figmaStationPedestalPaths()
  const root = PEDESTAL_CLASS[variant]
  return (
    <>
      <ellipse cx={shadow.cx} cy={shadow.cy} rx={shadow.rx} ry={shadow.ry} className="mq-figma-ground-shadow" />
      <path d={pedestal.right} className={`${root} mq-figma-pedestal-face mq-figma-pedestal-face--right`} />
      <path d={pedestal.left} className={`${root} mq-figma-pedestal-face mq-figma-pedestal-face--left`} />
      <path d={pedestal.top} className={`${root} mq-figma-pedestal-face mq-figma-pedestal-face--top`} />
    </>
  )
}

export function FigmaArmPedestalBlock() {
  const { pedestal, shadow } = figmaArmPedestalPaths()
  return (
    <>
      <ellipse cx={shadow.cx} cy={shadow.cy} rx={shadow.rx} ry={shadow.ry} className="mq-figma-ground-shadow" />
      <path d={pedestal.right} className="mq-figma-pedestal mq-figma-pedestal-face mq-figma-pedestal-face--right" />
      <path d={pedestal.left} className="mq-figma-pedestal mq-figma-pedestal-face mq-figma-pedestal-face--left" />
      <path d={pedestal.top} className="mq-figma-pedestal mq-figma-pedestal-face mq-figma-pedestal-face--top" />
    </>
  )
}

/** 主队列：工程绘本式入料台 + 待处理文档堆 */
export function FigmaQueueHopper({ variant }: { variant: ColorVariant }) {
  const accent = ACCENT_CLASS[variant]
  const paper = PAPER_CLASS[variant]
  const sheets = [0, 1, 2, 3, 4].map((d) => figmaIsoPaperSheet(78, 0, d))

  return (
    <g className="mq-figma-queue-hopper mq-figma-queue-intake-desk">
      <path d="M25 66 L126 66 L115 104 L37 104 Z" className="mq-figma-hopper-front" />
      <path d="M25 66 L42 47 L110 47 L126 66 Z" className="mq-figma-hopper-back" />
      <path d="M25 66 L42 47 L37 104 Z" className="mq-figma-hopper-side mq-figma-hopper-side--left" />
      <path d="M126 66 L110 47 L115 104 Z" className="mq-figma-hopper-side mq-figma-hopper-side--right" />
      <path d="M42 47 L50 36 L102 36 L110 47 Z" className="mq-figma-intake-loader" />
      <rect x="49" y="76" width="58" height="9" rx="4.5" className="mq-figma-hopper-scan-window" />
      <path d="M53 80.5 H103" className={`mq-figma-hopper-scan-beam ${accent}`} fill="none" strokeWidth="3" />
      <rect x="55" y="58" width="46" height="13" rx="3" className="mq-figma-intake-display" />
      <path d="M61 64 H78 M83 64 H94" className="mq-figma-intake-display-line" fill="none" />
      <path d="M50 104 H104" className="mq-figma-intake-foot" fill="none" />
      <text x="67" y="65" className="mq-figma-intake-label">
        IN
      </text>
      {sheets.map((s, i) => (
        <g key={i} className="mq-figma-paper-stack">
          <path d={s.left} className={`${paper} mq-figma-paper-face--left`} />
          <path d={s.right} className={`${paper} mq-figma-paper-face--right`} />
          <path d={s.top} className={`${paper} mq-figma-paper-face--top`} />
          <path d={s.fold} className="mq-figma-paper-fold" />
          <path d={`M${78 - i * 3 - 10} ${8 + i * 2.5 + 14} H${78 - i * 3 + 10}`} className="mq-figma-paper-line" fill="none" strokeWidth="1.2" />
        </g>
      ))}
    </g>
  )
}

/** 返工线：维修返工台 + U 形回流滑道 */
export function FigmaRetryChute({ variant }: { variant: ColorVariant }) {
  const accent = ACCENT_CLASS[variant]
  return (
    <g className="mq-figma-retry-chute mq-figma-repair-return-line">
      <path d="M23 58 L125 58 L125 70 L47 70 L47 88 L111 88 L111 101 L23 101 Z" className="mq-figma-chute-body" />
      <path d="M23 58 L34 46 L125 46 L125 58" className="mq-figma-chute-rim" />
      <rect x="42" y="39" width="72" height="15" rx="3" className="mq-figma-chute-warning" />
      <path d="M51 46 H104" className="mq-figma-chute-warning-line" fill="none" />
      <text x="57" y="50" className="mq-figma-rework-label">
        REWORK
      </text>
      <path
        d="M91 70 A24 24 0 1 1 69 95"
        className={`mq-figma-retry-arrow ${accent}`}
        fill="none"
        strokeWidth="5"
        strokeLinecap="round"
      />
      <polygon points="91,65 103,70 91,77" className={`mq-figma-retry-arrow-head ${accent}`} />
      <path d="M74 73 L94 93 M94 73 L74 93" className="mq-figma-repair-wrench" fill="none" />
      <path d="M101 91 L119 105 L115 111 L97 97 Z" className="mq-figma-repair-tag" />
      <path d="M104 96 H114 M106 100 H112" className="mq-figma-repair-tag-line" fill="none" />
      <circle cx="112" cy="88" r="7" className="mq-figma-chute-roller" />
      <circle cx="47" cy="88" r="7" className="mq-figma-chute-roller" />
      <path d="M33 101 H108" className="mq-figma-chute-foot" fill="none" />
    </g>
  )
}

/** 回收站：智能质检回收箱 + 发光循环核心 */
export function FigmaRecycleBin({ variant }: { variant: ColorVariant }) {
  const accent = ACCENT_CLASS[variant]
  return (
    <g className="mq-figma-recycle-bin mq-figma-smart-recycle-bin">
      <path d="M33 47 L116 47 L107 61 L43 61 Z" className="mq-figma-bin-lid" />
      <rect x="64" y="33" width="20" height="15" rx="3" className="mq-figma-bin-handle" />
      <path d="M43 61 L35 108 L110 108 L101 61 Z" className="mq-figma-bin-body" />
      <path d="M47 65 L97 65 L94 99 L51 99 Z" className="mq-figma-bin-core-window" />
      <path d="M45 61 L101 61 L97 68 L49 68 Z" className="mq-figma-bin-inner-lip" />
      <path d="M52 70 L55 101 M65 70 L66 101 M78 70 L76 101 M91 70 L86 101" className={`mq-figma-bin-grate ${accent}`} fill="none" strokeWidth="2.1" />
      <circle cx="75" cy="83" r="17" className="mq-figma-bin-glow" />
      <path
        d="M64 83 A14 14 0 1 1 86 83"
        className={`mq-figma-recycle-mark ${accent}`}
        fill="none"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <polygon points="86,76 95,83 86,90" className={`mq-figma-recycle-mark-head ${accent}`} />
      <text x="55" y="57" className="mq-figma-recycle-label">
        RECYCLE
      </text>
      <path d="M42 109 H105" className="mq-figma-bin-foot" fill="none" />
    </g>
  )
}

function FigmaStationRoleUnit({
  id,
  variant,
  children,
}: {
  id?: string
  variant: ColorVariant
  children: ReactNode
}) {
  return (
    <g {...(id ? { id } : {})}>
      <FigmaPedestal variant={variant} />
      {children}
    </g>
  )
}

export function FigmaStationQueueSymbol({ id, variant }: { id?: string; variant: ColorVariant }) {
  return (
    <FigmaStationRoleUnit id={id} variant={variant}>
      <FigmaQueueHopper variant={variant} />
    </FigmaStationRoleUnit>
  )
}

export function FigmaStationRetrySymbol({ id, variant }: { id?: string; variant: ColorVariant }) {
  return (
    <FigmaStationRoleUnit id={id} variant={variant}>
      <FigmaRetryChute variant={variant} />
    </FigmaStationRoleUnit>
  )
}

export function FigmaStationDlqSymbol({ id, variant }: { id?: string; variant: ColorVariant }) {
  return (
    <FigmaStationRoleUnit id={id} variant={variant}>
      <FigmaRecycleBin variant={variant} />
    </FigmaStationRoleUnit>
  )
}

/** 加工台底座 + 立柱 + 大臂（不含前臂） */
export function FigmaArmWorkbenchBase() {
  return (
    <g className="mq-figma-illustrated-workbench">
      <FigmaArmPedestalBlock />
      <path d="M18 67 L151 67 L139 88 L31 88 Z" className="mq-figma-workbench-top" />
      <path d="M18 67 L31 88 L31 98 L18 75 Z" className="mq-figma-workbench-side" />
      <path d="M31 88 L139 88 L139 98 L31 98 Z" className="mq-figma-workbench-front" />
      <rect x="34" y="52" width="28" height="24" rx="4" className="mq-figma-workbench-console" />
      <rect x="39" y="57" width="18" height="12" rx="2" className="mq-figma-workbench-screen" />
      <path d="M42 63 H54 M42 67 H50" className="mq-figma-workbench-screen-line" fill="none" />
      <path d="M57 48 C57 28 69 21 86 20" className="mq-figma-workbench-lamp-arm" fill="none" />
      <path d="M82 15 L104 15 L100 28 L78 28 Z" className="mq-figma-workbench-lamp" />
      <path d="M84 28 L94 47" className="mq-figma-workbench-lamp-beam" fill="none" />
      <rect x="72" y="38" width="18" height="31" rx="5" className="mq-figma-arm-column" />
      <rect x="55" y="46" width="17" height="31" rx="5" className="mq-figma-arm-column mq-figma-arm-column--secondary" />
      <path d="M82 38 L82 20 L111 11 L117 22 L91 31 Z" className="mq-figma-arm-upper" />
      <circle cx="115" cy="39" r="17" className="mq-figma-arm-joint mq-figma-arm-joint--upper" />
      <g className="mq-figma-workbench-gears">
        <circle cx="90" cy="75" r="17" className="mq-figma-gear mq-figma-gear--large" />
        <circle cx="117" cy="77" r="12" className="mq-figma-gear mq-figma-gear--small" />
        <circle cx="90" cy="75" r="5" className="mq-figma-gear-core" />
        <circle cx="117" cy="77" r="4" className="mq-figma-gear-core" />
        <path d="M73 75 H107 M105 77 H129 M90 58 V92 M117 65 V89" className="mq-figma-gear-tooth-lines" fill="none" />
      </g>
      <path d="M64 86 H129" className="mq-figma-workbench-roller" fill="none" />
      <circle cx="45" cy="80" r="10" className="mq-figma-workbench-bolt" />
      <circle cx="121" cy="80" r="10" className="mq-figma-workbench-bolt" />
      <path d="M51 98 L40 126 M124 88 L134 126" className="mq-figma-arm-leg" fill="none" />
      <path d="M52 72 H131" className="mq-figma-workbench-sensor" fill="none" />
    </g>
  )
}

export function FigmaWorkshopEngineer() {
  return (
    <g className="mq-figma-workshop-engineer" transform="translate(130 7)">
      <ellipse cx="30" cy="116" rx="25" ry="7" className="mq-figma-engineer-shadow" />
      <path d="M22 45 C16 51 13 61 14 76 L18 107 L43 107 L47 75 C49 59 43 49 36 44 Z" className="mq-figma-engineer-shirt" />
      <path d="M20 58 H43 L39 108 H24 Z" className="mq-figma-engineer-apron" />
      <path d="M24 45 L18 58 M37 45 L43 58" className="mq-figma-engineer-strap" fill="none" />
      <circle cx="31" cy="31" r="16" className="mq-figma-engineer-face" />
      <path d="M16 30 C18 13 43 9 47 28 C40 22 34 18 23 25 C21 27 19 29 16 30 Z" className="mq-figma-engineer-hair" />
      <path d="M24 31 H25 M36 31 H37" className="mq-figma-engineer-eye" fill="none" />
      <path d="M27 39 C31 42 35 42 38 38" className="mq-figma-engineer-smile" fill="none" />
      <path d="M18 62 C4 68 2 82 12 88" className="mq-figma-engineer-arm" fill="none" />
      <path d="M43 62 C57 68 63 78 70 91" className="mq-figma-engineer-arm mq-figma-engineer-arm--tool" fill="none" />
      <circle cx="12" cy="88" r="5" className="mq-figma-engineer-hand" />
      <circle cx="70" cy="91" r="5" className="mq-figma-engineer-hand" />
      <g className="mq-figma-engineer-caliper" transform="translate(58 76) rotate(-24)">
        <path d="M0 10 H56" />
        <path d="M9 10 L3 0 M20 10 L16 2 M43 10 L53 0" />
        <path d="M26 5 H38 V15 H26 Z" />
      </g>
      <path d="M24 108 L22 130 M39 108 L43 130" className="mq-figma-engineer-leg" fill="none" />
    </g>
  )
}

/** 加工台：工作台 + 立柱机械臂（静态） */
export function FigmaArmWorkbench() {
  return (
    <g className="mq-figma-workbench-scene">
      <FigmaArmWorkbenchBase />
      <g className="mq-figma-arm-pivot">
        <path d="M115 39 C134 45 149 57 164 76" strokeWidth="10" strokeLinecap="round" className="mq-figma-arm-link" fill="none" />
        <path d="M158 71 L174 74 L168 85 L155 79 Z" className="mq-figma-arm-nozzle" />
        <circle cx="164" cy="76" r="12" className="mq-figma-arm-joint mq-figma-arm-tip" />
        <circle cx="164" cy="76" r="5" className="mq-figma-arm-spark" opacity="0" />
      </g>
      <FigmaWorkshopEngineer />
    </g>
  )
}

export function FigmaConveyorBelt({ variant }: { variant: 'blue' | 'green' }) {
  const c = FIGMA_CONVEYOR
  const slotClass = variant === 'green' ? 'mq-figma-belt-slotG' : 'mq-figma-belt-slot'
  const slots = [146, 188, 230, 272, 548, 590, 632, 674, 716, 758, 800, 842]

  return (
    <g className="mq-figma-conveyor">
      <ellipse cx="538" cy="158" rx="432" ry="18" className="mq-figma-belt-ground" />
      <circle cx={c.leftRoller.cx} cy={c.leftRoller.cy} r={c.leftRoller.r} className="mq-figma-roller" />
      <circle cx={c.rightRoller.cx} cy={c.rightRoller.cy} r={c.rightRoller.r} className="mq-figma-roller" />
      <circle cx={c.leftRoller.cx} cy={c.leftRoller.cy} r="5" className="mq-figma-roller-cap" />
      <circle cx={c.rightRoller.cx} cy={c.rightRoller.cy} r="5" className="mq-figma-roller-cap" />
      <path d={c.front} className="mq-figma-belt-front" />
      <path d={c.top} className="mq-figma-belt-top" />
      <path d={c.lip} className="mq-figma-belt-lip" fill="none" />
      <path d={c.railLeft} className="mq-figma-belt-rail" fill="none" />
      <path d={c.railRight} className="mq-figma-belt-rail" fill="none" />
      {c.packages.map((pkg, i) => {
        const box = figmaIsoPackage(pkg.x, pkg.y)
        return (
          <g key={i} className="mq-figma-belt-package">
            <path d={box.left} className="mq-figma-package-face--left" />
            <path d={box.right} className="mq-figma-package-face--right" />
            <path d={box.top} className="mq-figma-package-face--top" />
          </g>
        )
      })}
      <g className="mq-figma-belt-slots">
        {slots.map((x) => (
          <rect key={x} x={x} y={c.slotY} width="18" height="8" rx="2" className={slotClass} />
        ))}
      </g>
    </g>
  )
}

export function FigmaRobotStanding() {
  return (
    <g className="mq-figma-robot mq-figma-robot--idle mq-figma-assistant-robot">
      <ellipse cx="55" cy="128" rx="52" ry="15" className="mq-figma-robot-shadow" />
      <ellipse cx="55" cy="123" rx="39" ry="8" className="mq-figma-robot-glow" />
      <line x1="55" y1="4" x2="55" y2="17" className="mq-figma-robot-antenna" strokeWidth="3" />
      <circle cx="55" cy="2" r="5" className="mq-figma-robot-antenna-tip" />
      <circle cx="55" cy="38" r="30" className="mq-figma-robot-head" />
      <rect x="35" y="28" width="40" height="19" rx="10" className="mq-figma-robot-visor" />
      <path d="M45 37 C47 34 50 34 52 37 M59 37 C61 34 64 34 66 37" className="mq-figma-robot-eye" fill="none" />
      <path d="M48 45 C53 50 60 50 65 45" className="mq-figma-robot-mouth" fill="none" />
      <circle cx="28" cy="39" r="8" className="mq-figma-robot-ear" />
      <circle cx="82" cy="39" r="8" className="mq-figma-robot-ear" />
      <rect x="43" y="68" width="24" height="7" rx="3.5" className="mq-figma-robot-neck" />
      <rect x="27" y="72" width="56" height="43" rx="18" className="mq-figma-robot-body" />
      <rect x="38" y="87" width="34" height="14" rx="7" className="mq-figma-robot-chest" />
      <text x="44" y="98" className="mq-figma-robot-idle-label">
        IDLE
      </text>
      <path d="M27 80 C9 82 7 99 20 106" className="mq-figma-robot-arm-link" fill="none" />
      <path d="M83 80 C101 82 104 99 91 108" className="mq-figma-robot-arm-link mq-figma-robot-arm-link--wave" fill="none" />
      <circle cx="20" cy="106" r="8" className="mq-figma-robot-limb" />
      <circle cx="91" cy="108" r="8" className="mq-figma-robot-limb" />
      <path d="M88 104 L86 94 M91 103 L94 94" className="mq-figma-robot-wave-fingers" fill="none" />
      <rect x="36" y="112" width="16" height="25" rx="7" className="mq-figma-robot-limb" />
      <rect x="58" y="112" width="16" height="25" rx="7" className="mq-figma-robot-limb" />
    </g>
  )
}

export function FigmaRobotLaptopOverlay() {
  return (
    <>
      <rect x="14" y="88" width="52" height="32" rx="4" className="mq-figma-robot-laptop-base" />
      <rect x="18" y="92" width="44" height="22" rx="2" className="mq-figma-robot-laptop-screen" />
      <path d="M20 96 H60 M20 100 H56 M20 104 H52" className="mq-figma-robot-laptop-lines" fill="none" strokeWidth="1.5" />
    </>
  )
}

/** 支线卡片底 — 须在主 SVG 文档树内渲染，勿经 <use>（外部 CSS 无法命中 shadow 内容） */
export function FigmaBranchCardShell({
  width = figmaSidecarCardWidth(),
  height = FIGMA_SIDECAR.cardHeight,
}: {
  width?: number
  height?: number
} = {}) {
  return (
    <>
      <rect width={width} height={height} rx="12" className="mq-figma-branch-card mq-figma-shadow" />
      <path d={`M20 96 H${width - 20}`} className="mq-figma-branch-divider" fill="none" />
    </>
  )
}

function FigmaBranchPlate({ children }: { children: ReactNode }) {
  return (
    <g className="mq-figma-branch-plate">
      <path d="M28 78 L84 78 L80 92 L32 92 Z" className="mq-figma-branch-plate-top" />
      <path d="M28 78 L32 92 L32 96 L28 82 Z" className="mq-figma-branch-plate-side" />
      {children}
    </g>
  )
}

export function FigmaBranchBellIcon({ id, tone }: { id?: string; tone: 'blue' | 'green' | 'purple' | 'orange' }) {
  return (
    <g {...(id ? { id } : {})} className="mq-figma-branch-icon">
      <FigmaBranchPlate>
        <path
          d="M56 28 C48 28 44 34 44 40 L44 44 L40 52 L72 52 L68 44 L68 40 C68 34 64 28 56 28 Z"
          className={`mq-figma-branch-bell mq-figma-branch-icon-fill mq-figma-branch-icon-fill--${tone}`}
        />
        <path
          d="M50 54 C50 58 52 62 56 62 C60 62 62 58 62 54"
          className={`mq-figma-branch-bell-clapper mq-figma-stroke-${tone === 'green' ? 'green' : tone === 'purple' ? 'purple' : tone === 'orange' ? 'orange' : 'blue'}`}
          fill="none"
          strokeWidth="2"
        />
        <circle
          cx="56"
          cy="24"
          r="3"
          className={`mq-figma-branch-bell-knob mq-figma-stroke-${tone === 'green' ? 'green' : tone === 'purple' ? 'purple' : tone === 'orange' ? 'orange' : 'blue'}`}
        />
      </FigmaBranchPlate>
    </g>
  )
}

export function FigmaBranchDocIcon({ id, tone }: { id?: string; tone: 'blue' | 'green' | 'purple' | 'orange' }) {
  return (
    <g {...(id ? { id } : {})} className="mq-figma-branch-icon">
      <FigmaBranchPlate>
        <path
          d="M44 22 L68 22 L72 58 L40 58 Z"
          className={`mq-figma-branch-doc mq-figma-branch-icon-fill mq-figma-branch-icon-fill--${tone}`}
        />
        <path d="M44 22 L50 22 L50 30 L44 30 Z" className="mq-figma-branch-doc-fold" />
        <path
          d="M46 36 H66 M46 42 H66 M46 48 H58"
          className={`mq-figma-branch-doc-lines mq-figma-stroke-${tone === 'green' ? 'green' : tone === 'purple' ? 'purple' : tone === 'orange' ? 'orange' : 'blue'}`}
          fill="none"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </FigmaBranchPlate>
    </g>
  )
}

export function FigmaBranchPdfIcon({ id, tone }: { id?: string; tone: 'blue' | 'green' | 'purple' | 'orange' }) {
  return (
    <g {...(id ? { id } : {})} className="mq-figma-branch-icon">
      <FigmaBranchPlate>
        <path
          d="M44 22 L68 22 L72 58 L40 58 Z"
          className={`mq-figma-branch-doc mq-figma-branch-icon-fill mq-figma-branch-icon-fill--${tone}`}
        />
        <text x="48" y="50" fontSize="16" fontWeight="700" className="mq-figma-branch-pdf-label">
          PDF
        </text>
      </FigmaBranchPlate>
    </g>
  )
}
