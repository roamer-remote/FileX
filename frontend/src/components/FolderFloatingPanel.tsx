import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { MinusOutlined } from '@ant-design/icons'
import { Input, Tooltip } from 'antd'
import { useTranslation } from 'react-i18next'
import FolderTreePanel from './FolderTreePanel'
import { useFoldersStore } from '@/stores/foldersStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import {
  folderPanelDimensions,
  folderPanelMaxHeight,
  measureTreeLayout,
} from '@/lib/folderTree'
import {
  panelMotionDelta,
  posBesideAnchor,
} from '@/lib/folderPanelMotion'
import {
  readPanelPosFromLocal,
  readPanelSizeFromLocal,
  UI_STATE_LOCAL_APPLIED_EVENT,
  writePanelPosToLocal,
  writePanelSizeToLocal,
  type PanelSizeLocal,
} from '@/lib/uiStateLocalSnapshot'
import { flushUiStatePatch, patchFoldersUiState } from '@/lib/uiStateSync'
import './FolderFloatingPanel.css'

const EDGE = 12
const MIN_PANEL_W = 280
const MIN_PANEL_H = 200
const MAX_PANEL_W = 540

type Point = { x: number; y: number }
type Size = PanelSizeLocal

function loadStoredPos(wsId: number | null): Point | null {
  return readPanelPosFromLocal(wsId)
}

function loadStoredSize(wsId: number | null): Size | null {
  return readPanelSizeFromLocal(wsId)
}

function defaultPos(width: number, height: number): Point {
  if (typeof window === 'undefined') return { x: 24, y: 80 }
  return {
    x: Math.max(EDGE, 24),
    y: Math.max(EDGE, 80),
  }
}

function clampPos(pos: Point, width: number, height: number): Point {
  if (typeof window === 'undefined') return pos
  const maxX = Math.max(EDGE, window.innerWidth - width - EDGE)
  const maxY = Math.max(EDGE, window.innerHeight - height - EDGE)
  return {
    x: Math.min(Math.max(EDGE, pos.x), maxX),
    y: Math.min(Math.max(EDGE, pos.y), maxY),
  }
}

function clampPanelSize(size: Size, top: number, viewportW: number, viewportH: number): Size {
  const maxW = Math.min(MAX_PANEL_W, Math.max(MIN_PANEL_W, viewportW - EDGE * 2))
  const maxH = Math.max(MIN_PANEL_H, viewportH - top - EDGE)
  return {
    width: Math.min(Math.max(MIN_PANEL_W, size.width), maxW),
    height: Math.min(Math.max(MIN_PANEL_H, size.height), maxH),
  }
}

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export default function FolderFloatingPanel() {
  const { t } = useTranslation()
  const wsId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const panelOpen = useFoldersStore((s) => s.panelOpen)
  const panelMotion = useFoldersStore((s) => s.panelMotion)
  const panelAnchor = useFoldersStore((s) => s.panelAnchor)
  const requestMinimizePanel = useFoldersStore((s) => s.requestMinimizePanel)
  const minimizePanel = useFoldersStore((s) => s.minimizePanel)
  const finishPanelMotion = useFoldersStore((s) => s.finishPanelMotion)
  const tree = useFoldersStore((s) => s.tree)
  const expandedFolderIds = useFoldersStore((s) => s.expandedFolderIds)
  const layout = useMemo(() => measureTreeLayout(tree, expandedFolderIds), [tree, expandedFolderIds])
  const [virtualRootExpanded, setVirtualRootExpanded] = useState(true)
  const [viewportH, setViewportH] = useState(() =>
    typeof window !== 'undefined' ? window.innerHeight : 800,
  )
  const [viewportW, setViewportW] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth : 1200,
  )
  const panelMaxH = useMemo(() => folderPanelMaxHeight(viewportH), [viewportH])
  const layoutSize = useMemo(
    () =>
      folderPanelDimensions(layout, {
        virtualRootExpanded,
        viewportHeight: viewportH,
      }),
    [layout, virtualRootExpanded, viewportH],
  )

  const panelRef = useRef<HTMLDivElement>(null)
  const [customSize, setCustomSize] = useState<Size | null>(() => loadStoredSize(wsId))
  const [measuredHeight, setMeasuredHeight] = useState(layoutSize.height)

  const effectiveWidth = customSize?.width ?? layoutSize.width
  const effectiveHeight = customSize?.height ?? measuredHeight

  const [pos, setPos] = useState<Point>(() =>
    clampPos(
      loadStoredPos(wsId) ?? defaultPos(layoutSize.width, layoutSize.height),
      effectiveWidth,
      effectiveHeight,
    ),
  )
  const dragRef = useRef<{ pointerId: number; startX: number; startY: number; origin: Point } | null>(
    null,
  )
  const resizeRef = useRef<{
    pointerId: number
    startX: number
    startY: number
    origin: Size
  } | null>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const [narrow, setNarrow] = useState(() =>
    typeof window === 'undefined' ? false : window.matchMedia('(max-width: 768px)').matches,
  )
  const [dragging, setDragging] = useState(false)
  const [resizing, setResizing] = useState(false)
  const [folderSearch, setFolderSearch] = useState('')

  const visible = panelOpen || panelMotion === 'exit'

  useLayoutEffect(() => {
    if (panelMotion !== 'enter' || !panelAnchor || narrow) return
    const stored = loadStoredPos(wsId)
    const next = stored
      ? clampPos(stored, effectiveWidth, effectiveHeight)
      : clampPos(posBesideAnchor(panelAnchor, effectiveWidth, effectiveHeight), effectiveWidth, effectiveHeight)
    setPos(next)
  }, [panelMotion, panelAnchor, narrow, wsId, effectiveWidth, effectiveHeight])

  useLayoutEffect(() => {
    if (!visible || prefersReducedMotion()) return
    if (panelMotion === 'idle') return
    const panel = panelRef.current
    if (!panel) return

    const onEnd = (ev: AnimationEvent) => {
      if (ev.target !== panel) return
      if (
        ev.animationName === 'folder-panel-from-trigger' ||
        ev.animationName === 'folder-panel-to-trigger'
      ) {
        finishPanelMotion()
      }
    }
    panel.addEventListener('animationend', onEnd)
    return () => panel.removeEventListener('animationend', onEnd)
  }, [visible, panelMotion, finishPanelMotion])

  useEffect(() => {
    if (!visible || panelMotion === 'idle' || !prefersReducedMotion()) return
    finishPanelMotion()
  }, [visible, panelMotion, finishPanelMotion])

  useLayoutEffect(() => {
    const panel = panelRef.current
    if (!panel || narrow) return
    const sync = () => {
      if (!customSize) {
        setMeasuredHeight(panel.offsetHeight)
      }
    }
    sync()
    const ro = new ResizeObserver(sync)
    ro.observe(panel)
    return () => ro.disconnect()
  }, [narrow, tree, expandedFolderIds, virtualRootExpanded, layoutSize.width, panelMaxH, visible, customSize])

  useLayoutEffect(() => {
    const el = bodyRef.current
    if (!el) return
    const clamp = () => {
      const max = Math.max(0, el.scrollHeight - el.clientHeight)
      if (el.scrollTop > max) el.scrollTop = max
    }
    clamp()
    const id = window.requestAnimationFrame(clamp)
    return () => window.cancelAnimationFrame(id)
  }, [tree, expandedFolderIds, virtualRootExpanded, customSize, effectiveHeight])

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)')
    const onChange = () => setNarrow(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  useEffect(() => {
    if (panelMotion === 'enter') return
    setPos((prev) => clampPos(loadStoredPos(wsId) ?? prev, effectiveWidth, effectiveHeight))
  }, [wsId, effectiveWidth, effectiveHeight, panelMotion])

  useEffect(() => {
    setCustomSize(loadStoredSize(wsId))
  }, [wsId])

  useEffect(() => {
    const reloadFromLocal = () => {
      const storedPos = loadStoredPos(wsId)
      if (storedPos) {
        setPos((prev) => clampPos(storedPos, effectiveWidth, effectiveHeight))
      }
      setCustomSize(loadStoredSize(wsId))
    }
    window.addEventListener(UI_STATE_LOCAL_APPLIED_EVENT, reloadFromLocal)
    return () => window.removeEventListener(UI_STATE_LOCAL_APPLIED_EVENT, reloadFromLocal)
  }, [wsId, effectiveWidth, effectiveHeight])

  useEffect(() => {
    if (narrow) return
    setCustomSize((prev) => {
      if (!prev) return prev
      const clamped = clampPanelSize(prev, pos.y, viewportW, viewportH)
      if (clamped.width === prev.width && clamped.height === prev.height) return prev
      try {
        writePanelSizeToLocal(wsId, clamped)
        patchFoldersUiState()
      } catch {
        /* ignore */
      }
      return clamped
    })
  }, [viewportW, viewportH, pos.y, narrow, wsId])

  useEffect(() => {
    const onResize = () => {
      setViewportH(window.innerHeight)
      setViewportW(window.innerWidth)
      setPos((prev) => clampPos(prev, effectiveWidth, effectiveHeight))
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [effectiveWidth, effectiveHeight])

  const persistPos = useCallback(
    (next: Point) => {
      const clamped = clampPos(next, effectiveWidth, effectiveHeight)
      setPos(clamped)
      try {
        writePanelPosToLocal(wsId, clamped)
        patchFoldersUiState()
      } catch {
        /* ignore */
      }
    },
    [wsId, effectiveWidth, effectiveHeight],
  )

  const persistSize = useCallback(
    (next: Size) => {
      const clamped = clampPanelSize(next, pos.y, viewportW, viewportH)
      setCustomSize(clamped)
      setPos((prev) => clampPos(prev, clamped.width, clamped.height))
      try {
        writePanelSizeToLocal(wsId, clamped)
        patchFoldersUiState()
      } catch {
        /* ignore */
      }
    },
    [wsId, pos.y, viewportW, viewportH],
  )

  const onPointerDown = (ev: React.PointerEvent<HTMLDivElement>) => {
    if (narrow || ev.button !== 0) return
    if ((ev.target as HTMLElement).closest('button')) return
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

  const onResizePointerDown = (ev: React.PointerEvent<HTMLButtonElement>) => {
    if (narrow || ev.button !== 0) return
    ev.stopPropagation()
    const panel = panelRef.current
    const originW = customSize?.width ?? panel?.offsetWidth ?? layoutSize.width
    const originH = customSize?.height ?? panel?.offsetHeight ?? layoutSize.height
    resizeRef.current = {
      pointerId: ev.pointerId,
      startX: ev.clientX,
      startY: ev.clientY,
      origin: { width: originW, height: originH },
    }
    setResizing(true)
    ev.currentTarget.setPointerCapture(ev.pointerId)
  }

  const onResizePointerMove = (ev: React.PointerEvent<HTMLButtonElement>) => {
    const resize = resizeRef.current
    if (!resize || resize.pointerId !== ev.pointerId) return
    persistSize({
      width: resize.origin.width + (ev.clientX - resize.startX),
      height: resize.origin.height + (ev.clientY - resize.startY),
    })
  }

  const onResizePointerUp = (ev: React.PointerEvent<HTMLButtonElement>) => {
    const resize = resizeRef.current
    if (!resize || resize.pointerId !== ev.pointerId) return
    resizeRef.current = null
    setResizing(false)
    if (ev.currentTarget.hasPointerCapture(ev.pointerId)) {
      ev.currentTarget.releasePointerCapture(ev.pointerId)
    }
    void flushUiStatePatch()
  }

  const minimizeAnimated = () => {
    if (prefersReducedMotion()) {
      minimizePanel()
      return
    }
    requestMinimizePanel(panelAnchor)
  }

  if (!visible) return null

  const motionClass =
    panelMotion === 'enter'
      ? ' folder-floating-panel--enter'
      : panelMotion === 'exit'
        ? ' folder-floating-panel--exit'
        : ''

  const motionDelta =
    panelAnchor && !narrow && panelMotion !== 'idle'
      ? panelMotionDelta(panelAnchor, pos.x, pos.y)
      : null

  const panelStyle = {
    ['--folder-panel-max-h' as string]: customSize
      ? `${customSize.height}px`
      : `${panelMaxH}px`,
    ...(customSize ? { ['--folder-panel-h' as string]: `${customSize.height}px` } : {}),
    ...(motionDelta
      ? {
          ['--folder-panel-motion-dx' as string]: `${motionDelta.dx}px`,
          ['--folder-panel-motion-dy' as string]: `${motionDelta.dy}px`,
        }
      : {}),
    ...(narrow
      ? {}
      : {
          left: pos.x,
          top: pos.y,
          width: effectiveWidth,
          ...(customSize ? { height: customSize.height } : {}),
        }),
  } as React.CSSProperties

  return (
    <div
      ref={panelRef}
        className={
          'folder-floating-panel' +
          (narrow ? ' folder-floating-panel--drawer' : '') +
          (dragging ? ' folder-floating-panel--dragging' : '') +
          (resizing ? ' folder-floating-panel--resizing' : '') +
          (customSize ? ' folder-floating-panel--resized' : '') +
          motionClass
        }
        style={panelStyle}
        role="dialog"
        aria-label={t('folders.panelTitle')}
      >
        <div className="folder-floating-panel__aura" aria-hidden />
        <div className="folder-floating-panel__frame" aria-hidden>
          <span className="folder-floating-panel__corner folder-floating-panel__corner--tl" />
          <span className="folder-floating-panel__corner folder-floating-panel__corner--tr" />
          <span className="folder-floating-panel__corner folder-floating-panel__corner--bl" />
          <span className="folder-floating-panel__corner folder-floating-panel__corner--br" />
        </div>

        <header
          className="folder-floating-panel__chrome"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        >
          <div className="folder-floating-panel__chrome-main">
            <h2 className="folder-floating-panel__title">{t('folders.panelTitle')}</h2>
            <Tooltip title={t('folders.panelMinimize')}>
              <button
                type="button"
                className="folder-floating-panel__icon-btn folder-floating-panel__icon-btn--minimize"
                aria-label={t('folders.panelMinimize')}
                onClick={minimizeAnimated}
              >
                <MinusOutlined />
              </button>
            </Tooltip>
          </div>
          <div
            className="folder-floating-panel__search"
            onPointerDown={(ev) => ev.stopPropagation()}
          >
            <Input.Search
              allowClear
              size="small"
              placeholder={t('folders.searchPlaceholder')}
              value={folderSearch}
              onChange={(e) => setFolderSearch(e.target.value)}
              aria-label={t('folders.searchPlaceholder')}
            />
          </div>
        </header>

        <div ref={bodyRef} className="folder-floating-panel__body">
          <FolderTreePanel
            showHeader={false}
            variant="hud"
            searchQuery={folderSearch}
            virtualRootExpanded={virtualRootExpanded}
            onVirtualRootExpandedChange={setVirtualRootExpanded}
          />
        </div>

        <footer className="folder-floating-panel__footer" aria-hidden>
          <span className="folder-floating-panel__footer-line" />
        </footer>

        {!narrow ? (
          <button
            type="button"
            className="folder-floating-panel__resize-handle"
            aria-label={t('folders.panelResize')}
            onPointerDown={onResizePointerDown}
            onPointerMove={onResizePointerMove}
            onPointerUp={onResizePointerUp}
            onPointerCancel={onResizePointerUp}
          />
        ) : null}
      </div>
  )
}
