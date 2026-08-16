import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import StatLabelWithHelp from '@/components/StatLabelWithHelp'
import { DeleteActionIcon } from '@/components/DeleteActionIcon'
import { App, Button, Form, Input, Select, Space, Switch, Table, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useTranslation } from 'react-i18next'
import {
  defaultPipelineStages,
  parsePipelineJson,
  serializePipelineFromTable,
  ROUTE_PROVIDERS,
  type PipelineRouteRow,
  type PipelineStages,
} from '@/utils/kbIngestionPipeline'

type Props = {
  value?: string
  globalDefaultProvider: string
  builtinRoutes?: Array<{
    match: { ext?: string[]; mime_prefix?: string }
    extract_provider: string
    engine?: string
    builtin?: boolean
    readonly?: boolean
  }>
  onSave: (json: string) => void | Promise<void>
}

export default function KbIngestionPipelineEditor({ value, globalDefaultProvider, builtinRoutes = [], onSave }: Props) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [routes, setRoutes] = useState<PipelineRouteRow[]>([])
  const [stages, setStages] = useState<PipelineStages>(defaultPipelineStages())
  const [advanced, setAdvanced] = useState(false)
  const [advancedJson, setAdvancedJson] = useState('')
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve())

  useEffect(() => {
    try {
      const parsed = parsePipelineJson(value)
      setRoutes(parsed.routes)
      setStages(parsed.stages)
      setAdvancedJson(parsed.advancedJson || (value?.trim() ? value : ''))
    } catch {
      setAdvancedJson(value ?? '')
    }
  }, [value])

  const providerOptions = useMemo(
    () => ROUTE_PROVIDERS.map((p) => ({ value: p, label: p })),
    [],
  )

  const notifySaved = useCallback(() => {
    message.success(t('admin.settings.pipelineSaved'))
  }, [message, t])

  const persistTable = useCallback(async (nextStages = stages) => {
    const saveTask = saveQueueRef.current.then(async () => {
      try {
        const json = serializePipelineFromTable(routes, nextStages)
        await onSave(json)
        notifySaved()
      } catch (e) {
        message.error(String(e))
      }
    })
    saveQueueRef.current = saveTask
    await saveTask
  }, [message, notifySaved, onSave, routes, stages])

  const persistAdvanced = useCallback(async () => {
    try {
      const parsed = parsePipelineJson(advancedJson)
      const json = serializePipelineFromTable(parsed.routes, parsed.stages)
      await onSave(json || advancedJson.trim())
      notifySaved()
    } catch (e) {
      message.error(String(e))
    }
  }, [advancedJson, message, notifySaved, onSave])

  const columns: ColumnsType<PipelineRouteRow> = [
    {
      title: t('admin.settings.pipelineMatchKind'),
      dataIndex: 'matchKind',
      render: (_, row, index) => (
        <Select
          value={row.matchKind}
          options={[
            { value: 'mime_prefix', label: 'MIME 前缀' },
            { value: 'ext', label: '扩展名' },
          ]}
          onChange={(v) => {
            setRoutes((prev) => prev.map((r, i) => (i === index ? { ...r, matchKind: v } : r)))
          }}
        />
      ),
    },
    {
      title: t('admin.settings.pipelineMatchValue'),
      render: (_, row, index) =>
        row.matchKind === 'mime_prefix' ? (
          <Input
            value={row.mimePrefix}
            placeholder="application/pdf"
            onChange={(e) => {
              const v = e.target.value
              setRoutes((prev) => prev.map((r, i) => (i === index ? { ...r, mimePrefix: v } : r)))
            }}
          />
        ) : (
          <Input
            value={row.extensions}
            placeholder=".docx, .pptx"
            onChange={(e) => {
              const v = e.target.value
              setRoutes((prev) => prev.map((r, i) => (i === index ? { ...r, extensions: v } : r)))
            }}
          />
        ),
    },
    {
      title: t('admin.settings.pipelineProvider'),
      dataIndex: 'extractProvider',
      render: (_, row, index) => (
        <Select
          value={row.extractProvider}
          options={providerOptions}
          onChange={(v) => {
            setRoutes((prev) => prev.map((r, i) => (i === index ? { ...r, extractProvider: v } : r)))
          }}
        />
      ),
    },
    {
      title: '',
      width: 72,
      render: (_, __, index) => (
        <Tooltip title={t('admin.settings.pipelineRemoveRoute')}>
          <Button
            danger
            size="small"
            icon={<DeleteActionIcon />}
            aria-label={t('admin.settings.pipelineRemoveRoute')}
            onClick={() => setRoutes((prev) => prev.filter((_, i) => i !== index))}
          />
        </Tooltip>
      ),
    },
  ]

  return (
    <div className="admin-settings-pipeline">
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Typography.Text type="secondary" className="admin-settings-pipeline__hint">
          {t('admin.settings.pipelineEffectiveDefault', { provider: globalDefaultProvider })}
        </Typography.Text>
        {builtinRoutes.length > 0 && (
          <div className="admin-settings-pipeline__builtin" aria-label={t('admin.settings.pipelineBuiltinTitle')}>
            <Typography.Text strong>{t('admin.settings.pipelineBuiltinTitle')}</Typography.Text>
            {builtinRoutes.map((route) => (
              <Typography.Paragraph key={route.engine ?? route.extract_provider} type="secondary" style={{ marginBottom: 0 }}>
                {(route.match.ext ?? []).join(', ')} → {route.extract_provider} / {route.engine ?? '—'} · {t('admin.settings.pipelineBuiltinReadonly')}
              </Typography.Paragraph>
            ))}
          </div>
        )}
        <Form.Item label={t('admin.settings.pipelineAdvancedJson')} className="admin-settings-pipeline__advanced">
          <Switch checked={advanced} onChange={setAdvanced} />
        </Form.Item>
        {!advanced ? (
          <>
            <Table
              className="admin-settings-pipeline-table"
              size="small"
              pagination={false}
              rowKey="key"
              dataSource={routes}
              columns={columns}
            />
            <Space wrap className="admin-settings-pipeline__actions">
              <Button
                onClick={() =>
                  setRoutes((prev) => [
                    ...prev,
                    {
                      key: `r-${Date.now()}`,
                      matchKind: 'mime_prefix',
                      mimePrefix: '',
                      extensions: '',
                      extractProvider: 'legacy',
                    },
                  ])
                }
              >
                {t('admin.settings.pipelineAddRoute')}
              </Button>
              <Button type="primary" className="admin-settings-pipeline__save" onClick={() => void persistTable()}>
                {t('admin.settings.pipelineSave')}
              </Button>
            </Space>
            <Form.Item
              label={
                <StatLabelWithHelp
                  label={t('admin.settings.pipelineStageEntityExtract')}
                  help={t('admin.settings.pipelineStageEntityExtractHint')}
                  tooltipClassName="admin-settings-pipeline-help-tooltip"
                />
              }
              className="admin-settings-pipeline__stage"
            >
              <Switch
                checked={stages.entity_extract}
                onChange={(v) => {
                  const nextStages = { ...stages, entity_extract: v }
                  setStages(nextStages)
                  void persistTable(nextStages)
                }}
              />
            </Form.Item>
          </>
        ) : (
          <>
            <Input.TextArea
              className="admin-settings-pipeline__json"
              rows={10}
              value={advancedJson}
              onChange={(e) => setAdvancedJson(e.target.value)}
              placeholder='{"version":1,"routes":[],"stages":{}}'
            />
            <Button type="primary" className="admin-settings-pipeline__save" onClick={() => void persistAdvanced()}>
              {t('admin.settings.pipelineSave')}
            </Button>
          </>
        )}
      </Space>
    </div>
  )
}
