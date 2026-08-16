import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  AppstoreOutlined,
  DatabaseOutlined,
  DownOutlined,
  EnvironmentOutlined,
  FileTextOutlined,
  HolderOutlined,
  HomeOutlined,
  ShareAltOutlined,
  TagOutlined,
  UpOutlined,
} from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useMatchMedia } from '@/hooks/useMatchMedia'
import {
  getVisibleHotspots,
  isPanelVisible,
  parsePanelParam,
  type LobbyHotspotKey,
} from '@/lib/knowledgePanelConfig'
import { UI_STATE_LOCAL_APPLIED_EVENT } from '@/lib/uiStateLocalSnapshot'
import { flushUiStatePatch, patchKbToolbarUiState } from '@/lib/uiStateSync'
import { useSystemSettingsStore } from '@/stores/systemSettingsStore'
import './FloatingKbToolbar.css'

const POS_STORAGE_KEY = 'filex_kb_toolbar_pos'
const COLLAPSED_STORAGE_KEY = 'filex_kb_toolbar_collapsed'
const TOOLBAR_W = 76
const EDGE = 12

type Point = { x: number; y: number }

const HOTSPOT_ICONS: Record<LobbyHotspotKey, ReactNode> = {
  files: <FileTextOutlined aria-hidden />,
  wikiPages: <AppstoreOutlined aria-hidden />,
  wikiLinks: <ShareAltOutlined aria-hidden />,
  libraryMap: <EnvironmentOutlined aria-hidden />,
  tags: <TagOutlined aria-hidden />,
}

function loadStoredPos(): Point | null {
  try {
    const raw = localStorage.getItem(POS_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Point
    if (typeof parsed?.x === 'number' && typeof parsed?.y === 'number') return parsed
  } catch {
    /* ignore */
  }
  return null
}

function loadStoredCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

function defaultPos(): Point {
  if (typeof window === 'undefined') return { x: EDGE, y: EDGE }
  return {
    x: Math.max(EDGE, window.innerWidth - TOOLBAR_W - 16),
    y: EDGE,
  }
}

function clampPos(pos: Point, panelH: number): Point {
  if (typeof window === 'undefined') return pos
  const maxX = Math.max(EDGE, window.innerWidth - TOOLBAR_W - EDGE)
  const maxY = Math.max(EDGE, window.innerHeight - panelH - EDGE)
  return {
    x: Math.min(Math.max(EDGE, pos.x), maxX),
    y: Math.min(Math.max(EDGE, pos.y), maxY),
  }
}

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

type ToolbarNavButtonProps = {
  label: string
  active: boolean
  icon: ReactNode
  onClick: () => void
  variant?: 'lobby' | 'panel'
}

function ToolbarNavButton({ label, active, icon, onClick, variant = 'panel' }: ToolbarNavButtonProps) {
  const className = [
    'floating-kb-toolbar__btn',
    variant === 'lobby' ? 'floating-kb-toolbar__btn--lobby' : '',
    active ? 'is-active' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button type="button" className={className} aria-label={label} onClick={onClick}>
      <span className="floating-kb-toolbar__btn-icon">{icon}</span>
      <span className="floating-kb-toolbar__btn-label">{label}</span>
    </button>
  )
}

type HotspotButtonProps = {
  panelKey: LobbyHotspotKey
  label: string
  active: boolean
  onOpen: () => void
}

function HotspotButton({ panelKey, label, active, onOpen }: HotspotButtonProps) {
  return (
    <ToolbarNavButton
      label={label}
      active={active}
      icon={HOTSPOT_ICONS[panelKey]}
      onClick={onOpen}
    />
  )
}

export default function FloatingKbToolbar() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const isMobile = useMatchMedia('(max-width: 768px)')
  const tagGraphEnabled = useSystemSettingsStore((s) => s.tag_graph_enabled ?? true)

  // 浮动工具栏为全局导航，不受当前目录 scope 限制（子目录下也应能展开全部热点）
  const visibleHotspots = useMemo(
    () => getVisibleHotspots(true, tagGraphEnabled),
    [tagGraphEnabled],
  )

  const [collapsed, setCollapsed] = useState(() => loadStoredCollapsed())
  const [pos, setPos] = useState<Point>(() => clampPos(loadStoredPos() ?? defaultPos(), 120))
  const [dragging, setDragging] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ pointerId: number; startX: number; startY: number; origin: Point } | null>(
    null,
  )

  const onLobby = location.pathname === '/' || location.pathname === ''
  const activePanel = onLobby ? parsePanelParam(searchParams.get('panel')) : null
  const lobbyActive = onLobby && activePanel === null

  const displayKeys: LobbyHotspotKey[] = collapsed ? ['files'] : visibleHotspots

  const persistCollapsed = useCallback((next: boolean) => {
    setCollapsed(next)
    try {
      localStorage.setItem(COLLAPSED_STORAGE_KEY, next ? '1' : '0')
      patchKbToolbarUiState()
    } catch {
      /* ignore */
    }
  }, [])

  const persistPos = useCallback((next: Point) => {
    const panelH = panelRef.current?.offsetHeight ?? 120
    const clamped = clampPos(next, panelH)
    setPos(clamped)
    try {
      localStorage.setItem(POS_STORAGE_KEY, JSON.stringify(clamped))
      patchKbToolbarUiState()
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    const reload = () => {
      const storedPos = loadStoredPos()
      if (storedPos) {
        const panelH = panelRef.current?.offsetHeight ?? 120
        setPos(clampPos(storedPos, panelH))
      }
      setCollapsed(loadStoredCollapsed())
    }
    window.addEventListener(UI_STATE_LOCAL_APPLIED_EVENT, reload)
    return () => window.removeEventListener(UI_STATE_LOCAL_APPLIED_EVENT, reload)
  }, [])

  useEffect(() => {
    if (isMobile) return
    const onResize = () => {
      const panelH = panelRef.current?.offsetHeight ?? 120
      setPos((prev) => clampPos(prev, panelH))
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [isMobile])

  const openPanel = useCallback(
    (key: LobbyHotspotKey) => {
      if (!isPanelVisible(key, true, tagGraphEnabled)) return
      if (onLobby) {
        setSearchParams(
          (prev) => {
            const next = new URLSearchParams(prev)
            next.set('panel', key)
            return next
          },
          { replace: false },
        )
      } else {
        navigate(`/?panel=${key}`)
      }
    },
    [tagGraphEnabled, navigate, onLobby, setSearchParams],
  )

  const goToLobby = useCallback(() => {
    if (onLobby) {
      setSearchParams(
        (prev) => {
          if (!prev.get('panel')) return prev
          const next = new URLSearchParams(prev)
          next.delete('panel')
          return next
        },
        { replace: true },
      )
      return
    }
    navigate('/')
  }, [navigate, onLobby, setSearchParams])

  const onPointerDown = (ev: React.PointerEvent<HTMLDivElement>) => {
    if (isMobile || ev.button !== 0) return
    if (!(ev.target as HTMLElement).closest('.floating-kb-toolbar__drag-handle')) return
    dragRef.current = {
      pointerId: ev.pointerId,
      startX: ev.clientX,
      startY: ev.clientY,
      origin: pos,
    }
    setDragging(true)
    ev.currentTarget.setPointerCapture(ev.pointerId)
  }

  const onPointerMove = (ev: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== ev.pointerId) return
    persistPos({
      x: drag.origin.x + (ev.clientX - drag.startX),
      y: drag.origin.y + (ev.clientY - drag.startY),
    })
  }

  const onPointerUp = (ev: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== ev.pointerId) return
    dragRef.current = null
    setDragging(false)
    if (ev.currentTarget.hasPointerCapture(ev.pointerId)) {
      ev.currentTarget.releasePointerCapture(ev.pointerId)
    }
    void flushUiStatePatch()
  }

  const panelClass =
    'floating-kb-toolbar' +
    (isMobile ? ' floating-kb-toolbar--mobile' : '') +
    (dragging ? ' floating-kb-toolbar--dragging' : '') +
    (collapsed ? ' floating-kb-toolbar--collapsed' : '') +
    (prefersReducedMotion() ? ' floating-kb-toolbar--reduced-motion' : '')

  return (
    <div
      ref={panelRef}
      className={panelClass}
      role="toolbar"
      aria-label={t('knowledge.floatingToolbarAria')}
      style={isMobile ? undefined : { left: pos.x, top: pos.y }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      {!isMobile ? (
        <div className="floating-kb-toolbar__drag-handle" aria-hidden>
          <HolderOutlined />
        </div>
      ) : null}

      <div className="floating-kb-toolbar__buttons" id="floating-kb-toolbar-buttons">
        <ToolbarNavButton
          label={t('knowledge.floatingToolbarLobby')}
          active={lobbyActive}
          icon={<HomeOutlined aria-hidden />}
          onClick={goToLobby}
          variant="lobby"
        />
        {displayKeys.map((key) => (
          <HotspotButton
            key={key}
            panelKey={key}
            label={t(`knowledge.lobbyHotspot.${key}`)}
            active={activePanel === key}
            onOpen={() => openPanel(key)}
          />
        ))}
        {!collapsed ? (
          <ToolbarNavButton
            label={t('appLayout.knowledgeIndex')}
            active={false}
            icon={<DatabaseOutlined aria-hidden />}
            onClick={() => navigate('/knowledge-base')}
          />
        ) : null}
      </div>

      <button
        type="button"
        className="fx-btn fx-btn--text floating-kb-toolbar__collapse-btn"
        aria-expanded={!collapsed}
        aria-controls="floating-kb-toolbar-buttons"
        aria-label={
          collapsed ? t('knowledge.floatingToolbarExpand') : t('knowledge.floatingToolbarCollapse')
        }
        onClick={() => persistCollapsed(!collapsed)}
      >
        {collapsed ? <DownOutlined aria-hidden /> : <UpOutlined aria-hidden />}
      </button>
    </div>
  )
}
