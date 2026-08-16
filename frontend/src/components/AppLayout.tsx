import { useCallback, useEffect, useRef, useState } from 'react'
import { Outlet, useNavigate, NavLink, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons'
import { useAuthStore } from '@/stores/authStore'
import { useFoldersStore } from '@/stores/foldersStore'
import Sidebar from './Sidebar'
import NavMenuLabel from './NavMenuLabel'
import AdminEnterpriseDataNavMenu from './AdminEnterpriseDataNavMenu'
import AdminOpsNavMenu from './AdminOpsNavMenu'
import ThemeSwitcher from './ThemeSwitcher'
import LanguageSwitcher from './LanguageSwitcher'
import RuntimeEnvPill from './RuntimeEnvPill'
import AccountOverviewModal from './AccountOverviewModal'
import UserNavAvatar from './UserNavAvatar'
import AppLogo from './AppLogo'
import AgentSkillInstallPrompt from './AgentSkillInstallPrompt'
import MqWorkerPet from './MqWorkerPet'
import FolderFloatingPanel from './FolderFloatingPanel'
import FloatingKbToolbar from './knowledge/FloatingKbToolbar'
import GettingStartedHelpModal, { type HelpSection } from './GettingStartedHelpModal'
import GettingStartedHelpFab from './GettingStartedHelpFab'
import ApiKeyOnboardingGate, { type ApiKeyGateState } from './ApiKeyOnboardingGate'
import {
  markGettingStartedSeen,
  resolveGettingStartedAutoOpenState,
  type GettingStartedAutoOpenState,
} from '@/lib/gettingStartedStorage'
import { initialApiKeyGateState } from '@/lib/apiKeyOnboardingGate'
import { MqStatusProvider } from '@/providers/MqStatusProvider'
import { useKbIndexWebSocket } from '@/hooks/useKbIndexWebSocket'
import { useKbIndexStatusPoll } from '@/hooks/useKbIndexStatusPoll'
import { useSystemSettingsStore } from '@/stores/systemSettingsStore'
import { isKbIndexRoute, isKnowledgeFileListRoute, isKnowledgeLobbyRoute } from '@/lib/wikiLinkEvents'
import { patchSidebarUiState } from '@/lib/uiStateSync'
import './AppLayout.css'

const SIDEBAR_COLLAPSED_KEY = 'filex_sidebar_collapsed'

export default function AppLayout() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const setFolderSelected = useFoldersStore((s) => s.setSelected)
  const location = useLocation()
  const navLinksRef = useRef<HTMLElement>(null)
  const onKnowledgeRoute = isKnowledgeFileListRoute(location.pathname) && !isKbIndexRoute(location.pathname)
  const onKbIndexRoute = isKbIndexRoute(location.pathname)
  const onLobbyRoute = isKnowledgeLobbyRoute(location.pathname)
  const onKbPreferencesRoute = location.pathname === '/account/preferences'
  const onAgentRunsRoute = location.pathname.startsWith('/agent/runs')

  useKbIndexWebSocket(!!user)
  useKbIndexStatusPoll(!!user)

  useEffect(() => {
    if (!user) return
    void useSystemSettingsStore.getState().load()
    const reloadSettings = () => {
      void useSystemSettingsStore.getState().load()
    }
    window.addEventListener('filex:system-settings-changed', reloadSettings)
    window.addEventListener('filex:user-settings-changed', reloadSettings)
    return () => {
      window.removeEventListener('filex:system-settings-changed', reloadSettings)
      window.removeEventListener('filex:user-settings-changed', reloadSettings)
    }
  }, [user])

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1'
    } catch {
      return false
    }
  })
  const [accountOpen, setAccountOpen] = useState(false)
  const [helpModalOpen, setHelpModalOpen] = useState(false)
  const [helpModalSection, setHelpModalSection] = useState<HelpSection>('start')
  const [helpModalMarkSeenOnClose, setHelpModalMarkSeenOnClose] = useState(false)
  const [gettingStartedAutoOpen, setGettingStartedAutoOpen] = useState<GettingStartedAutoOpenState>(
    () => resolveGettingStartedAutoOpenState(user?.id, initialApiKeyGateState(user?.id)),
  )
  const [apiKeyGate, setApiKeyGate] = useState<ApiKeyGateState>(() =>
    initialApiKeyGateState(user?.id),
  )

  useEffect(() => {
    setApiKeyGate(initialApiKeyGateState(user?.id))
  }, [user?.id])

  useEffect(() => {
    setGettingStartedAutoOpen(resolveGettingStartedAutoOpenState(user?.id, apiKeyGate))
  }, [user?.id, apiKeyGate])

  useEffect(() => {
    if (gettingStartedAutoOpen !== 'open' || apiKeyGate !== 'ok') return
    setHelpModalSection('start')
    setHelpModalMarkSeenOnClose(true)
    setHelpModalOpen(true)
  }, [gettingStartedAutoOpen, apiKeyGate])

  const openHelpModal = useCallback((section: HelpSection, markSeenOnClose: boolean) => {
    setHelpModalSection(section)
    setHelpModalMarkSeenOnClose(markSeenOnClose)
    setHelpModalOpen(true)
  }, [])

  const closeHelpModal = useCallback(() => {
    setHelpModalOpen(false)
    if (helpModalMarkSeenOnClose && user?.id) markGettingStartedSeen(user.id)
  }, [helpModalMarkSeenOnClose, user?.id])

  const helpModalVisible =
    helpModalOpen && (helpModalSection === 'system' || apiKeyGate === 'ok')

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed ? '1' : '0')
    } catch {
      /* ignore */
    }
    patchSidebarUiState()
  }, [sidebarCollapsed])

  useEffect(() => {
    if (location.pathname === '/account/preferences') {
      setAccountOpen(false)
    }
  }, [location.pathname])

  useEffect(() => {
    const nav = navLinksRef.current
    if (!nav) return
    const active = nav.querySelector<HTMLElement>('.nav-link.active')
    active?.scrollIntoView({ inline: 'nearest', block: 'nearest' })
  }, [location.pathname])

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <MqStatusProvider enabled={!!user}>
    <div className={'app-layout' + (sidebarCollapsed ? ' app-layout--sidebar-collapsed' : '')}>
      <header className="global-nav">
        <div className="nav-content">
          <div className="nav-left">
            <AppLogo placement="nav" to="/" />
            <button
              type="button"
              className="nav-sidebar-toggle"
              onClick={() => setSidebarCollapsed((v) => !v)}
              aria-expanded={!sidebarCollapsed}
              aria-controls="app-sidebar"
              title={sidebarCollapsed ? t('appLayout.expandSidebar') : t('appLayout.collapseSidebar')}
            >
              {sidebarCollapsed ? <MenuUnfoldOutlined aria-hidden /> : <MenuFoldOutlined aria-hidden />}
            </button>
            <nav ref={navLinksRef} className="nav-links" aria-label="Main navigation">
              {user ? (
                <>
                  <NavLink
                    to="/"
                    className={
                      'nav-link nav-link--with-icon nav-link--knowledge' + (onKnowledgeRoute ? ' active' : '')
                    }
                    aria-current={onKnowledgeRoute ? 'page' : undefined}
                    onClick={() => setFolderSelected('all')}
                  >
                    <NavMenuLabel icon="lobby">{t('sidebar.allFiles')}</NavMenuLabel>
                  </NavLink>
                  <NavLink
                    to="/knowledge-base"
                    className={'nav-link nav-link--with-icon' + (onKbIndexRoute ? ' active' : '')}
                    aria-current={onKbIndexRoute ? 'page' : undefined}
                  >
                    <NavMenuLabel icon="knowledgeIndex">{t('appLayout.knowledgeIndex')}</NavMenuLabel>
                  </NavLink>
                  <NavLink
                    to="/agent/runs"
                    className={'nav-link nav-link--with-icon' + (onAgentRunsRoute ? ' active' : '')}
                    aria-current={onAgentRunsRoute ? 'page' : undefined}
                  >
                    <NavMenuLabel icon="mqMonitor">{t('appLayout.agentRuns')}</NavMenuLabel>
                  </NavLink>
                </>
              ) : null}
              {user && !user.is_admin ? (
                <NavLink
                  to="/account/preferences"
                  className={
                    'nav-link nav-link--with-icon' + (onKbPreferencesRoute ? ' active' : '')
                  }
                  aria-current={onKbPreferencesRoute ? 'page' : undefined}
                >
                  <NavMenuLabel icon="kbPreferences">{t('appLayout.kbPreferences')}</NavMenuLabel>
                </NavLink>
              ) : null}
              {user?.is_admin ? (
                <>
                  <AdminEnterpriseDataNavMenu />
                  <NavLink
                    to="/admin/skill"
                    className={({ isActive }) => 'nav-link nav-link--with-icon' + (isActive ? ' active' : '')}
                  >
                    <NavMenuLabel icon="skillEditor">{t('appLayout.skillEditor')}</NavMenuLabel>
                  </NavLink>
                  <AdminOpsNavMenu />
                </>
              ) : null}
            </nav>
          </div>
          <div className="nav-right">
            <div className="nav-toolbar-cluster" aria-label={t('appLayout.toolbarClusterAria')}>
              {user ? <AgentSkillInstallPrompt variant="nav" /> : null}
              <RuntimeEnvPill />
              <ThemeSwitcher />
              <LanguageSwitcher />
            </div>
            <div className="user-menu">
              {user?.is_admin ? <span className="admin-indicator">●</span> : null}
              <button
                type="button"
                className="user-display user-display-btn"
                onClick={() => setAccountOpen(true)}
                title={t('appLayout.openAccount')}
                aria-label={t('appLayout.openAccount')}
              >
                <UserNavAvatar />
                <span className="user-display-name">{user?.username}</span>
              </button>
              <button type="button" className="fx-btn fx-btn--text nav-pill-btn" onClick={handleLogout} title={t('appLayout.disconnect')}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 2H3a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h2" />
                  <path d="M10 9l2-2-2-2" />
                  <path d="M12 7H5" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className={'app-body' + (onLobbyRoute ? '' : ' app-body--flush')}>
        <aside id="app-sidebar" className="app-sidebar" aria-hidden={sidebarCollapsed}>
          <Sidebar />
        </aside>
        <main className={'app-main' + (onLobbyRoute ? '' : ' app-main--flush')}>
          <div
            className={
              'app-main-inner' + (onLobbyRoute ? '' : ' app-main-inner--single-card')
            }
          >
            <Outlet />
          </div>
        </main>
      </div>

      <AccountOverviewModal open={accountOpen} onClose={() => setAccountOpen(false)} />
      {user ? (
        <>
          <GettingStartedHelpFab onClick={() => openHelpModal('start', true)} />
          <GettingStartedHelpModal
            open={helpModalVisible}
            initialSection={helpModalSection}
            onDismiss={closeHelpModal}
            onGotIt={closeHelpModal}
          />
          <ApiKeyOnboardingGate userId={user.id} onGateStateChange={setApiKeyGate} />
        </>
      ) : null}
      {user ? <MqWorkerPet /> : null}
      {user ? <FolderFloatingPanel /> : null}
      {user ? <FloatingKbToolbar /> : null}
    </div>
    </MqStatusProvider>
  )
}
