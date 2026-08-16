type MqFactoryRobotProps = {
  idPrefix: string
  active?: boolean
}

/** 工厂视图专用白机器人（idle 站立 / active 坐笔记本），与设计图一致 */
export default function MqFactoryRobot({ idPrefix, active = false }: MqFactoryRobotProps) {
  const bodyGrad = `${idPrefix}RobotBody`
  const glowId = `${idPrefix}RobotGlow`

  return (
    <svg className="mq-factory-robot-sprite" viewBox="0 0 80 96" aria-hidden>
      <defs>
        <linearGradient id={bodyGrad} x1="20" y1="10" x2="60" y2="90" gradientUnits="userSpaceOnUse">
          <stop stopColor="#f8fafc" />
          <stop offset="1" stopColor="#cbd5e1" />
        </linearGradient>
        <filter id={glowId} x="-30%" y="-20%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="2.5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* 底座光晕 */}
      <ellipse cx="40" cy="88" rx="22" ry="5" className="mq-factory-robot-sprite__base-glow" />
      <ellipse cx="40" cy="86" rx="16" ry="3.5" className="mq-factory-robot-sprite__base" />

      {active ? (
        <g className="mq-factory-robot-sprite__pose mq-factory-robot-sprite__pose--active" filter={`url(#${glowId})`}>
          {/* 坐姿 + 笔记本 */}
          <rect x="22" y="58" width="36" height="22" rx="10" fill={`url(#${bodyGrad})`} />
          <rect x="26" y="48" width="28" height="18" rx="8" fill={`url(#${bodyGrad})`} />
          <circle cx="33" cy="56" r="2.5" className="mq-factory-robot-sprite__eye" />
          <circle cx="47" cy="56" r="2.5" className="mq-factory-robot-sprite__eye" />
          <rect x="18" y="62" width="44" height="26" rx="3" className="mq-factory-robot-sprite__laptop" />
          <rect x="22" y="66" width="36" height="16" rx="2" className="mq-factory-robot-sprite__screen" />
          <line x1="40" y1="88" x2="40" y2="80" className="mq-factory-robot-sprite__antenna" strokeWidth="2" />
          <circle cx="40" cy="78" r="2" className="mq-factory-robot-sprite__antenna-tip" />
        </g>
      ) : (
        <g className="mq-factory-robot-sprite__pose mq-factory-robot-sprite__pose--idle">
          <line x1="40" y1="12" x2="40" y2="18" className="mq-factory-robot-sprite__antenna" strokeWidth="2" />
          <circle cx="40" cy="10" r="2.5" className="mq-factory-robot-sprite__antenna-tip" />
          <rect x="26" y="18" width="28" height="22" rx="9" fill={`url(#${bodyGrad})`} />
          <circle cx="33" cy="28" r="2.8" className="mq-factory-robot-sprite__eye" />
          <circle cx="47" cy="28" r="2.8" className="mq-factory-robot-sprite__eye" />
          <rect x="32" y="33" width="16" height="2" rx="1" className="mq-factory-robot-sprite__mouth" />
          <rect x="22" y="38" width="36" height="28" rx="12" fill={`url(#${bodyGrad})`} />
          <rect x="14" y="42" width="8" height="18" rx="4" fill={`url(#${bodyGrad})`} />
          <rect x="58" y="42" width="8" height="18" rx="4" fill={`url(#${bodyGrad})`} />
          <rect x="26" y="64" width="10" height="16" rx="4" fill={`url(#${bodyGrad})`} />
          <rect x="44" y="64" width="10" height="16" rx="4" fill={`url(#${bodyGrad})`} />
        </g>
      )}
    </svg>
  )
}
