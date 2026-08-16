import '@/styles/app-backdrop.css'

export type AppBackdropVariant = 'auth' | 'app'

type AppBackdropProps = {
  /** auth：登录/注册/分享；app：登录后主界面 */
  variant?: AppBackdropVariant
}

/** 全站固定全屏背景（filex-bg.jpg） */
export default function AppBackdrop({ variant = 'app' }: AppBackdropProps) {
  return (
    <div className="app-backdrop" aria-hidden>
      <img
        className="app-backdrop__img"
        src="/filex-bg.jpg"
        alt=""
        decoding="async"
        fetchPriority="high"
      />
      <div className={`app-backdrop__scrim app-backdrop__scrim--${variant}`} />
    </div>
  )
}
