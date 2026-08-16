import { Link } from 'react-router-dom'
import './AppLogo.css'

type AppLogoProps = {
  /** auth：登录/注册/分享；app：主界面顶栏固定；nav：内嵌顶栏 */
  placement?: 'auth' | 'app' | 'nav'
  to?: string
}

export default function AppLogo({ placement = 'auth', to = '/' }: AppLogoProps) {
  return (
    <Link
      to={to}
      className={`app-logo app-logo--${placement}`}
      title="FileX"
      aria-label="FileX"
    >
      <img
        src="/filex-logo.png"
        alt=""
        className="app-logo__img"
        decoding="async"
        fetchPriority="high"
      />
    </Link>
  )
}
