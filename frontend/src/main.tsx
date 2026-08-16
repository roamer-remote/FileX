import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './styles/apple-tokens.css'
import './styles/cyber.css'
import './styles/buttons.css'
import './styles/delete-action.css'
import './styles/high-end.css'
import './styles/app-backdrop.css'
import './styles/markdown-host.css'
import './styles/markdown-hljs.css'
import 'katex/dist/katex.min.css'
import './styles/page-heading.css'
import './styles/responsive.css'
import './styles/auth.css'
import './i18n'
import { useThemeStore } from './stores/themeStore'
import { useAuthStore } from './stores/authStore'
useThemeStore.getState().hydrateFromStorage()
useAuthStore.getState().loadFromStorage()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
