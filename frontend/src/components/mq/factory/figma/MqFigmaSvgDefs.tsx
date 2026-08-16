/** Figma 工厂 SVG 全局 defs（阴影滤镜、3D 深度渐变等） */
export default function MqFigmaSvgDefs() {
  return (
    <svg aria-hidden width={0} height={0} style={{ position: 'absolute' }}>
      <defs>
        <filter id="mq-figma-shadow" x="-25%" y="-25%" width="160%" height="170%">
          <feDropShadow dx="0" dy="10" stdDeviation="14" floodColor="#5a8fca" floodOpacity="0.22" />
        </filter>
        <filter id="mq-figma-shadow-3d" x="-30%" y="-30%" width="170%" height="180%">
          <feDropShadow dx="0" dy="12" stdDeviation="18" floodColor="#4a6f9a" floodOpacity="0.18" />
          <feDropShadow dx="0" dy="4" stdDeviation="6" floodColor="#3a5f8a" floodOpacity="0.1" />
        </filter>
        {/* 3D 面板纵向渐变 */}
        <linearGradient id="mq-figma-panel-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fafcff" />
          <stop offset="100%" stopColor="#eef3f8" />
        </linearGradient>
        {/* 3D 传送带纵向渐变 */}
        <linearGradient id="mq-figma-belt-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f4faff" />
          <stop offset="100%" stopColor="#ccddf0" />
        </linearGradient>
        <linearGradient id="mq-figma-belt-front-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#c5d9ef" />
          <stop offset="100%" stopColor="#a8c4e0" />
        </linearGradient>
      </defs>
    </svg>
  )
}
