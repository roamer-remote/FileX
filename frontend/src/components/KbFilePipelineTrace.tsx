import { useEffect, useMemo, useState } from 'react'
import { App, Button, Drawer, Space, Steps, Typography } from 'antd'
import type { StepsProps } from 'antd'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { getFilePipelineTrace, type FilePipelineTraceResponse } from '@/api/files'
import { FlTableMarqueeText } from '@/components/FileListComponents'
import { useAuthStore } from '@/stores/authStore'
import { formatDate } from '@/utils'
import '@/components/FileList.css'
import './KbFilePipelineTrace.css'

type Props = {
  fileId: number | null
  filename?: string
  open: boolean
  onClose: () => void
}

function mapStepStatus(status: string): StepsProps['status'] {
  switch (status) {
    case 'finish':
      return 'finish'
    case 'error':
      return 'error'
    case 'process':
      return 'process'
    case 'skip':
      return 'wait'
    default:
      return 'wait'
  }
}

function postSkipReasonLabel(t: (key: string, options?: { defaultValue?: string }) => string, reason: string): string {
  return t(`kbPipeline.postSkipReasons.${reason}`, { defaultValue: reason })
}

export default function KbFilePipelineTrace({ fileId, filename, open, onClose }: Props) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const isAdmin = useAuthStore((s) => s.user?.is_admin === true)
  const [data, setData] = useState<FilePipelineTraceResponse | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || fileId == null) {
      setData(null)
      return
    }
    let cancelled = false
    void (async () => {
      setLoading(true)
      try {
        const res = await getFilePipelineTrace(fileId)
        if (!cancelled) setData(res.data)
      } catch (e) {
        if (!cancelled) message.error(String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [fileId, message, open])

  const stepItems = useMemo(() => {
    if (!data) return []
    return data.steps.map((step) => ({
      title: step.title,
      status: mapStepStatus(step.status),
      description: (
        <div className="kb-file-pipeline-trace__step-desc">
          {step.detail ? <Typography.Text type="secondary">{step.detail}</Typography.Text> : null}
          {step.key === 'index' && (step.embed_ms != null || step.persist_ms != null || step.post_index_ms != null) ? (
            <Typography.Text type="secondary" className="kb-file-pipeline-trace__perf">
              {t('kbPipeline.indexPerf', {
                embed: step.embed_ms != null ? (step.embed_ms / 1000).toFixed(1) : '—',
                persist: step.persist_ms != null ? (step.persist_ms / 1000).toFixed(1) : '—',
                post: step.post_index_ms != null ? (step.post_index_ms / 1000).toFixed(1) : '—',
              })}
              {step.large_pdf ? ` ${t('kbPipeline.largePdfMode')}` : ''}
            </Typography.Text>
          ) : null}
          {step.key === 'index' &&
          (step.post_entity_ms != null || step.post_sag_ms != null || step.post_raptor_ms != null) ? (
            <Typography.Text type="secondary" className="kb-file-pipeline-trace__perf">
              {t('kbPipeline.indexPostStages', {
                entity: step.post_entity_ms != null ? (step.post_entity_ms / 1000).toFixed(2) : '—',
                sag: step.post_sag_ms != null ? (step.post_sag_ms / 1000).toFixed(2) : '—',
                raptor: step.post_raptor_ms != null ? (step.post_raptor_ms / 1000).toFixed(2) : '—',
              })}
            </Typography.Text>
          ) : null}
          {step.key === 'index' && step.post_skip_reason ? (
            <Typography.Text type="secondary" className="kb-file-pipeline-trace__perf">
              {t('kbPipeline.postSkipReason', {
                reason: postSkipReasonLabel(t, step.post_skip_reason),
              })}
              {step.large_pdf &&
              step.embed_ms == null &&
              step.persist_ms == null &&
              step.post_index_ms == null
                ? ` ${t('kbPipeline.largePdfMode')}`
                : ''}
            </Typography.Text>
          ) : null}
          {step.key === 'post' &&
          (step.post_entity_ms != null || step.post_sag_ms != null || step.post_raptor_ms != null) ? (
            <Typography.Text type="secondary" className="kb-file-pipeline-trace__perf">
              {t('kbPipeline.postStages', {
                entity: step.post_entity_ms != null ? (step.post_entity_ms / 1000).toFixed(2) : '—',
                sag: step.post_sag_ms != null ? (step.post_sag_ms / 1000).toFixed(2) : '—',
                raptor: step.post_raptor_ms != null ? (step.post_raptor_ms / 1000).toFixed(2) : '—',
              })}
            </Typography.Text>
          ) : null}
          {step.key === 'post' && step.post_skip_reason ? (
            <Typography.Text type="secondary" className="kb-file-pipeline-trace__perf">
              {t('kbPipeline.postSkipReason', {
                reason: postSkipReasonLabel(t, step.post_skip_reason),
              })}
            </Typography.Text>
          ) : null}
          {step.error_message ? (
            <Typography.Text type="danger" className="kb-file-pipeline-trace__error">
              {step.error_message}
            </Typography.Text>
          ) : null}
          {step.occurred_at ? (
            <span className="kb-file-pipeline-trace__time">{formatDate(step.occurred_at)}</span>
          ) : null}
          {isAdmin && step.log_deep_link ? (
            <Link to={step.log_deep_link}>{t('kbPipeline.viewLogs')}</Link>
          ) : null}
        </div>
      ),
    }))
  }, [data, isAdmin, t])

  const displayName = filename ?? data?.filename ?? (fileId != null ? `#${fileId}` : '')

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={480}
      destroyOnClose
      rootClassName="kb-file-pipeline-trace-drawer"
      title={
        <div className="kb-file-pipeline-trace__header">
          <FlTableMarqueeText
            key={`${open}-${displayName}`}
            text={displayName}
            className="kb-file-pipeline-trace__filename"
          />
          {data?.trace_provider ? (
            <Typography.Text type="secondary" className="kb-file-pipeline-trace__provider">
              {t('kbPipeline.traceProvider', { provider: data.trace_provider })}
            </Typography.Text>
          ) : null}
        </div>
      }
    >
      {loading ? (
        <Typography.Text type="secondary">{t('kbPipeline.loading')}</Typography.Text>
      ) : data ? (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            {t('kbPipeline.traceSummary', {
              chunks: data.chunk_count,
              notes: data.has_md_notes ? t('kbPipeline.notesYes') : t('kbPipeline.notesNo'),
            })}
          </Typography.Text>
          <Steps direction="vertical" size="small" items={stepItems} />
        </Space>
      ) : null}
      <div className="kb-file-pipeline-trace__footer">
        <Button onClick={onClose}>{t('common.close')}</Button>
      </div>
    </Drawer>
  )
}
