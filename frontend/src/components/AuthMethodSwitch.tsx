export type AuthMethodSwitchOption<T extends string> = {
  label: string
  value: T
}

type AuthMethodSwitchProps<T extends string> = {
  value: T
  options: AuthMethodSwitchOption<T>[]
  onChange: (value: T) => void
  ariaLabel: string
}

export default function AuthMethodSwitch<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: AuthMethodSwitchProps<T>) {
  return (
    <div className="auth-method-switch" role="tablist" aria-label={ariaLabel}>
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            className={`auth-method-switch__tab${active ? ' is-active' : ''}`}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
