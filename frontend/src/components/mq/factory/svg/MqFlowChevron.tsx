type MqFlowChevronProps = {
  running?: boolean
  vertical?: boolean
}

export default function MqFlowChevron({ running = false, vertical = false }: MqFlowChevronProps) {
  return (
    <div
      className={`mq-factory-flow${running ? ' mq-factory-flow--fast' : ''}${vertical ? ' mq-factory-flow--vertical' : ''}`}
      aria-hidden
    >
      <svg viewBox="0 0 28 20" className="mq-factory-flow__svg">
        <path d="M4 10 L10 5 L10 8 L18 8 L18 5 L24 10 L18 15 L18 12 L10 12 L10 15 Z" className="mq-factory-flow__chev mq-factory-flow__chev--a" />
        <path d="M-6 10 L0 5 L0 8 L8 8 L8 5 L14 10 L8 15 L8 12 L0 12 L0 15 Z" className="mq-factory-flow__chev mq-factory-flow__chev--b" />
      </svg>
    </div>
  )
}
