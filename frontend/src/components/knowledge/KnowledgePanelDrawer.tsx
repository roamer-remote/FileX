import { useCallback, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Button, Drawer } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import type { KnowledgePageTabKey } from '@/contexts/KnowledgePageTabsContext'
import { KnowledgePanelToolbarSlotContext } from '@/contexts/KnowledgePanelToolbarSlotContext'
import { KNOWLEDGE_PANEL_CONFIG, type KnowledgePanelLayout } from '@/lib/knowledgePanelConfig'
import type { KbPanelTransitionId } from '@/lib/knowledgePanelTransition'
import { useMatchMedia } from '@/hooks/useMatchMedia'
import './KnowledgePanelDrawer.css'
import './KnowledgeLobbyToolbar.css'
import './knowledgePanelTransition.css'
import '@/styles/knowledge-panel-shell.css'
import '@/styles/knowledge-workspace-layout.css'

type Props = {
  open: boolean
  panelKey: KnowledgePageTabKey | null
  transitionId?: KbPanelTransitionId | null
  onClose: () => void
  onRefresh: () => void
  /** 顶栏标题右侧内联区（如资料页文件名搜索） */
  headerAfterTitle?: ReactNode
  /** 顶栏标题与刷新按钮之间的操作区（如主题页新建/体检） */
  headerActions?: ReactNode
  /** 替换顶栏标题区（如智能检索工具栏占满标题槽） */
  headerToolbar?: ReactNode
  /** 顶栏工具栏 Portal 挂载槽（子组件 createPortal 填入，避免输入态丢失） */
  headerToolbarSlot?: boolean
  /** 顶栏最右侧自定义区（如资料库总览「刷新报告」） */
  panelExtra?: ReactNode
  children: ReactNode
}

function getKnowledgeDrawerContainer(): HTMLElement | false {
  if (typeof document === 'undefined') return false
  const el = document.querySelector('.app-main')
  return el instanceof HTMLElement ? el : false
}

function drawerTitleNode(
  config: KnowledgePanelLayout,
  t: (key: string) => string,
  headerAfterTitle?: ReactNode,
  headerActions?: ReactNode,
  headerToolbar?: ReactNode,
  headerToolbarSlot?: boolean,
  toolbarSlotRef?: (node: HTMLDivElement | null) => void,
) {
  if (headerToolbarSlot) {
    return (
      <>
        <span className="knowledge-panel-drawer-head__sr-title">{t(config.titleKey)}</span>
        <div
          ref={toolbarSlotRef}
          className="knowledge-panel-drawer-head__toolbar-inline knowledge-panel-drawer-head__toolbar-slot"
        />
      </>
    )
  }

  if (headerToolbar) {
    return (
      <>
        <span className="knowledge-panel-drawer-head__sr-title">{t(config.titleKey)}</span>
        <div className="knowledge-panel-drawer-head__toolbar-inline">{headerToolbar}</div>
      </>
    )
  }

  const titleLabel = config.subtitleKey
    ? (
        <div className="panel-title-row knowledge-panel-drawer__title-row">
          <span className="knowledge-panel-drawer-head__title">{t(config.titleKey)}</span>
          <span className="panel-subtitle">{t(config.subtitleKey)}</span>
        </div>
      )
    : (
        <span className="knowledge-panel-drawer-head__title">{t(config.titleKey)}</span>
      )

  if (headerAfterTitle || headerActions) {
    return (
      <div className="knowledge-panel-drawer-head">
        {titleLabel}
        {headerAfterTitle ? (
          <div className="knowledge-panel-drawer-head__after-title">{headerAfterTitle}</div>
        ) : null}
        {headerActions ? (
          <div className="knowledge-panel-drawer-head__actions">{headerActions}</div>
        ) : null}
      </div>
    )
  }

  return titleLabel
}

export default function KnowledgePanelDrawer({
  open,
  panelKey,
  transitionId,
  onClose,
  onRefresh,
  headerAfterTitle,
  headerActions,
  headerToolbar,
  headerToolbarSlot,
  panelExtra,
  children,
}: Props) {
  const { t } = useTranslation()
  const isMobile = useMatchMedia('(max-width: 768px)')
  const config = panelKey ? KNOWLEDGE_PANEL_CONFIG[panelKey] : null
  const fxClass = transitionId ? ` knowledge-panel-drawer--fx-${transitionId}` : ''
  const [toolbarSlotEl, setToolbarSlotEl] = useState<HTMLElement | null>(null)
  const toolbarSlotRef = useCallback((node: HTMLDivElement | null) => {
    setToolbarSlotEl(node)
  }, [])

  const afterOpenChange = useCallback(
    (visible: boolean) => {
      if (!visible) return
      // 等 Drawer 打开并完成自定义进入动效后再刷新图表尺寸
      window.setTimeout(() => {
        window.dispatchEvent(new CustomEvent('kb-panel-resize'))
        onRefresh()
      }, 480)
    },
    [onRefresh],
  )

  return (
    <KnowledgePanelToolbarSlotContext.Provider value={toolbarSlotEl}>
      <Drawer
        open={open}
        onClose={onClose}
        destroyOnClose
        getContainer={isMobile ? false : getKnowledgeDrawerContainer()}
        rootClassName={
          'knowledge-panel-drawer' +
          fxClass +
          (config?.fullscreen ? ' knowledge-panel-drawer--fullscreen' : '') +
          (panelKey === 'eval' ? ' knowledge-panel-drawer--eval' : '')
        }
        placement={isMobile ? 'bottom' : 'right'}
        width={isMobile ? '100%' : config?.fullscreen ? '100%' : config?.width}
        height={isMobile ? 'min(92dvh, 900px)' : undefined}
        title={
          config
            ? drawerTitleNode(
                config,
                t,
                headerAfterTitle,
                headerActions,
                headerToolbar,
                headerToolbarSlot,
                toolbarSlotRef,
              )
            : undefined
        }
        extra={
          panelExtra !== undefined
            ? panelExtra
            : panelKey && panelKey !== 'eval'
              ? (
                  <Button
                    type="text"
                    size="small"
                    icon={<ReloadOutlined aria-hidden />}
                    aria-label={t('knowledge.refresh')}
                    onClick={onRefresh}
                  />
                )
              : null
        }
        afterOpenChange={afterOpenChange}
      >
        <div
          key={`${panelKey ?? 'panel'}-${transitionId ?? 'none'}`}
          className="knowledge-panel-shell"
        >
          {children}
        </div>
      </Drawer>
    </KnowledgePanelToolbarSlotContext.Provider>
  )
}
