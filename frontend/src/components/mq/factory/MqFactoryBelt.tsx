type MqFactoryBeltProps = {
  running?: boolean
}

export default function MqFactoryBelt({ running = false }: MqFactoryBeltProps) {
  return (
    <div
      className={`mq-factory-belt${running ? ' mq-factory-belt--fast' : ''}`}
      aria-hidden
    >
      <div className="mq-factory-belt__rail" />
      <div className="mq-factory-belt__rollers">
        {Array.from({ length: 3 }, (_, i) => (
          <span key={i} className="mq-factory-belt__roller" />
        ))}
      </div>
    </div>
  )
}
