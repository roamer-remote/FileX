import { ConfigProvider, theme as antTheme } from 'antd'
import { createRoot } from 'react-dom/client'
import { I18nextProvider } from 'react-i18next'
import i18n from '@/i18n'
import '@/styles/apple-tokens.css'
import '@/styles/cyber.css'
import '@/styles/buttons.css'
import '@/styles/delete-action.css'
import '@/styles/high-end.css'
import '@/styles/app-backdrop.css'
import '@/styles/markdown-host.css'
import '@/styles/markdown-hljs.css'
import '@/styles/page-heading.css'
import '@/styles/responsive.css'
import '@/styles/auth.css'
import EvidenceApp from './EvidenceApp'

function readParams() {
  const params = new URLSearchParams(window.location.search)
  const sceneRaw = params.get('scene')
  const scene =
    sceneRaw === 'progress' ||
    sceneRaw === 'multi-queue' ||
    sceneRaw === 'extract-running' ||
    sceneRaw === 'extract-idle' ||
    sceneRaw === 'default'
      ? sceneRaw
      : 'default'
  return {
    theme: params.get('theme') === 'light' ? 'light' : 'dark',
    mode: params.get('mode') === 'user' ? 'user' : 'admin',
    scene,
  } as const
}

function bootstrap() {
  const { theme, mode, scene } = readParams()
  document.documentElement.setAttribute('data-theme', theme)
  document.body.style.background = theme === 'light' ? '#f8fafc' : '#0a0e1a'

  const rootEl = document.getElementById('root')
  if (!rootEl) return

  createRoot(rootEl).render(
    <ConfigProvider
      theme={{
        algorithm: theme === 'light' ? antTheme.defaultAlgorithm : antTheme.darkAlgorithm,
      }}
    >
      <I18nextProvider i18n={i18n}>
        <EvidenceApp mode={mode} scene={scene} />
      </I18nextProvider>
    </ConfigProvider>,
  )
}

bootstrap()
