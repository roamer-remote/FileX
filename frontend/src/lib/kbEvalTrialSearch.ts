import type { NavigateFunction } from 'react-router-dom'
import type { MessageInstance } from 'antd/es/message/interface'
import type { TFunction } from 'i18next'
import { copyToClipboard } from '@/utils/copyToClipboard'
import { getActiveWorkspaceId } from '@/stores/workspaceStore'
import { buildKbEvalLobbyPath, deriveChunkTrialSearchQuery } from '@/lib/kbEvalLobbyLink'

export async function openKbEvalTrialSearch(
  navigate: NavigateFunction,
  deps: { message: MessageInstance; t: TFunction },
  input: { boostKeywords?: string | null; text?: string; workspaceId?: number | null },
): Promise<void> {
  const query = deriveChunkTrialSearchQuery({
    boostKeywords: input.boostKeywords,
    text: input.text,
  })
  const workspaceId = input.workspaceId ?? getActiveWorkspaceId()
  if (query) {
    navigate(buildKbEvalLobbyPath({ prefillQuery: query, workspaceId }))
    deps.message.success(deps.t('kbChunks.trialSearchOpened'))
    return
  }
  const clip = (input.text ?? '').replace(/\s+/g, ' ').trim().slice(0, 500)
  if (clip) {
    try {
      await copyToClipboard(clip)
      deps.message.info(deps.t('kbChunks.trialSearchClipboard'))
    } catch {
      deps.message.warning(deps.t('kbChunks.trialSearchClipboardFailed'))
    }
  }
  navigate(buildKbEvalLobbyPath({ workspaceId, trialClip: true }))
}
