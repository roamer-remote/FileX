type SidecarIconKind = 'bell' | 'document'

export function MqSidecarIcon({ kind }: { kind: SidecarIconKind }) {
  if (kind === 'bell') {
    return (
      <svg viewBox="0 0 32 32" className="mq-sidecar-icon" aria-hidden>
        <path
          d="M16 6 C12 6 10 9 10 12 L10 14 L8 18 L24 18 L22 14 L22 12 C22 9 20 6 16 6 Z"
          className="mq-sidecar-icon__body"
        />
        <path d="M13 20 C13 22 14.5 24 16 24 C17.5 24 19 22 19 20" className="mq-sidecar-icon__clapper" fill="none" strokeWidth="1.5" />
        <circle cx="16" cy="5" r="2" className="mq-sidecar-icon__knob" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 32 32" className="mq-sidecar-icon" aria-hidden>
      <path d="M10 8 L22 8 L24 26 L8 26 Z" className="mq-sidecar-icon__doc" />
      <path d="M12 12 L20 12 M12 16 L20 16 M12 20 L17 20" className="mq-sidecar-icon__lines" fill="none" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M10 8 L14 8 L14 12 L10 12 Z" className="mq-sidecar-icon__fold" />
    </svg>
  )
}
