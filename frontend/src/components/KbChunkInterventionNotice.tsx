import { useTranslation, Trans } from 'react-i18next'
import { Alert, Button, Space } from 'antd'

export type KbChunkInterventionNoticeProps = {
  showActions?: boolean
  reindexLoading?: boolean
  forceReindexLoading?: boolean
  onReindex?: () => void
  onForceReindex?: () => void
  className?: string
}

export default function KbChunkInterventionNotice({
  showActions = false,
  reindexLoading = false,
  forceReindexLoading = false,
  onReindex,
  onForceReindex,
  className,
}: KbChunkInterventionNoticeProps) {
  const { t } = useTranslation()

  return (
    <Alert
      type="warning"
      showIcon
      className={className}
      message={
        <Trans
          i18nKey="kbChunks.overrideNotice"
          components={{
            force: <strong />,
            md: <strong />,
          }}
        />
      }
      action={
        showActions ? (
          <Space direction="vertical" size={4} align="end">
            <Button size="small" loading={reindexLoading} onClick={onReindex}>
              {t('kbChunks.reindexBtn')}
            </Button>
            <Button
              type="link"
              size="small"
              loading={forceReindexLoading}
              onClick={onForceReindex}
              className="kbc-force-reindex-link"
            >
              {t('kbChunks.forceReindexBtn')}
            </Button>
          </Space>
        ) : undefined
      }
    />
  )
}
