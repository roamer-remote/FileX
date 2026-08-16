import type { ReactNode } from 'react'
import ThemeSwitcher from '@/components/ThemeSwitcher'
import LanguageSwitcher from '@/components/LanguageSwitcher'
import AppBackdrop from '@/components/AppBackdrop'
import '@/styles/auth.css'

type AuthScreenProps = {
  children: ReactNode
}

/** 登录 / 注册共用全屏背景与顶栏控件 */
export default function AuthScreen({ children }: AuthScreenProps) {
  return (
    <div className="auth-screen">
      <AppBackdrop variant="auth" />
      <div className="auth-card">{children}</div>
      <div className="auth-controls">
        <ThemeSwitcher />
        <LanguageSwitcher />
      </div>
    </div>
  )
}
