import type { FigmaWorkshopTheme } from './mqFigmaTheme'

const CHEVRON_X = [274, 520, 765] as const

type MqFigmaFactoryChevronsProps = {
  theme: FigmaWorkshopTheme
  isRunning: boolean
}

export default function MqFigmaFactoryChevrons({ theme, isRunning }: MqFigmaFactoryChevronsProps) {
  return (
    <>
      {CHEVRON_X.map((x, index) => {
        const delayClass =
          index === 1 ? ' mq-figma-flow-chev-live--2' : index === 2 ? ' mq-figma-flow-chev-live--3' : ''
        const animClass = isRunning ? ` mq-figma-flow-chev-live${delayClass}` : ''
        return (
          <text
            key={x}
            x={x}
            y="116"
            fontSize="32"
            fontWeight="700"
            className={`${theme.chevronClass}${animClass}`}
            fontFamily="sans-serif"
          >
            »
          </text>
        )
      })}
    </>
  )
}
