import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { App } from 'antd'
import { forceRaptorKnowledgeBaseFile } from '@/api/knowledgeBase'

export function useKbForceRaptor(options?: { onQueued?: (fileId: number, status: string) => void }) {
  const { t } = useTranslation()
  const { message, modal } = App.useApp()
  const [loadingFileId, setLoadingFileId] = useState<number | null>(null)

  const confirmForceRaptor = useCallback(
    (fileId: number) => {
      modal.confirm({
        title: t("fileList.forceRaptorConfirmTitle"),
        content: t("fileList.forceRaptorConfirmContent"),
        okText: t("fileList.forceRaptorAction"),
        okButtonProps: { danger: true },
        onOk: async () => {
          setLoadingFileId(fileId)
          try {
            const res = await forceRaptorKnowledgeBaseFile(fileId)
            if (res.kb_post_status === "ready") {
              message.success(t("fileList.forceRaptorDone"))
            } else if (res.kb_post_status === "failed") {
              message.error(t("fileList.forceRaptorFailed"))
            } else {
              message.success(t("fileList.forceRaptorQueued"))
            }
            options?.onQueued?.(fileId, res.kb_post_status)
          } catch (err: unknown) {
            const detail =
              err && typeof err === "object" && "response" in err
                ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
                : undefined
            message.error(detail || t("fileList.forceRaptorFailed"))
          } finally {
            setLoadingFileId(null)
          }
        },
      })
    },
    [message, modal, options, t],
  )

  return { confirmForceRaptor, forceRaptorLoadingFileId: loadingFileId }
}
