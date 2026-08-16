import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { DownOutlined, UpOutlined } from '@ant-design/icons'
import { patchSidebarUiState } from '@/lib/uiStateSync'
import './SidebarNav.css'

type GroupController = (open: boolean) => void

type SidebarNavAccordionContextValue = {
  registerGroup: (id: string, controller: GroupController) => () => void
  onItemClick: (groupId?: string) => void
}

const SidebarNavAccordionContext = createContext<SidebarNavAccordionContextValue | null>(null)
const SidebarNavGroupContext = createContext<string | undefined>(undefined)

export function SidebarNavAccordionProvider({ children }: { children: ReactNode }) {
  const groupsRef = useRef(new Map<string, GroupController>())

  const registerGroup = useCallback((id: string, controller: GroupController) => {
    groupsRef.current.set(id, controller)
    return () => {
      const current = groupsRef.current.get(id)
      if (current === controller) groupsRef.current.delete(id)
    }
  }, [])

  const onItemClick = useCallback((groupId?: string) => {
    if (groupId) groupsRef.current.get(groupId)?.(true)
  }, [])

  return (
    <SidebarNavAccordionContext.Provider value={{ registerGroup, onItemClick }}>
      {children}
    </SidebarNavAccordionContext.Provider>
  )
}

type SidebarNavGroupProps = {
  id: string
  title: string
  defaultOpen?: boolean
  actions?: ReactNode
  children: ReactNode
}

export function SidebarNavGroup({ id, title, defaultOpen = true, actions, children }: SidebarNavGroupProps) {
  const accordion = useContext(SidebarNavAccordionContext)
  const storageKey = `filex_sidebar_group_${id}`
  const [open, setOpen] = useState(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      if (raw != null) return raw === '1'
    } catch {
      /* ignore */
    }
    return defaultOpen
  })

  useEffect(() => {
    if (!accordion) return undefined
    return accordion.registerGroup(id, setOpen)
  }, [accordion, id])

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, open ? '1' : '0')
    } catch {
      /* ignore */
    }
    patchSidebarUiState()
  }, [open, storageKey])

  return (
    <SidebarNavGroupContext.Provider value={id}>
      <section className={`sidebar-nav-group${open ? ' is-open' : ' is-collapsed'}`}>
        <button
          type="button"
          className="sidebar-nav-group-header"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <span className="sidebar-nav-group-title">{title}</span>
          {actions ? (
            <span className="sidebar-nav-group-actions" onClick={(e) => e.stopPropagation()}>
              {actions}
            </span>
          ) : null}
          <span className="sidebar-nav-group-chevron" aria-hidden>
            {open ? <UpOutlined /> : <DownOutlined />}
          </span>
        </button>
        {open ? <div className="sidebar-nav-group-body">{children}</div> : null}
      </section>
    </SidebarNavGroupContext.Provider>
  )
}

type SidebarNavItemProps = {
  active?: boolean
  onClick: () => void
  icon?: ReactNode
  children: ReactNode
  className?: string
  'data-folder-nav-id'?: string
}

export function SidebarNavItem({
  active,
  onClick,
  icon,
  children,
  className,
  'data-folder-nav-id': dataFolderNavId,
}: SidebarNavItemProps) {
  const accordion = useContext(SidebarNavAccordionContext)
  const groupId = useContext(SidebarNavGroupContext)

  return (
    <button
      type="button"
      className={`sidebar-nav-item${active ? ' is-active' : ''}${className ? ` ${className}` : ''}`}
      aria-current={active ? 'page' : undefined}
      onClick={() => {
        if (groupId) accordion?.onItemClick(groupId)
        onClick()
      }}
      data-folder-nav-id={dataFolderNavId}
    >
      {icon ? <span className="sidebar-nav-item-icon">{icon}</span> : null}
      <span className="sidebar-nav-item-label">{children}</span>
    </button>
  )
}

export function useSidebarNavAccordion() {
  return useContext(SidebarNavAccordionContext)
}

export function SidebarNavTree({ children }: { children: ReactNode }) {
  return <div className="sidebar-nav-tree">{children}</div>
}
