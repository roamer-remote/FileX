/** 提取正文 pet：内联 SVG，供 CSS 分部件动画（眨眼、招手等）。 */
export default function MqRobotPetSprite({ idPrefix = 'mqRobot' }: { idPrefix?: string }) {
  const bodyGrad = `${idPrefix}BodyGrad`
  const faceGrad = `${idPrefix}FaceGrad`
  const glow = `${idPrefix}Glow`

  return (
    <svg
      className="mq-robot-pet"
      viewBox="0 0 96 96"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <defs>
        <linearGradient id={bodyGrad} x1="24" y1="20" x2="72" y2="80" gradientUnits="userSpaceOnUse">
          <stop stopColor="#1d4ed8" />
          <stop offset="1" stopColor="#00c7d4" />
        </linearGradient>
        <linearGradient id={faceGrad} x1="30" y1="34" x2="66" y2="58" gradientUnits="userSpaceOnUse">
          <stop stopColor="#0f172a" />
          <stop offset="1" stopColor="#1e3a5f" />
        </linearGradient>
        <filter id={glow} x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <g className="mq-robot-pet__head-group">
        <g className="mq-robot-pet__antenna">
          <line x1="48" y1="10" x2="48" y2="18" stroke="#64d2ff" strokeWidth="3" strokeLinecap="round" />
          <circle className="mq-robot-pet__antenna-tip" cx="48" cy="8" r="4" fill="#ffd60a" filter={`url(#${glow})`} />
        </g>

        <rect className="mq-robot-pet__head" x="26" y="18" width="44" height="36" rx="12" fill={`url(#${bodyGrad})`} />
        <rect x="30" y="28" width="36" height="22" rx="8" fill={`url(#${faceGrad})`} />

        <circle className="mq-robot-pet__eye mq-robot-pet__eye--left" cx="40" cy="39" r="4.5" fill="#64d2ff" />
        <circle className="mq-robot-pet__eye mq-robot-pet__eye--right" cx="56" cy="39" r="4.5" fill="#64d2ff" />

        <rect
          className="mq-robot-pet__mouth"
          x="38"
          y="46"
          width="20"
          height="3"
          rx="1.5"
          fill="#94a3b8"
        />
      </g>

      <rect className="mq-robot-pet__torso" x="22" y="48" width="52" height="34" rx="14" fill={`url(#${bodyGrad})`} />
      <rect x="34" y="58" width="28" height="16" rx="6" fill="#0f172a" opacity="0.35" />
      <circle
        className="mq-robot-pet__chest-light"
        cx="48"
        cy="66"
        r="5"
        fill="#ffd60a"
        filter={`url(#${glow})`}
      />

      <g className="mq-robot-pet__arm mq-robot-pet__arm--left">
        <rect x="10" y="52" width="14" height="8" rx="4" fill="#0071e3" />
      </g>
      <g className="mq-robot-pet__arm mq-robot-pet__arm--right">
        <rect x="70" y="52" width="14" height="8" rx="4" fill="#00c7d4" />
      </g>

      <g className="mq-robot-pet__legs">
        <rect className="mq-robot-pet__leg mq-robot-pet__leg--left" x="30" y="80" width="12" height="10" rx="5" fill="#1d4ed8" />
        <rect className="mq-robot-pet__leg mq-robot-pet__leg--right" x="54" y="80" width="12" height="10" rx="5" fill="#00a8c4" />
      </g>
    </svg>
  )
}
