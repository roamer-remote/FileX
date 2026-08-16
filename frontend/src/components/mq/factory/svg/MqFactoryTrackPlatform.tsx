type MqFactoryTrackPlatformProps = {
  running?: boolean
  idPrefix: string
}

export default function MqFactoryTrackPlatform({ running = false, idPrefix }: MqFactoryTrackPlatformProps) {
  const stripeId = `${idPrefix}-belt-stripe`
  return (
    <svg
      className={`mq-factory-platform${running ? ' mq-factory-platform--fast' : ''}`}
      viewBox="0 0 640 56"
      preserveAspectRatio="none"
      aria-hidden
    >
      <defs>
        <pattern id={stripeId} width="12" height="12" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
          <rect width="6" height="12" className="mq-factory-platform__stripe-a" />
          <rect x="6" width="6" height="12" className="mq-factory-platform__stripe-b" />
        </pattern>
        <linearGradient id={`${idPrefix}-platform-shade`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.08" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0.22" />
        </linearGradient>
      </defs>
      {/* 等距传送带顶面 */}
      <path
        d="M8 28 L320 12 L632 28 L320 44 Z"
        fill={`url(#${idPrefix}-platform-shade)`}
        className="mq-factory-platform__surface"
      />
      <path
        d="M8 28 L320 12 L632 28 L320 44 Z"
        fill={`url(#${stripeId})`}
        className="mq-factory-platform__belt"
      />
      {/* 前边 */}
      <path d="M8 28 L8 36 L320 52 L320 44 Z" className="mq-factory-platform__front" />
      <path d="M320 44 L320 52 L632 36 L632 28 Z" className="mq-factory-platform__front mq-factory-platform__front--right" />
      {/* 侧栏 */}
      <path d="M8 28 L320 12" className="mq-factory-platform__rail" fill="none" />
      <path d="M632 28 L320 44" className="mq-factory-platform__rail" fill="none" />
    </svg>
  )
}
