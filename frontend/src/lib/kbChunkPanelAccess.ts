import { isMultimodalReadOnlyKind } from '@/lib/kbChunkMultimodalDisplay'

export type KbChunkPanelAccess = {
  canEdit: boolean
  canReindex: boolean
}

/** FilePreview → KbChunkPanel：owner/admin 可 PATCH；仅 owner 可 reindex。 */
export function resolveKbChunkPanelAccess(input: {
  fileOwnerId: number | null | undefined
  currentUserId: number | null | undefined
  isAdmin: boolean | null | undefined
}): KbChunkPanelAccess {
  const { fileOwnerId, currentUserId, isAdmin } = input
  if (fileOwnerId == null || currentUserId == null) {
    return { canEdit: false, canReindex: false }
  }
  const isOwner = fileOwnerId === currentUserId
  return {
    canEdit: isOwner || isAdmin === true,
    canReindex: isOwner,
  }
}

export function shouldShowReindexActions(canReindex: boolean): boolean {
  return canReindex
}

export function kbChunkDrawerFieldState(
  canEdit: boolean,
  contentKind: string | null | undefined,
): { textEditable: boolean; boostEditable: boolean } {
  return {
    textEditable: canEdit && !isMultimodalReadOnlyKind(contentKind),
    boostEditable: canEdit,
  }
}
