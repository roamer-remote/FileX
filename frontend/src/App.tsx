import { useEffect, useMemo, useState } from 'react'
import { Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom'
import { App as AntdApp, ConfigProvider, Spin, theme } from 'antd'
import { useTranslation } from 'react-i18next'
import zhCN from 'antd/locale/zh_CN'
import enUS from 'antd/locale/en_US'
import { getMe } from '@/api/auth'
import {
  clearAuthStorage,
  getStorageToken,
  isAuthPersistedToLocalStorage,
  setStorageUser,
} from '@/api/index'
import { useAuthStore, type User } from '@/stores/authStore'
import { bootstrapUiStateAfterAuth } from '@/lib/uiStateSync'
import { useThemeStore } from './stores/themeStore'
import AppLayout from './components/AppLayout'
import AppBackdrop from './components/AppBackdrop'
import LoginPage from './pages/Login'
import RegisterPage from './pages/Register'
import SharePage from './pages/Share'
import KnowledgeFilesPage from './pages/KnowledgeFiles'
import KnowledgeBaseIndexPage from './pages/KnowledgeBaseIndex'
import AdminUsersPage from './pages/admin/Users'
import AdminLogsPage from './pages/admin/Logs'
import AdminAllFilesPage from './pages/admin/AllFiles'
import AdminSettingsPage from './pages/admin/Settings'
import AdminMqMonitorPage from './pages/admin/MqMonitor'
import MqTaskMonitorPage from './pages/MqTaskMonitor'
import AgentRunListPage from './pages/AgentRunList'
import AgentRunDetailPage from './pages/AgentRunDetail'
import AdminWorkspacesPage from './pages/admin/Workspaces'
import AdminWorkspaceDetailPage from './pages/admin/WorkspaceDetail'
import AdminSkillEditorPage from './pages/admin/SkillEditor'
import AdminOrganizationPage from './pages/admin/Organization'
import AdminEnterpriseRolesPage from './pages/admin/EnterpriseRoles'
import AdminAgentRunsPage from './pages/admin/AgentRuns'
import AdminKbSearchEvalPage from './pages/admin/KbSearchEval'
import QualityWorkbenchPage from './pages/admin/QualityWorkbench'
import UnknownRoutePage from './pages/UnknownRoute'
import UserPreferencesPage from './pages/account/UserPreferences'
import LicenseRoot from './components/LicenseRoot'

function RedirectFilesToRoot() {
  const location = useLocation()
  return <Navigate to={{ pathname: '/', search: location.search, hash: location.hash }} replace />
}

function ProtectedRoute() {
  const token = getStorageToken()
  const cachedUser = useAuthStore.getState().user
  const [sessionState, setSessionState] = useState<'pending' | 'ok' | 'invalid'>(() => {
    if (!token) return 'invalid'
    if (cachedUser) return 'ok'
    return 'pending'
  })

  useEffect(() => {
    if (!token) {
      setSessionState('invalid')
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const meRes = await getMe({ skipErrorToast: true, skipAuthRedirect: true })
        if (cancelled) return
        const user = meRes.data as User
        const remember = isAuthPersistedToLocalStorage()
        setStorageUser(JSON.stringify(user), remember)
        useAuthStore.getState().setUser(user)
        await bootstrapUiStateAfterAuth()
        if (cancelled) return
        setSessionState('ok')
      } catch {
        if (cancelled) return
        clearAuthStorage()
        useAuthStore.getState().logout()
        setSessionState('invalid')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  if (!token || sessionState === 'invalid') {
    return <Navigate to="/login" replace />
  }
  if (sessionState === 'pending') {
    return (
      <div className="app-session-check">
        <Spin size="large" />
      </div>
    )
  }
  return <Outlet />
}

function AdminRoute() {
  const token = getStorageToken()
  const cachedIsAdmin = useAuthStore.getState().user?.is_admin === true
  const [state, setState] = useState<'pending' | 'ok' | 'denied'>(() => {
    if (!token) return 'denied'
    if (cachedIsAdmin) return 'ok'
    return 'pending'
  })

  useEffect(() => {
    if (!token) {
      setState('denied')
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const meRes = await getMe({ skipErrorToast: true, skipAuthRedirect: true })
        if (cancelled) return
        const user = meRes.data as User
        if (!user.is_admin) {
          setState('denied')
          return
        }
        const remember = isAuthPersistedToLocalStorage()
        setStorageUser(JSON.stringify(user), remember)
        useAuthStore.getState().setUser(user)
        setState('ok')
      } catch {
        if (cancelled) return
        clearAuthStorage()
        useAuthStore.getState().logout()
        setState('denied')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [token])

  if (!token || state === 'denied') {
    return <Navigate to="/" replace />
  }
  if (state === 'pending') {
    return (
      <div className="app-session-check">
        <Spin size="large" />
      </div>
    )
  }
  return <Outlet />
}

function AppShell() {
  return (
    <div className="app-viewport">
      <AppBackdrop variant="app" />
      <div className="app-shell">
        <Outlet />
      </div>
    </div>
  )
}

export default function App() {
  const { i18n } = useTranslation()
  const resolvedMode = useThemeStore((s) => s.resolvedMode)
  const isDark = resolvedMode === 'dark'

  const antTheme = useMemo(
    () => ({
      algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
      token: {
        colorPrimary: isDark ? '#2997ff' : '#0071e3',
        colorLink: isDark ? '#2997ff' : '#0071e3',
        colorLinkHover: isDark ? '#40a9ff' : '#0077ed',
        colorInfo: isDark ? '#2997ff' : '#0066cc',
        ...(isDark
          ? {
              colorBgSpotlight: '#323234',
              colorTextLightSolid: '#f5f5f7',
            }
          : {
              colorSuccess: '#0071e3',
              colorBgSpotlight: '#e8f4fc',
              colorTextLightSolid: '#1d1d1f',
            }),
        borderRadiusLG: 9,
        borderRadius: 6,
        borderRadiusSM: 4,
        fontSize: 17,
        fontSizeSM: 14,
        fontSizeLG: 17,
        lineHeight: 1.47,
        fontFamily:
          'system-ui, -apple-system, BlinkMacSystemFont, Inter, "Noto Sans SC", sans-serif',
      },
      components: {
        Button: {
          primaryShadow: 'none',
          defaultShadow: 'none',
          dangerShadow: 'none',
          controlOutline: isDark ? '#2997ff' : '#0071e3',
          controlOutlineWidth: 2,
          contentLineHeight: 1.29,
          borderRadius: 4,
          defaultBg: isDark ? '#2c2c2e' : '#ffffff',
          defaultBorderColor: isDark ? 'rgba(255, 255, 255, 0.12)' : 'rgba(44, 44, 46, 0.08)',
          defaultColor: isDark ? '#f5f5f7' : '#2c2c2e',
          defaultHoverBg: isDark ? '#333335' : '#f7f8fa',
          defaultHoverBorderColor: isDark ? 'rgba(255, 255, 255, 0.18)' : 'rgba(44, 44, 46, 0.12)',
          defaultHoverColor: isDark ? '#2997ff' : '#0071e3',
          primaryColor: isDark ? '#2997ff' : '#0071e3',
          colorPrimaryHover: isDark ? '#40a9ff' : '#0077ed',
          colorPrimaryActive: isDark ? '#40a9ff' : '#0077ed',
          colorError: '#ff453a',
          colorErrorHover: '#ff6961',
          colorErrorActive: '#ff6961',
          colorText: isDark ? '#a1a1a6' : '#5c5c5e',
          colorLink: isDark ? '#2997ff' : '#0071e3',
          colorLinkHover: isDark ? '#40a9ff' : '#0077ed',
        },
        Card: {
          boxShadowTertiary: 'none',
          boxShadowSecondary: 'none',
          boxShadow: 'none',
        },
        Modal: { boxShadow: 'none' },
        Table: {
          fontSize: 14,
          cellFontSize: 14,
          cellPaddingBlock: 14,
          cellPaddingInline: 16,
        },
        Tabs: {
          horizontalItemGutter: 8,
          horizontalMargin: '0 0 0 0',
          titleFontSize: 17,
        },
        Input: {
          borderRadius: 4,
          paddingBlock: 10,
          paddingInline: 16,
        },
        Select: { borderRadius: 6 },
        Tooltip: {
          colorBgSpotlight: isDark ? '#323234' : '#e8f4fc',
          colorTextLightSolid: isDark ? '#f5f5f7' : '#1d1d1f',
          borderRadius: 6,
        },
      },
    }),
    [isDark],
  )

  return (
    <ConfigProvider locale={i18n.language === 'zh-CN' ? zhCN : enUS} theme={antTheme}>
      <AntdApp>
        <LicenseRoot>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/share/:token" element={<SharePage />} />

          <Route element={<AppShell />}>
              <Route element={<ProtectedRoute />}>
                <Route element={<AppLayout />}>
                  <Route path="/" element={<KnowledgeFilesPage />} />
                  <Route path="/files" element={<RedirectFilesToRoot />} />
                  <Route path="/files/*" element={<RedirectFilesToRoot />} />
                  <Route path="/knowledge-base" element={<KnowledgeBaseIndexPage />} />
                  <Route path="/account/preferences" element={<UserPreferencesPage />} />
                  <Route path="/mq" element={<MqTaskMonitorPage />} />
                  <Route path="/agent/runs" element={<AgentRunListPage />} />
                  <Route path="/agent/runs/:runId" element={<AgentRunDetailPage />} />
                  <Route path="/tags/graph" element={<Navigate to="/" replace />} />
                  <Route path="/settings/api-keys" element={<Navigate to="/" replace />} />
                  <Route path="/settings/password" element={<Navigate to="/" replace />} />
                  <Route path="/settings/account/*" element={<Navigate to="/" replace />} />
                  <Route element={<AdminRoute />}>
                    <Route path="/admin" element={<Navigate to="/admin/users" replace />} />
                    <Route path="/admin/users" element={<AdminUsersPage />} />
                    <Route path="/admin/organization" element={<AdminOrganizationPage />} />
                    <Route path="/admin/enterprise-roles" element={<AdminEnterpriseRolesPage />} />
                    <Route path="/admin/files" element={<AdminAllFilesPage />} />
                    <Route path="/admin/logs" element={<AdminLogsPage />} />
                    <Route path="/admin/license" element={<Navigate to="/admin/settings" replace />} />
                    <Route path="/admin/settings" element={<AdminSettingsPage />} />
                    <Route path="/admin/mq" element={<AdminMqMonitorPage />} />
                    <Route path="/admin/skill" element={<AdminSkillEditorPage />} />
                    <Route path="/admin/agent-runs" element={<AdminAgentRunsPage />} />
                    <Route path="/admin/kb-search-eval" element={<AdminKbSearchEvalPage />} />
                    <Route path="/admin/knowledge-base/quality-workbench" element={<QualityWorkbenchPage />} />
                    <Route path="/admin/workspaces" element={<AdminWorkspacesPage />} />
                    <Route path="/admin/workspaces/:workspaceId" element={<AdminWorkspaceDetailPage />} />
                    <Route path="/admin/external-sync" element={<Navigate to="/admin/users" replace />} />
                  </Route>
                  <Route path="*" element={<UnknownRoutePage />} />
                </Route>
              </Route>
          </Route>
        </Routes>
        </LicenseRoot>
      </AntdApp>
    </ConfigProvider>
  )
}
