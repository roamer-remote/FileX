import { useEffect, useMemo, useState } from 'react'
import { App, Spin, Tag, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import { getKbPipelineTopology, type PipelineTopologyNode, type PipelineTopologyResponse } from '@/api/admin'
import { groupNodesByLayer } from '@/utils/kbPipelineTopologyLayout'
import './KbPipelineTopology.css'

const STAGE_LABEL_KEYS: Record<string, string> = {
  entity_extract: 'admin.settings.pipelineStageEntityExtract',
  wiki_lint_on_index: 'admin.settings.pipelineStageWikiLint',
}

function renderNode(node: PipelineTopologyNode) {
  return (
    <div
      key={node.id}
      className={
        'kb-pipeline-topology__node' +
        (node.highlight ? ' kb-pipeline-topology__node--highlight' : '') +
        (node.kind === 'read_only' ? ' kb-pipeline-topology__node--readonly' : '')
      }
      title={node.description ?? undefined}
    >
      <span className="kb-pipeline-topology__node-label">{node.label}</span>
      {node.kind === 'sidecar' || node.kind === 'read_only' ? (
        <Tag className="kb-pipeline-topology__node-tag">{node.kind}</Tag>
      ) : null}
    </div>
  )
}

export default function KbPipelineTopology() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [data, setData] = useState<PipelineTopologyResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setLoading(true)
      try {
        const res = await getKbPipelineTopology()
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
  }, [message])

  const layers = useMemo(() => {
    if (!data) return []
    return groupNodesByLayer(data.nodes, data.edges)
  }, [data])

  const stageTags = useMemo(() => {
    if (!data) return []
    return Object.entries(data.stages).map(([key, enabled]) => ({
      key,
      label: STAGE_LABEL_KEYS[key] ? t(STAGE_LABEL_KEYS[key]) : key,
      enabled,
    }))
  }, [data, t])

  if (loading) {
    return (
      <div className="kb-pipeline-topology kb-pipeline-topology--loading">
        <Spin />
      </div>
    )
  }

  if (!data) return null

  return (
    <section className="kb-pipeline-topology" aria-label={t('admin.settings.pipelineTopologyTitle')}>
      <header className="kb-pipeline-topology__header">
        <Typography.Text strong>{t('admin.settings.pipelineTopologyTitle')}</Typography.Text>
        <Typography.Text type="secondary" className="kb-pipeline-topology__hint">
          {t('admin.settings.pipelineTopologyHint')}
        </Typography.Text>
      </header>

      <div className="kb-pipeline-topology__dag">
        {layers.map((layer, layerIndex) => (
          <div key={layer.map((node) => node.id).join('-')} className="kb-pipeline-topology__layer">
            <div className="kb-pipeline-topology__layer-nodes">
              {layer.map((node) => renderNode(node))}
            </div>
            {layerIndex < layers.length - 1 ? (
              <div className="kb-pipeline-topology__layer-down" aria-hidden>
                ↓
              </div>
            ) : null}
          </div>
        ))}
      </div>

      <div className="kb-pipeline-topology__meta">
        <Typography.Text type="secondary">
          {t('admin.settings.pipelineEffectiveDefault', { provider: data.global_default_provider })}
        </Typography.Text>
        {data.effective_routes.length > 0 ? (
          <ul className="kb-pipeline-topology__routes">
            {data.effective_routes.map((route) => (
              <li key={route.route_index}>
                <Tag color="blue">{route.match_label}</Tag>
                <span>→</span>
                <Tag color="purple">{route.extract_provider}</Tag>
              </li>
            ))}
          </ul>
        ) : null}
        {stageTags.length > 0 ? (
          <div className="kb-pipeline-topology__stages">
            {stageTags.map((stage) => (
              <Tag key={stage.key} color={stage.enabled ? 'success' : 'default'}>
                {stage.label}: {stage.enabled ? t('admin.settings.pipelineStageOn') : t('admin.settings.pipelineStageOff')}
              </Tag>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  )
}
