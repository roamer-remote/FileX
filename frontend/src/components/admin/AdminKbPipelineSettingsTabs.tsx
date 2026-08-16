import { useState, useEffect, type ReactNode } from 'react'
import { QuestionCircleOutlined } from '@ant-design/icons'
import { Button, Col, Form, Input, InputNumber, Row, Select, Switch, Tooltip, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import KbIngestionPipelineEditor from '@/components/admin/KbIngestionPipelineEditor'
import KbPipelineTopology from '@/components/admin/KbPipelineTopology'
import StatLabelWithHelp from '@/components/StatLabelWithHelp'
import { getSelectableExtractProviders } from '@/utils/extractProviders'
import { getAdminMineruVersion, type MineruVersionResponse } from '@/api/admin'
import '@/styles/helpDoc.css'

export type KbPipelineSettingsSubTab = 'engine' | 'routing' | 'topology' | 'insavlo' | 'mineru'

const KB_PIPELINE_SUB_TABS: KbPipelineSettingsSubTab[] = [
  'engine',
  'routing',
  'topology',
  'mineru',
  'insavlo',
]

type AdminKbPipelineSettingsTabsProps = {
  insavloReady: boolean
  pipelineJson: string
  globalExtractProvider: string
  insavloCallbackUrl: string
  insavloHelpStatus: string
  insavloHelpText: string
  testingInsavlo: boolean
  onTestInsavlo: () => void
  onPipelineSave: (json: string) => Promise<void>
  builtinRoutes?: SystemSettingsBuiltinRoute[]
}

export type SystemSettingsBuiltinRoute = {
  match: { ext?: string[]; mime_prefix?: string }
  extract_provider: string
  engine?: string
  builtin?: boolean
  readonly?: boolean
}

function currentPageOrigin(): string {
  return window.location.origin.replace(/\/$/, '')
}

function kbPipelineSubTabButtonId(key: KbPipelineSettingsSubTab): string {
  return `admin-kb-pipeline-subtab-${key}`
}

function kbPipelineSubTabPanelId(key: KbPipelineSettingsSubTab): string {
  return `admin-kb-pipeline-subtabpanel-${key}`
}

type KbPipelineSubTabPanelProps = {
  tabKey: KbPipelineSettingsSubTab
  activeTab: KbPipelineSettingsSubTab
  children: ReactNode
}

function KbPipelineSubTabPanel({ tabKey, activeTab, children }: KbPipelineSubTabPanelProps) {
  return (
    <div
      role="tabpanel"
      id={kbPipelineSubTabPanelId(tabKey)}
      aria-labelledby={kbPipelineSubTabButtonId(tabKey)}
      hidden={activeTab !== tabKey}
      className="admin-settings-kb-pipeline-tabs__panel"
    >
      {children}
    </div>
  )
}

export default function AdminKbPipelineSettingsTabs({
  insavloReady,
  pipelineJson,
  globalExtractProvider,
  insavloCallbackUrl,
  insavloHelpStatus,
  insavloHelpText,
  testingInsavlo,
  onTestInsavlo,
  onPipelineSave,
  builtinRoutes,
}: AdminKbPipelineSettingsTabsProps) {
  const { t } = useTranslation()
  const [activeSubTab, setActiveSubTab] = useState<KbPipelineSettingsSubTab>('engine')

  // MinerU 运行时版本（仅在切到 mineru tab 时获取）
  const [mineruVersion, setMineruVersion] = useState<MineruVersionResponse | null>(null)
  const [mineruVersionLoading, setMineruVersionLoading] = useState(false)

  useEffect(() => {
    if (activeSubTab !== 'mineru') return
    let cancelled = false
    setMineruVersionLoading(true)
    getAdminMineruVersion()
      .then((res) => {
        if (!cancelled) setMineruVersion(res.data)
      })
      .catch(() => {
        if (!cancelled) setMineruVersion({ error: '获取失败' })
      })
      .finally(() => {
        if (!cancelled) setMineruVersionLoading(false)
      })
    return () => { cancelled = true }
  }, [activeSubTab])

  const enginePanel = (
    <Row gutter={[12, 0]}>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_extract_provider"
          label={t('admin.settings.kbExtractProvider')}
          tooltip={t('admin.settings.kbExtractProviderHint')}
        >
          <Select
            options={getSelectableExtractProviders(insavloReady).map((value) => ({
              value,
              label: value,
            }))}
          />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_pdf_inspector_enabled"
          label={t('admin.settings.kbPdfInspectorEnabled')}
          tooltip={t('admin.settings.kbPdfInspectorEnabledHint')}
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_chunk_profile"
          label={t('admin.settings.kbChunkProfile')}
          tooltip={t('admin.settings.kbChunkProfileHint')}
        >
          <Select
            options={[
              { value: 'default', label: t('admin.settings.kbChunkProfileDefault') },
              { value: 'long_doc', label: t('admin.settings.kbChunkProfileLongDoc') },
              { value: 'qa_pairs', label: t('admin.settings.kbChunkProfileQa') },
              { value: 'table_heavy', label: t('admin.settings.kbChunkProfileTable') },
            ]}
          />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_chunk_size"
          label={t('admin.settings.kbChunkSize')}
          tooltip={t('admin.settings.kbChunkSizeHint')}
        >
          <InputNumber min={1} max={100000} step={50} precision={0} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_chunk_overlap"
          label={t('admin.settings.kbChunkOverlap')}
          tooltip={t('admin.settings.kbChunkOverlapHint')}
        >
          <InputNumber min={0} max={99999} step={10} precision={0} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_chunk_split_recursive"
          label={t('admin.settings.kbChunkSplitRecursive')}
          tooltip={t('admin.settings.kbChunkSplitRecursiveHint')}
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_embed_cache_enabled"
          label={t('admin.settings.kbEmbedCacheEnabled')}
          tooltip={t('admin.settings.kbEmbedCacheEnabledHint')}
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name="kb_embed_effective_max_chars" label={t('admin.settings.kbEmbedEffectiveMaxChars')}>
          <InputNumber disabled className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_index_max_attempts"
          label={t('admin.settings.kbIndexMaxAttempts')}
          extra={t('admin.settings.kbIndexMaxAttemptsHint')}
        >
          <InputNumber min={1} max={10} step={1} precision={0} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_post_async_enabled"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.kbPostAsyncEnabled')}
              help={t('admin.settings.kbPostAsyncEnabledHint')}
            />
          }
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_post_max_attempts"
          label={t('admin.settings.kbPostMaxAttempts')}
          extra={t('admin.settings.kbPostMaxAttemptsHint')}
        >
          <InputNumber min={1} max={10} step={1} precision={0} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_voice_notify_enabled"
          label={t('admin.settings.kbVoiceNotifyEnabled')}
          extra={t('admin.settings.kbVoiceNotifyEnabledHint')}
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_voice_notify_playback_ttl_seconds"
          label={t('admin.settings.kbVoiceNotifyPlaybackTtl')}
          extra={t('admin.settings.kbVoiceNotifyPlaybackTtlHint')}
        >
          <InputNumber min={1} max={3600} step={10} precision={0} className="admin-settings-number" />
        </Form.Item>
      </Col>
    </Row>
  )

  const routingPanel = (
    <>
      <p className="admin-settings-kb-pipeline-tabs__desc">{t('admin.settings.pipelineDesc')}</p>
      <KbIngestionPipelineEditor
        value={pipelineJson}
        globalDefaultProvider={globalExtractProvider}
        builtinRoutes={builtinRoutes}
        onSave={onPipelineSave}
      />
    </>
  )

  const insavloPanel = (
    <Row gutter={[12, 0]}>
      <Col xs={24}>
        <span className="stat-label-with-help">
          <Typography.Text strong className="stat-label-with-help__text">
            Insavlo
          </Typography.Text>
          <Tooltip
            classNames={{ root: 'admin-insavlo-help-tooltip' }}
            styles={{ root: { maxWidth: 680 } }}
            title={
              <>
                <div>{insavloHelpStatus}</div>
                <div>{t('admin.settings.insavloNoFallbackHint')}</div>
              </>
            }
          >
            <button type="button" className="stat-label-with-help__btn" aria-label={insavloHelpText}>
              <QuestionCircleOutlined aria-hidden />
            </button>
          </Tooltip>
        </span>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name="kb_extract_insavlo_enabled" label={t('admin.settings.insavloEnabled')} valuePropName="checked">
          <Switch />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name="kb_extract_insavlo_timeout_minutes" label={t('admin.settings.insavloTimeoutMinutes')}>
          <InputNumber min={2} max={120} step={1} precision={0} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name="kb_extract_insavlo_base_url" label={t('admin.settings.insavloBaseUrl')}>
          <Input placeholder="https://demo.insavlo.com/insavlo/public-api" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name="kb_extract_insavlo_callback_origin" label={t('admin.settings.insavloCallbackOrigin')}>
          <Input placeholder={currentPageOrigin()} />
        </Form.Item>
      </Col>
      <Col xs={24}>
        <Typography.Text type="secondary">
          {t('admin.settings.insavloCallbackUrl')}: {insavloCallbackUrl}
        </Typography.Text>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name="kb_extract_insavlo_skill_code" label={t('admin.settings.insavloSkillCode')}>
          <Input />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item name="kb_extract_insavlo_api_key" label={t('admin.settings.insavloApiKey')}>
          <Input />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12} className="admin-insavlo-secret-col">
        <Form.Item name="kb_extract_insavlo_webhook_secret" label={t('admin.settings.insavloWebhookSecret')}>
          <Input />
        </Form.Item>
        <Button loading={testingInsavlo} onClick={onTestInsavlo}>
          {t('admin.settings.testInsavlo')}
        </Button>
      </Col>
    </Row>
  )

  const mineruPanel = (
    <Row gutter={[12, 0]}>
      <Col xs={24}>
        <Typography.Text type="secondary">
          {mineruVersionLoading || !mineruVersion
            ? t('admin.settings.mineruVersionLoading')
            : mineruVersion?.error
              ? t('admin.settings.mineruVersionUnknown')
              : t('admin.settings.mineruVersion', {
                  version: mineruVersion?.mineru_version ?? 'unknown',
                  sidecar: mineruVersion?.sidecar_version ?? 'unknown',
                })}
        </Typography.Text>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="mineru_min_batch_mode"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.mineruMinBatchMode')}
              help={t('admin.settings.mineruMinBatchModeHelp')}
            />
          }
        >
          <Select
            options={[
              { value: 'auto', label: t('admin.settings.mineruMinBatchModeAuto') },
              { value: 'fixed', label: t('admin.settings.mineruMinBatchModeFixed') },
            ]}
          />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="mineru_min_batch_inference_size"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.mineruMinBatchSize')}
              help={t('admin.settings.mineruMinBatchSizeHelp')}
            />
          }
        >
          <InputNumber min={8} max={384} step={1} precision={0} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="mineru_min_batch_floor"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.mineruMinBatchFloor')}
              help={t('admin.settings.mineruMinBatchFloorHelp')}
            />
          }
        >
          <InputNumber min={8} max={384} step={1} precision={0} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="mineru_parse_method"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.mineruParseMethod')}
              help={t('admin.settings.mineruParseMethodHelp')}
            />
          }
        >
          <Select
            options={[
              { value: 'auto', label: 'auto' },
              { value: 'txt', label: 'txt' },
              { value: 'ocr', label: 'ocr' },
            ]}
          />
        </Form.Item>
      </Col>
      <Col xs={24} sm={8}>
        <Form.Item
          name="mineru_formula_enable"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.mineruFormulaEnable')}
              help={t('admin.settings.mineruFormulaEnableHelp')}
            />
          }
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      </Col>
      <Col xs={24} sm={8}>
        <Form.Item
          name="mineru_table_enable"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.mineruTableEnable')}
              help={t('admin.settings.mineruTableEnableHelp')}
            />
          }
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="mineru_parse_timeout_sec"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.mineruParseTimeoutSec')}
              help={t('admin.settings.mineruParseTimeoutSecHelp')}
            />
          }
        >
          <InputNumber min={60} max={3600} step={10} precision={0} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="mineru_rpc_timeout_sec"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.mineruRpcTimeoutSec')}
              help={t('admin.settings.mineruRpcTimeoutSecHelp')}
            />
          }
        >
          <InputNumber min={60} max={7200} step={60} precision={0} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={8}>
        <Form.Item
          name="mineru_page_chunk_enabled"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.mineruPageChunkEnabled')}
              help={t('admin.settings.mineruPageChunkEnabledHelp')}
            />
          }
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      </Col>
      <Col xs={24} sm={8}>
        <Form.Item
          name="mineru_page_chunk_threshold"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.mineruPageChunkThreshold')}
              help={t('admin.settings.mineruPageChunkThresholdHelp')}
            />
          }
        >
          <InputNumber min={1} max={2000} step={1} precision={0} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={8}>
        <Form.Item
          name="mineru_page_chunk_pages"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.mineruPageChunkPages')}
              help={t('admin.settings.mineruPageChunkPagesHelp')}
            />
          }
        >
          <InputNumber min={8} max={200} step={1} precision={0} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={8}>
        <Form.Item
          name="mineru_table_auto_rotate"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.mineruTableAutoRotate')}
              help={t('admin.settings.mineruTableAutoRotateHelp')}
            />
          }
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      </Col>
      <Col xs={24} sm={8}>
        <Form.Item
          name="mineru_table_rotate_max_tables"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.mineruTableRotateMaxTables')}
              help={t('admin.settings.mineruTableRotateMaxTablesHelp')}
            />
          }
        >
          <InputNumber min={1} max={64} step={1} precision={0} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={8}>
        <Form.Item
          name="mineru_table_rotate_timeout_sec"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.mineruTableRotateTimeoutSec')}
              help={t('admin.settings.mineruTableRotateTimeoutSecHelp')}
            />
          }
        >
          <InputNumber min={1} max={300} step={1} precision={0} className="admin-settings-number" />
        </Form.Item>
      </Col>
    </Row>
  )

  return (
    <div className="admin-settings-kb-pipeline-tabs">
      <nav
        className="wlg-help-section-nav wlg-help-section-nav--admin admin-settings-kb-pipeline-tabs__nav"
        role="tablist"
        aria-label={t('admin.settings.kbPipelineSubTabsAria')}
      >
        {KB_PIPELINE_SUB_TABS.map((key) => {
          const isActive = activeSubTab === key
          return (
            <button
              key={key}
              type="button"
              role="tab"
              id={kbPipelineSubTabButtonId(key)}
              className={`wlg-help-section-btn wlg-help-section-btn--admin${isActive ? ' is-active' : ''}`}
              aria-selected={isActive}
              aria-controls={kbPipelineSubTabPanelId(key)}
              onClick={() => setActiveSubTab(key)}
            >
              {t(`admin.settings.kbPipelineSubTabs.${key}`)}
            </button>
          )
        })}
      </nav>
      <div className="admin-settings-kb-pipeline-tabs__panels">
        <KbPipelineSubTabPanel tabKey="engine" activeTab={activeSubTab}>
          {enginePanel}
        </KbPipelineSubTabPanel>
        <KbPipelineSubTabPanel tabKey="routing" activeTab={activeSubTab}>
          {routingPanel}
        </KbPipelineSubTabPanel>
        <KbPipelineSubTabPanel tabKey="topology" activeTab={activeSubTab}>
          <KbPipelineTopology />
        </KbPipelineSubTabPanel>
        <KbPipelineSubTabPanel tabKey="mineru" activeTab={activeSubTab}>
          {mineruPanel}
        </KbPipelineSubTabPanel>
        <KbPipelineSubTabPanel tabKey="insavlo" activeTab={activeSubTab}>
          {insavloPanel}
        </KbPipelineSubTabPanel>
      </div>
    </div>
  )
}
