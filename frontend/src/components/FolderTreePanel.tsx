import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { App, Button, Dropdown, Input, Modal, Spin } from 'antd'
import type { InputRef, MenuProps } from 'antd'
import {
  CaretDownOutlined,
  CaretRightOutlined,
  EditOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import { DeleteActionIcon } from '@/components/DeleteActionIcon'
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  pointerWithin,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import FolderTreeIcon, { type FolderTreeIconVariant } from './FolderTreeIcon'
import { MarqueeTooltip } from '@/components/FileListComponents'
import { useAuthStore } from '@/stores/authStore'
import { useFoldersStore } from '@/stores/foldersStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import { formatApiError } from '@/api/index'
import {
  buildFolderMovePayload,
  canManageFolders,
  computeFolderDropHint,
  dropTargetPreviewLabel,
  pointerYFromDragEvent,
  type FolderDropHint,
} from '@/lib/folderDragDrop'
import {
  ancestorFolderIds,
  expandIdsForFolderSearch,
  FOLDER_NAV_ID_MY_MATERIALS,
  folderDisplayLabel,
  folderMatchesSearch,
  folderNavDataId,
  folderNodeVisibleInSearch,
  folderPathLabel,
  folderSearchMatchIds,
  myMaterialsMatchesSearch,
  uncategorizedMatchesSearch,
  virtualRootDisplayLabel,
  virtualRootVisibleInSearch,
  type FolderSelection,
  type FolderTreeNode,
} from '@/lib/folderTree'
import {
  dispatchFolderNavToFileList,
  knowledgeFileListPathForFolderSelection,
} from '@/lib/wikiLinkEvents'
import './FolderSidebarSection.css'

const VIRTUAL_ROOT_DROP_ID = 'folder-drop-virtual-root'

function focusModalInput(ref: React.RefObject<InputRef | null>) {
  window.requestAnimationFrame(() => {
    const el = ref.current?.input
    if (!el) return
    el.focus()
    el.select()
  })
}

function FolderMarqueeLabel({ text }: { text: string }) {
  const viewportRef = useRef<HTMLSpanElement>(null)
  const stripRef = useRef<HTMLSpanElement>(null)
  const [marquee, setMarquee] = useState(false)

  useLayoutEffect(() => {
    const vp = viewportRef.current
    const strip = stripRef.current
    if (!vp || !strip) return
    const measure = () => {
      const overflow = strip.scrollWidth > vp.clientWidth + 1
      setMarquee(overflow)
      if (overflow) {
        const w = strip.scrollWidth
        const sec = Math.min(48, Math.max(8, w / 28))
        vp.style.setProperty('--folder-marquee-sec', `${sec}s`)
      }
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(vp)
    ro.observe(strip)
    return () => ro.disconnect()
  }, [text])

  return (
    <MarqueeTooltip active={marquee} title={text}>
      <span className="folder-tree-item-label">
        <span ref={viewportRef} className="folder-tree-label-viewport">
          <span
            className={
              marquee
                ? 'folder-tree-label-track folder-tree-label-track--marquee'
                : 'folder-tree-label-track'
            }
          >
            <span ref={stripRef} className="folder-tree-label-strip">
              {text}
            </span>
            {marquee ? (
              <span className="folder-tree-label-strip" aria-hidden>
                {text}
              </span>
            ) : null}
          </span>
        </span>
      </span>
    </MarqueeTooltip>
  )
}

function folderRowMenuItems(t: (key: string) => string): MenuProps['items'] {
  return [
    { key: 'newChild', label: t('folders.newChild'), icon: <PlusOutlined /> },
    { key: 'rename', label: t('folders.rename'), icon: <EditOutlined /> },
    { type: 'divider' },
    { key: 'delete', label: t('folders.delete'), icon: <DeleteActionIcon />, danger: true },
  ]
}

function FolderTreeRow({
  className,
  style,
  menuItems,
  onMenuClick,
  rowRef,
  children,
}: {
  className?: string
  style?: CSSProperties
  menuItems: MenuProps['items']
  onMenuClick: MenuProps['onClick']
  rowRef?: (node: HTMLDivElement | null) => void
  children: React.ReactNode
}) {
  return (
    <Dropdown
      menu={{ items: menuItems, onClick: onMenuClick }}
      trigger={['contextMenu']}
      overlayClassName="folder-context-menu"
    >
      <div ref={rowRef} className={className ?? 'folder-tree-row'} style={style}>
        {children}
      </div>
    </Dropdown>
  )
}

function FolderNavButton({
  active,
  label,
  variant,
  open,
  dataFolderNavId,
  searchMatch,
  onClick,
  buttonRef,
  dragListeners,
  dragAttributes,
  draggable,
}: {
  active: boolean
  label: string
  variant: FolderTreeIconVariant
  open?: boolean
  dataFolderNavId?: string
  searchMatch?: boolean
  onClick: () => void
  buttonRef?: (node: HTMLButtonElement | null) => void
  dragListeners?: ReturnType<typeof useDraggable>['listeners']
  dragAttributes?: ReturnType<typeof useDraggable>['attributes']
  draggable?: boolean
}) {
  return (
    <button
      ref={buttonRef}
      type="button"
      className={
        'folder-tree-nav-btn' +
        (active ? ' is-active' : '') +
        (searchMatch ? ' is-search-match' : '') +
        (draggable ? ' folder-tree-nav-btn--draggable' : '')
      }
      data-folder-nav-id={dataFolderNavId}
      aria-current={active ? 'true' : undefined}
      onClick={onClick}
      {...(dragListeners ?? {})}
      {...(dragAttributes ?? {})}
    >
      <FolderTreeIcon variant={variant} open={open} className="folder-tree-nav-icon" />
      <FolderMarqueeLabel text={label} />
    </button>
  )
}

function VirtualRootDropRow({
  dndEnabled,
  dropHint,
  className,
  style,
  children,
}: {
  dndEnabled: boolean
  dropHint: FolderDropHint | null
  className?: string
  style?: CSSProperties
  children: React.ReactNode
}) {
  const { setNodeRef } = useDroppable({
    id: VIRTUAL_ROOT_DROP_ID,
    disabled: !dndEnabled,
    data: { type: 'virtual-root' },
  })
  const activeInside =
    dropHint?.target.kind === 'virtual-root' &&
    dropHint.position === 'inside' &&
    !dropHint.invalid
  return (
    <div
      ref={setNodeRef}
      className={
        (className ?? '') +
        (activeInside ? ' folder-tree-row--drop-target' : '')
      }
      style={style}
    >
      {children}
    </div>
  )
}

function DraggableFolderNodeRow({
  node,
  depth,
  folders,
  dndEnabled,
  dropHint,
  isDraggingId,
  expanded,
  active,
  searchMatch,
  t,
  onToggleExpanded,
  onPick,
  onMenu,
  displayLabel,
}: {
  node: FolderTreeNode
  depth: number
  folders: ReturnType<typeof useFoldersStore.getState>['folders']
  dndEnabled: boolean
  dropHint: FolderDropHint | null
  isDraggingId: number | null
  expanded: boolean
  active: boolean
  searchMatch: boolean
  t: (key: string) => string
  onToggleExpanded: () => void
  onPick: () => void
  onMenu: MenuProps['onClick']
  displayLabel: string
}) {
  const { attributes, listeners, setNodeRef: setDragRef, isDragging } = useDraggable({
    id: node.id,
    disabled: !dndEnabled,
    data: { type: 'folder', folderId: node.id },
  })
  const { setNodeRef: setDropRef } = useDroppable({
    id: node.id,
    disabled: !dndEnabled,
    data: { type: 'folder', folderId: node.id },
  })
  const indentPx = 12 + depth * 16
  const hintForNode =
    dropHint?.target.kind === 'folder' && dropHint.target.folderId === node.id ? dropHint : null
  const rowClass =
    'folder-tree-row' +
    (isDragging || isDraggingId === node.id ? ' folder-tree-row--dragging' : '') +
    (hintForNode?.position === 'inside' && !hintForNode.invalid
      ? ' folder-tree-row--drop-target folder-tree-row--drop-inside'
      : '') +
    (hintForNode?.position === 'before' && !hintForNode.invalid
      ? ' folder-tree-row--drop-before'
      : '') +
    (hintForNode?.position === 'after' && !hintForNode.invalid
      ? ' folder-tree-row--drop-after'
      : '')

  return (
    <FolderTreeRow
      className={rowClass}
      style={{ paddingLeft: indentPx }}
      menuItems={folderRowMenuItems(t)}
      onMenuClick={onMenu}
      rowRef={setDropRef}
    >
      <button
        type="button"
        className="folder-tree-expand"
        aria-expanded={expanded}
        aria-label={expanded ? t('folders.collapse') : t('folders.expand')}
        onClick={onToggleExpanded}
      >
        {node.children.length > 0 ? (
          expanded ? <CaretDownOutlined /> : <CaretRightOutlined />
        ) : null}
      </button>
      <div className="folder-tree-item">
        <FolderNavButton
          active={active}
          variant="child"
          open={expanded && node.children.length > 0}
          label={displayLabel}
          dataFolderNavId={String(node.id)}
          searchMatch={searchMatch}
          onClick={onPick}
          buttonRef={setDragRef}
          dragListeners={dndEnabled ? listeners : undefined}
          dragAttributes={dndEnabled ? attributes : undefined}
          draggable={dndEnabled}
        />
      </div>
    </FolderTreeRow>
  )
}

type FolderTreePanelProps = {
  showHeader?: boolean
  variant?: 'default' | 'hud'
  treeRef?: React.RefObject<HTMLDivElement | null>
  searchQuery?: string
  virtualRootExpanded?: boolean
  onVirtualRootExpandedChange?: (expanded: boolean) => void
}

const VIRTUAL_ROOT_CHILD_DEPTH = 1
const virtualRootChildIndentPx = 12 + VIRTUAL_ROOT_CHILD_DEPTH * 16

export default function FolderTreePanel({
  showHeader = true,
  variant = 'default',
  treeRef: externalTreeRef,
  searchQuery = '',
  virtualRootExpanded = true,
  onVirtualRootExpandedChange,
}: FolderTreePanelProps) {
  const { t } = useTranslation()
  const { message: msg } = App.useApp()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const folders = useFoldersStore((s) => s.folders)
  const tree = useFoldersStore((s) => s.tree)
  const selected = useFoldersStore((s) => s.selected)
  const expandedFolderIds = useFoldersStore((s) => s.expandedFolderIds)
  const loading = useFoldersStore((s) => s.loading)
  const folderMovePending = useFoldersStore((s) => s.folderMovePending)
  const workspaces = useWorkspaceStore((s) => s.workspaces)
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const isAdmin = useAuthStore((s) => s.user?.is_admin)
  const folderFileCounts = useFoldersStore((s) => s.folderFileCounts)
  const uncategorizedFileCount = useFoldersStore((s) => s.uncategorizedFileCount)
  const zeroAclMember = useFoldersStore((s) => s.zeroAclMember)
  const fetchFolders = useFoldersStore((s) => s.fetchFolders)
  const setSelected = useFoldersStore((s) => s.setSelected)
  const toggleExpanded = useFoldersStore((s) => s.toggleExpanded)
  const createFolder = useFoldersStore((s) => s.createFolder)
  const renameFolder = useFoldersStore((s) => s.renameFolder)
  const moveFolder = useFoldersStore((s) => s.moveFolder)
  const removeFolder = useFoldersStore((s) => s.removeFolder)
  const mergeExpandedFolderIds = useFoldersStore((s) => s.mergeExpandedFolderIds)

  const [createOpen, setCreateOpen] = useState(false)
  const [createParentId, setCreateParentId] = useState<number | null>(null)
  const [newName, setNewName] = useState('')
  const [renameTarget, setRenameTarget] = useState<{ id: number; name: string } | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<{ id: number; name: string } | null>(null)
  const [activeDragId, setActiveDragId] = useState<number | null>(null)
  const [dropHint, setDropHint] = useState<FolderDropHint | null>(null)
  const internalTreeRef = useRef<HTMLDivElement>(null)
  const createInputRef = useRef<InputRef>(null)
  const renameInputRef = useRef<InputRef>(null)
  const treeRef = externalTreeRef ?? internalTreeRef

  const activeWs = workspaces.find((w) => w.id === activeWorkspaceId)
  const canManage = !zeroAclMember && canManageFolders(isAdmin, activeWs?.my_role)
  const trimmedSearch = searchQuery.trim()
  const dndEnabled = canManage && !trimmedSearch && !folderMovePending

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  )

  const clearDragState = useCallback(() => {
    setActiveDragId(null)
    setDropHint(null)
  }, [])

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const id = Number(event.active.id)
    if (Number.isFinite(id)) setActiveDragId(id)
  }, [])

  const resolveHintFromEvent = useCallback(
    (event: DragOverEvent | DragEndEvent): FolderDropHint | null => {
      const draggedId = Number(event.active.id)
      if (!Number.isFinite(draggedId) || !event.over) return null
      const pointerY = pointerYFromDragEvent(event)
      if (pointerY == null) return null
      return computeFolderDropHint(
        folders,
        draggedId,
        event.over.id,
        pointerY,
        event.over.rect,
        VIRTUAL_ROOT_DROP_ID,
      )
    },
    [folders],
  )

  const handleDragOver = useCallback(
    (event: DragOverEvent) => {
      if (!dndEnabled) return
      if (!event.over) {
        setDropHint(null)
        return
      }
      setDropHint(resolveHintFromEvent(event))
    },
    [dndEnabled, resolveHintFromEvent],
  )

  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      const draggedId = Number(event.active.id)
      const hint = resolveHintFromEvent(event)
      clearDragState()
      if (!dndEnabled || !Number.isFinite(draggedId) || !event.over || !hint || hint.invalid) return
      const payload = buildFolderMovePayload(folders, draggedId, hint.target, hint.position)
      if (Object.keys(payload).length === 0) return
      try {
        await moveFolder(draggedId, payload)
        msg.success(t('folders.moveSuccess'))
        const parentId =
          payload.parent_id !== undefined
            ? payload.parent_id
            : folders.find((f) => f.id === draggedId)?.parent_id ?? null
        if (parentId != null) {
          mergeExpandedFolderIds([...ancestorFolderIds(folders, parentId), parentId])
        } else if (payload.parent_id === null) {
          onVirtualRootExpandedChange?.(true)
        }
        if (hint.target.kind === 'folder' && hint.position === 'inside') {
          mergeExpandedFolderIds([hint.target.folderId])
        }
      } catch (e) {
        msg.error(formatApiError(e))
      }
    },
    [
      clearDragState,
      dndEnabled,
      folders,
      mergeExpandedFolderIds,
      moveFolder,
      msg,
      onVirtualRootExpandedChange,
      resolveHintFromEvent,
      t,
    ],
  )

  useLayoutEffect(() => {
    if (loading) return
    const navId = folderNavDataId(selected)
    if (!navId) return
    const run = () => {
      const el = treeRef.current?.querySelector(`[data-folder-nav-id="${navId}"]`)
      el?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' })
    }
    window.requestAnimationFrame(() => window.requestAnimationFrame(run))
  }, [loading, selected, tree, expandedFolderIds, treeRef, virtualRootExpanded])

  useEffect(() => {
    if (activeWorkspaceId == null) return
    void fetchFolders()
  }, [fetchFolders, activeWorkspaceId])

  const virtualRootLabel = useMemo(
    () => virtualRootDisplayLabel(activeWs, t),
    [activeWs, t],
  )
  const uncategorizedLabel = t('folders.uncategorized')
  const searchMatchIds = useMemo(
    () => (trimmedSearch ? folderSearchMatchIds(folders, trimmedSearch) : []),
    [folders, trimmedSearch],
  )
  const showVirtualRoot = useMemo(
    () =>
      virtualRootVisibleInSearch(
        trimmedSearch,
        virtualRootLabel,
        uncategorizedLabel,
        tree,
        folders,
      ),
    [trimmedSearch, virtualRootLabel, uncategorizedLabel, tree, folders],
  )
  const searchHasMatch = !trimmedSearch || showVirtualRoot

  useEffect(() => {
    if (!trimmedSearch || loading) return
    if (
      searchMatchIds.length > 0 ||
      uncategorizedMatchesSearch(trimmedSearch, uncategorizedLabel)
    ) {
      onVirtualRootExpandedChange?.(true)
    }
    if (searchMatchIds.length === 0) return
    mergeExpandedFolderIds(expandIdsForFolderSearch(folders, searchMatchIds))
    const firstId = String(searchMatchIds[0])
    const run = () => {
      treeRef.current
        ?.querySelector(`[data-folder-nav-id="${firstId}"]`)
        ?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' })
    }
    window.requestAnimationFrame(() => window.requestAnimationFrame(run))
  }, [
    trimmedSearch,
    searchMatchIds,
    loading,
    folders,
    mergeExpandedFolderIds,
    treeRef,
    uncategorizedLabel,
    onVirtualRootExpandedChange,
  ])

  const pick = (sel: FolderSelection) => {
    setSelected(sel)
    const targetPath = knowledgeFileListPathForFolderSelection(pathname)
    if (targetPath) {
      navigate(targetPath)
      return
    }
    dispatchFolderNavToFileList()
  }

  const openCreate = (parentId: number | null) => {
    setCreateParentId(parentId)
    setNewName('')
    setCreateOpen(true)
  }

  const submitCreate = async () => {
    const name = newName.trim()
    if (!name) return
    try {
      await createFolder(name, createParentId)
      msg.success(t('folders.created'))
      setCreateOpen(false)
    } catch (e) {
      msg.error(formatApiError(e))
    }
  }

  const submitRename = async () => {
    if (!renameTarget) return
    const name = renameTarget.name.trim()
    if (!name) return
    try {
      await renameFolder(renameTarget.id, name)
      msg.success(t('folders.renamed'))
      setRenameTarget(null)
    } catch (e) {
      msg.error(formatApiError(e))
    }
  }

  const submitDelete = async () => {
    if (!deleteTarget) return
    try {
      await removeFolder(deleteTarget.id)
      msg.success(t('folders.deleted'))
      setDeleteTarget(null)
    } catch (e) {
      msg.error(formatApiError(e))
    }
  }

  const renderNode = (node: FolderTreeNode, depth: number) => {
    if (!folderNodeVisibleInSearch(node, folders, trimmedSearch)) return null
    const expanded = expandedFolderIds.includes(node.id)
    const active = selected === node.id
    const searchMatch = trimmedSearch ? folderMatchesSearch(folders, node.id, trimmedSearch) : false
    return (
      <div key={node.id}>
        <DraggableFolderNodeRow
          node={node}
          depth={depth}
          folders={folders}
          dndEnabled={dndEnabled}
          dropHint={dropHint}
          isDraggingId={activeDragId}
          expanded={expanded}
          active={active}
          searchMatch={searchMatch}
          displayLabel={folderDisplayLabel(node.name, folderFileCounts[node.id])}
          t={t}
          onToggleExpanded={() => toggleExpanded(node.id)}
          onPick={() => pick(node.id)}
          onMenu={({ key, domEvent }) => {
            domEvent.stopPropagation()
            if (key === 'newChild') openCreate(node.id)
            else if (key === 'rename') setRenameTarget({ id: node.id, name: node.name })
            else if (key === 'delete') setDeleteTarget({ id: node.id, name: node.name })
          }}
        />
        {expanded && node.children.length > 0
          ? node.children.map((child) => renderNode(child, depth + 1))
          : null}
      </div>
    )
  }

  const isHud = variant === 'hud'
  const virtualRootSearchMatch = Boolean(
    trimmedSearch && myMaterialsMatchesSearch(trimmedSearch, virtualRootLabel),
  )
  const showUncategorizedRow =
    virtualRootExpanded &&
    uncategorizedMatchesSearch(trimmedSearch, uncategorizedLabel)

  const dragOverlayLabel =
    activeDragId != null
      ? folderPathLabel(folders, activeDragId) ||
        folders.find((f) => f.id === activeDragId)?.name ||
        ''
      : ''

  const dropPreviewText =
    dropHint && !dropHint.invalid && activeDragId != null
      ? dropTargetPreviewLabel(folders, dropHint, {
          myMaterials: virtualRootLabel,
          into: t('folders.dropPreviewInto'),
          before: t('folders.dropPreviewBefore'),
          after: t('folders.dropPreviewAfter'),
        })
      : ''

  const treeBody = (
    <div
      className={
        'folder-tree' +
        (isHud ? ' folder-tree--hud' : '') +
        (dropHint?.invalid ? ' folder-tree--drag-invalid' : '')
      }
      ref={treeRef}
    >
      {dropPreviewText ? (
        <div className="folder-tree-drop-preview" aria-live="polite">
          {dropPreviewText}
        </div>
      ) : null}
      {showVirtualRoot ? (
        <>
          <VirtualRootDropRow
            dndEnabled={dndEnabled}
            dropHint={dropHint}
            className="folder-tree-row folder-tree-row--virtual-root"
            style={{ paddingLeft: 12 }}
          >
            <button
              type="button"
              className="folder-tree-expand"
              aria-expanded={virtualRootExpanded}
              aria-label={virtualRootExpanded ? t('folders.collapse') : t('folders.expand')}
              onClick={() => onVirtualRootExpandedChange?.(!virtualRootExpanded)}
            >
              {virtualRootExpanded ? <CaretDownOutlined /> : <CaretRightOutlined />}
            </button>
            <div className="folder-tree-item">
              <FolderNavButton
                active={selected === 'all'}
                variant="root"
                open={virtualRootExpanded}
                label={virtualRootLabel}
                dataFolderNavId={FOLDER_NAV_ID_MY_MATERIALS}
                searchMatch={virtualRootSearchMatch}
                onClick={() => pick('all')}
              />
            </div>
          </VirtualRootDropRow>

          {showUncategorizedRow ? (
            <div
              className="folder-tree-row folder-tree-row--uncategorized"
              style={{ paddingLeft: virtualRootChildIndentPx }}
            >
              <span className="folder-tree-expand folder-tree-expand--placeholder" aria-hidden />
              <div className="folder-tree-item">
                <FolderNavButton
                  active={selected === 'uncategorized'}
                  variant="uncategorized"
                  label={folderDisplayLabel(uncategorizedLabel, uncategorizedFileCount)}
                  dataFolderNavId="uncategorized"
                  searchMatch={Boolean(
                    trimmedSearch &&
                      uncategorizedMatchesSearch(trimmedSearch, uncategorizedLabel),
                  )}
                  onClick={() => pick('uncategorized')}
                />
              </div>
              {isHud && !showHeader ? (
                <button
                  type="button"
                  className="folder-tree-hud-new-root-btn"
                  onClick={() => openCreate(null)}
                >
                  <PlusOutlined />
                  {t('folders.newRoot')}
                </button>
              ) : null}
            </div>
          ) : null}

          {virtualRootExpanded
            ? tree.map((root) => renderNode(root, VIRTUAL_ROOT_CHILD_DEPTH))
            : null}
        </>
      ) : null}

      {!loading && trimmedSearch && !searchHasMatch ? (
        <div className={'folder-sidebar-empty' + (isHud ? ' folder-sidebar-empty--hud' : '')}>
          {t('folders.searchNoMatch')}
        </div>
      ) : null}

      {!loading && !trimmedSearch && tree.length === 0 && virtualRootExpanded ? (
        <div
          className={'folder-sidebar-empty' + (isHud ? ' folder-sidebar-empty--hud' : '')}
          style={{ paddingLeft: virtualRootChildIndentPx }}
        >
          {zeroAclMember ? t('folders.zeroAclHint') : t('folders.emptyHint')}
        </div>
      ) : null}
    </div>
  )

  return (
    <>
      {showHeader ? (
        <div className="folder-tree-panel-header">
          <span className="folder-tree-panel-title">{t('folders.title')}</span>
          <Button
            type="text"
            size="small"
            icon={<PlusOutlined />}
            title={t('folders.newRoot')}
            onClick={() => openCreate(null)}
          />
        </div>
      ) : null}
      {loading && folders.length === 0 ? (
        <Spin size="small" style={{ margin: isHud ? '8px auto' : '8px 12px', display: 'block' }} />
      ) : null}

      {dndEnabled ? (
        <DndContext
          sensors={sensors}
          collisionDetection={pointerWithin}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragEnd={(e) => void handleDragEnd(e)}
          onDragCancel={clearDragState}
        >
          {treeBody}
          <DragOverlay dropAnimation={null}>
            {activeDragId != null ? (
              <div className="folder-tree-item" style={{ minWidth: 180 }}>
                <button type="button" className="folder-tree-nav-btn is-active folder-tree-nav-btn--draggable">
                  <FolderTreeIcon variant="child" className="folder-tree-nav-icon" />
                  <span className="folder-tree-item-label">{dragOverlayLabel}</span>
                </button>
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      ) : (
        treeBody
      )}

      <Modal
        title={createParentId == null ? t('folders.newRoot') : t('folders.newChild')}
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => void submitCreate()}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        destroyOnHidden
        afterOpenChange={(open) => {
          if (open) focusModalInput(createInputRef)
        }}
      >
        <Input
          ref={createInputRef}
          autoFocus
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder={t('folders.namePlaceholder')}
          maxLength={100}
          onPressEnter={() => void submitCreate()}
        />
      </Modal>

      <Modal
        title={t('folders.rename')}
        open={renameTarget != null}
        onCancel={() => setRenameTarget(null)}
        onOk={() => void submitRename()}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        destroyOnHidden
        afterOpenChange={(open) => {
          if (open) focusModalInput(renameInputRef)
        }}
      >
        <Input
          ref={renameInputRef}
          autoFocus
          value={renameTarget?.name ?? ''}
          onChange={(e) =>
            setRenameTarget((prev) => (prev ? { ...prev, name: e.target.value } : prev))
          }
          maxLength={100}
          onPressEnter={() => void submitRename()}
        />
      </Modal>

      <Modal
        title={t('folders.deleteTitle')}
        open={deleteTarget != null}
        onCancel={() => setDeleteTarget(null)}
        onOk={() => void submitDelete()}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        okButtonProps={{ danger: true }}
        destroyOnHidden
      >
        {deleteTarget ? t('folders.deleteContent', { name: deleteTarget.name }) : null}
      </Modal>
    </>
  )
}
