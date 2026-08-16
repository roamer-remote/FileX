import type { ReactNode } from 'react'

type SettingsSectionProps = {
  id: string
  title: string
  description?: string
  /** `flat`: Tab 内仅展示 description + body；标题由 Tab 按钮承担，section 用 aria-label 保留语义 */
  variant?: 'card' | 'flat'
  children: ReactNode
}

export default function SettingsSection({
  id,
  title,
  description,
  variant = 'card',
  children,
}: SettingsSectionProps) {
  const titleId = `${id}-title`
  const isFlat = variant === 'flat'

  return (
    <section
      id={id}
      className={`admin-settings-section${isFlat ? ' admin-settings-section--flat' : ''}`}
      aria-labelledby={isFlat ? undefined : titleId}
      aria-label={isFlat ? title : undefined}
    >
      <header className="admin-settings-section__header">
        {!isFlat ? (
          <h3 id={titleId} className="admin-settings-section__title">
            {title}
          </h3>
        ) : null}
        {description ? <p className="admin-settings-section__desc">{description}</p> : null}
      </header>
      <div className="admin-settings-section__body">{children}</div>
    </section>
  )
}
