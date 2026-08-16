import { getEventCoordinates } from '@dnd-kit/utilities'
import type { FolderItem, FolderMovePayload } from '@/api/folders'
import { folderPathLabel } from '@/lib/folderTree'

export type DropPosition = 'before' | 'after' | 'inside'

export type FolderDropTarget =
  | { kind: 'folder'; folderId: number }
  | { kind: 'virtual-root' }

export type FolderDropHint = {
  target: FolderDropTarget
  position: DropPosition
  invalid: boolean
}

/** 行顶/底仅 EDGE_PX 触发 before/after，中间区域均为 inside（改父级） */
export const DROP_EDGE_PX = 8

export function canManageFolders(isAdmin: boolean | undefined, myRole: string | undefined): boolean {
  if (isAdmin) return true
  return myRole === 'curator' || myRole === 'admin'
}

export function sortedSiblings(
  folders: FolderItem[],
  parentId: number | null,
  excludeId?: number,
): FolderItem[] {
  return folders
    .filter((f) => (f.parent_id ?? null) === parentId && f.id !== excludeId)
    .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
}

export function isFolderDescendant(
  folders: FolderItem[],
  ancestorId: number,
  candidateId: number,
): boolean {
  if (ancestorId === candidateId) return true
  let current = folders.find((f) => f.id === candidateId)
  const seen = new Set<number>()
  while (current?.parent_id != null) {
    if (current.parent_id === ancestorId) return true
    if (seen.has(current.parent_id)) break
    seen.add(current.parent_id)
    current = folders.find((f) => f.id === current!.parent_id)
  }
  return false
}

export function isInvalidFolderDrop(
  folders: FolderItem[],
  draggedId: number,
  target: FolderDropTarget,
  position: DropPosition,
): boolean {
  if (target.kind === 'virtual-root') {
    return position !== 'inside'
  }
  const targetId = target.folderId
  if (targetId === draggedId) return true
  if (position === 'inside' && isFolderDescendant(folders, draggedId, targetId)) {
    return true
  }
  return false
}

export function resolveDropPosition(
  pointerY: number,
  rectTop: number,
  rectHeight: number,
  edgePx: number = DROP_EDGE_PX,
): DropPosition {
  const fromTop = pointerY - rectTop
  const height = Math.max(rectHeight, 1)
  if (fromTop <= edgePx) return 'before'
  if (fromTop >= height - edgePx) return 'after'
  return 'inside'
}

export function pointerYFromDragEvent(event: {
  activatorEvent: Event | null
  delta: { x: number; y: number }
}): number | null {
  const { activatorEvent, delta } = event
  if (!activatorEvent) return null
  try {
    const coords = getEventCoordinates(activatorEvent as MouseEvent & TouchEvent)
    if (!coords) return null
    return coords.y + delta.y
  } catch {
    return null
  }
}

export function computeFolderDropHint(
  folders: FolderItem[],
  draggedId: number,
  overId: string | number,
  pointerY: number,
  overRect: { top: number; height: number },
  virtualRootDropId: string,
): FolderDropHint | null {
  if (!Number.isFinite(draggedId)) return null
  let target: FolderDropTarget
  let position: DropPosition
  if (overId === virtualRootDropId) {
    target = { kind: 'virtual-root' }
    position = 'inside'
  } else {
    const folderId = Number(overId)
    if (!Number.isFinite(folderId)) return null
    position = resolveDropPosition(pointerY, overRect.top, overRect.height)
    target = { kind: 'folder', folderId }
  }
  const invalid = isInvalidFolderDrop(folders, draggedId, target, position)
  return { target, position, invalid }
}

export function dropTargetPreviewLabel(
  folders: FolderItem[],
  hint: FolderDropHint,
  labels: { myMaterials: string; before: string; after: string; into: string },
): string {
  const { target, position } = hint
  if (target.kind === 'virtual-root') {
    return labels.into.replace('{{path}}', labels.myMaterials)
  }
  const folder = folders.find((f) => f.id === target.folderId)
  if (!folder) return ''
  if (position === 'inside') {
    const path = folderPathLabel(folders, folder.id)
    return labels.into.replace('{{path}}', path || folder.name)
  }
  if (position === 'before') {
    return labels.before.replace('{{name}}', folder.name)
  }
  return labels.after.replace('{{name}}', folder.name)
}

export function buildFolderMovePayload(
  folders: FolderItem[],
  draggedId: number,
  target: FolderDropTarget,
  position: DropPosition,
): FolderMovePayload {
  const dragged = folders.find((f) => f.id === draggedId)
  if (!dragged) return {}

  if (target.kind === 'virtual-root') {
    const siblings = sortedSiblings(folders, null, draggedId)
    return { parent_id: null, sort_order: siblings.length }
  }

  const targetFolder = folders.find((f) => f.id === target.folderId)
  if (!targetFolder) return {}

  if (position === 'inside') {
    const children = sortedSiblings(folders, target.folderId, draggedId)
    return { parent_id: target.folderId, sort_order: children.length }
  }

  const parentId = targetFolder.parent_id ?? null
  const siblings = sortedSiblings(folders, parentId, draggedId)
  const targetIdx = siblings.findIndex((s) => s.id === target.folderId)
  const insertAt = position === 'before' ? targetIdx : targetIdx + 1
  const payload: FolderMovePayload = { sort_order: insertAt }
  if ((dragged.parent_id ?? null) !== parentId) {
    payload.parent_id = parentId
  }
  return payload
}
