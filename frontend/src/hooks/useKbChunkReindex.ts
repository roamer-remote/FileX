import { useCallback, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { App } from 'antd'
import { reindexKnowledgeBaseFile } from '@/api/knowledgeBase'
import {
  buildForceReindexConfirmContent,
  type ForceReindexConfirmOptions,
} from '@/lib/kbForceReindexConfirm'

export type { ForceReindexConfirmOptions } from '@/lib/kbForceReindexConfirm'
export { buildForceReindexConfirmContent } from '@/lib/kbForceReindexConfirm'

export type UseKbChunkReindexOptions = {
  onQueued?: (status: string, force: boolean) => void
}

export function useKbChunkReindex(fileId: number, options?: UseKbChunkReindexOptions) {
  const { t } = useTranslation()
  const { message, modal } = App.useApp()
  const [loading, setLoading] = useState<'normal' | 'force' | null>(null)
  const onQueuedRef = useRef(options?.onQueued)
  onQueuedRef.current = options?.onQueued

  const runReindex = useCallback(
    async (force: boolean) => {
      setLoading(force ? 'force' : 'normal')
      try {
        const res = await reindexKnowledgeBaseFile(fileId, { force })
        message.success(force ? t('kbChunks.forceReindexOk') : t('kbChunks.reindexOk'))
        onQueuedRef.current?.(res.index_status, force)
      } catch {
        message.error(force ? t('kbChunks.forceReindexFailed') : t('kbChunks.reindexFailed'))
      } finally {
        setLoading(null)
      }
    },
    [fileId, message, t],
  )

  const reindexNormal = useCallback(() => void runReindex(false), [runReindex])

  const confirmForceReindex = useCallback(
    (opts?: ForceReindexConfirmOptions) => {
      modal.confirm({
        title: t('kbChunks.forceReindexConfirmTitle'),
        content: buildForceReindexConfirmContent(t, opts),
        okText: t('kbChunks.forceReindexBtn'),
        okButtonProps: { danger: true },
        onOk: () => runReindex(true),
      })
    },
    [modal, runReindex, t],
  )

  return {
    reindexNormal,
    confirmForceReindex,
    reindexLoading: loading === 'normal',
    forceReindexLoading: loading === 'force',
  }
}
