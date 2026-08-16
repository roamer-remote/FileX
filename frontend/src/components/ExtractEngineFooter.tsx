import { Tooltip } from 'antd'
import { useTranslation } from 'react-i18next'
import type { FileItem } from '@/api/files'
import { formatDate } from '@/utils'
import { getExtractEngineDisplay } from '@/utils/extractEngineInfo'
import './ExtractEngineFooter.css'

type Props = {
  file: Pick<FileItem, 'extract_engine' | 'extract_status' | 'extracted_at' | 'has_md' | 'original_name'>
  className?: string
}

export default function ExtractEngineFooter({ file, className }: Props) {
  const { t } = useTranslation()
  const info = getExtractEngineDisplay(file, t, formatDate)
  if (!info) return null

  return (
    <Tooltip
      title={<span className="extract-engine-footer__tip">{info.detail}</span>}
      placement="topLeft"
      overlayStyle={{ maxWidth: 420 }}
    >
      <div className={['extract-engine-footer', className].filter(Boolean).join(' ')}>
        <span className="extract-engine-footer__headline">
          <span className="extract-engine-footer__label">{t('extractEngine.footerLabel')}：</span>
          <span className="extract-engine-footer__summary">{info.summary}</span>
        </span>
        {info.extractedAtLabel ? (
          <span className="extract-engine-footer__meta">{info.extractedAtLabel}</span>
        ) : null}
      </div>
    </Tooltip>
  )
}
