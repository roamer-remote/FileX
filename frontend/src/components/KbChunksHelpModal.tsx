import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import HelpDocModal from '@/components/HelpDocModal'
import { getKbChunksHelpHtml } from '@/content/kbChunksHelp'

export type KbChunksHelpModalProps = {
  open: boolean
  onClose: () => void
}

export default function KbChunksHelpModal({ open, onClose }: KbChunksHelpModalProps) {
  const { t, i18n } = useTranslation()
  const html = useMemo(() => getKbChunksHelpHtml(i18n.language), [i18n.language])

  return (
    <HelpDocModal
      open={open}
      onClose={onClose}
      title={t('kbChunks.help.title')}
      closeLabel={t('kbChunks.help.close')}
      html={html}
      width={600}
    />
  )
}
