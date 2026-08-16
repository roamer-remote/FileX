import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import HelpDocModal from '@/components/HelpDocModal'
import { getWikiLinksHelpHtml } from '@/content/wikiLinksHelp'

export type WikiLinksHelpModalProps = {
  open: boolean
  onClose: () => void
}

export default function WikiLinksHelpModal({ open, onClose }: WikiLinksHelpModalProps) {
  const { t, i18n } = useTranslation()
  const html = useMemo(() => getWikiLinksHelpHtml(i18n.language), [i18n.language])

  return (
    <HelpDocModal
      open={open}
      onClose={onClose}
      title={t('wikiLinks.help.title')}
      closeLabel={t('wikiLinks.help.close')}
      html={html}
      width={600}
    />
  )
}
