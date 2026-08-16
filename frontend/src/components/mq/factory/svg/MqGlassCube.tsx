import type { ReactNode } from 'react'
import { glassGradientIds, isoCubePaths } from './mqIsometry'

type MqGlassCubeProps = {
  idPrefix: string
  cx?: number
  cy?: number
  size?: number
  glow?: boolean
  className?: string
  children?: ReactNode
}

export default function MqGlassCube({
  idPrefix,
  cx = 60,
  cy = 52,
  size = 16,
  glow = false,
  className = '',
  children,
}: MqGlassCubeProps) {
  const ids = glassGradientIds(idPrefix)
  const paths = isoCubePaths(cx, cy, size)

  return (
    <g className={`mq-glass-cube ${className}`.trim()} filter={glow ? `url(#${ids.glow})` : undefined}>
      <defs>
        <linearGradient id={ids.top} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.28" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0.08" />
        </linearGradient>
        <linearGradient id={ids.left} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.16" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0.32" />
        </linearGradient>
        <linearGradient id={ids.right} x1="100%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.12" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0.26" />
        </linearGradient>
        <filter id={ids.glow} x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <path d={paths.edge} className="mq-glass-cube__edge" fill="none" />
      <path d={paths.left} className="mq-glass-cube__face" fill={`url(#${ids.left})`} />
      <path d={paths.right} className="mq-glass-cube__face" fill={`url(#${ids.right})`} />
      <path d={paths.top} className="mq-glass-cube__face mq-glass-cube__face--top" fill={`url(#${ids.top})`} />
      <path d={`M${cx - size * 0.866} ${cy} L${cx} ${cy - size * 0.5} L${cx + size * 0.866} ${cy}`} className="mq-glass-cube__highlight" fill="none" />
      {children}
    </g>
  )
}
