type MqPackageStackProps = {
  count: number
  extra?: number
  emptyLabel?: string
}

export default function MqPackageStack({ count, extra = 0, emptyLabel }: MqPackageStackProps) {
  if (count <= 0) {
    return emptyLabel ? <span className="mq-factory-packages__empty">{emptyLabel}</span> : null
  }

  const visible = Math.min(count, 5)
  return (
    <div className="mq-factory-packages mq-factory-packages--stack">
      {Array.from({ length: visible }, (_, i) => (
        <svg
          key={i}
          className="mq-factory-package-block"
          viewBox="0 0 24 20"
          aria-hidden
          style={{ ['--pkg-offset' as string]: i }}
        >
          <path
            d="M4 6 L12 2 L20 6 L20 14 L12 18 L4 14 Z"
            className="mq-factory-package-block__top"
          />
          <path d="M4 6 L4 14 L12 18 L12 10 Z" className="mq-factory-package-block__left" />
          <path d="M12 10 L12 18 L20 14 L20 6 Z" className="mq-factory-package-block__right" />
        </svg>
      ))}
      {extra > 0 ? <span className="mq-factory-packages__more">+{extra}</span> : null}
    </div>
  )
}
