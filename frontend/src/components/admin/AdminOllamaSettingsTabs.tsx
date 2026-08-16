import { useState, type ReactNode } from 'react'
import { QuestionCircleOutlined } from '@ant-design/icons'
import { Button, Col, Form, Input, InputNumber, Row, Select, Switch } from 'antd'
import { Trans, useTranslation } from 'react-i18next'
import HelpDocModal from '@/components/HelpDocModal'
import StatLabelWithHelp from '@/components/StatLabelWithHelp'
import { RAPTOR_CONCEPT_HELP_HTML_EN } from '@/content/raptorConceptHelpEn'
import { RAPTOR_CONCEPT_HELP_HTML_ZH } from '@/content/raptorConceptHelpZh'
import '@/styles/helpDoc.css'

export type OllamaSettingsSubTab = 'embed' | 'postLlm' | 'raptor'

const OLLAMA_SUB_TABS: OllamaSettingsSubTab[] = ['embed', 'postLlm', 'raptor']

type AdminOllamaSettingsTabsProps = {
  testingOllama: boolean
  onTestOllama: () => void
  kbRaptorEnabled: boolean
  onRaptorEnabledChange: (enabled: boolean) => void
}

function ollamaSubTabButtonId(key: OllamaSettingsSubTab): string {
  return `admin-ollama-subtab-${key}`
}

function ollamaSubTabPanelId(key: OllamaSettingsSubTab): string {
  return `admin-ollama-subtabpanel-${key}`
}

type OllamaSubTabPanelProps = {
  tabKey: OllamaSettingsSubTab
  activeTab: OllamaSettingsSubTab
  children: ReactNode
}

function OllamaSubTabPanel({ tabKey, activeTab, children }: OllamaSubTabPanelProps) {
  return (
    <div
      role="tabpanel"
      id={ollamaSubTabPanelId(tabKey)}
      aria-labelledby={ollamaSubTabButtonId(tabKey)}
      hidden={activeTab !== tabKey}
      className="admin-settings-ollama-tabs__panel"
    >
      {children}
    </div>
  )
}

export default function AdminOllamaSettingsTabs({
  testingOllama,
  onTestOllama,
  kbRaptorEnabled,
  onRaptorEnabledChange,
}: AdminOllamaSettingsTabsProps) {
  const { t, i18n } = useTranslation()
  const [activeSubTab, setActiveSubTab] = useState<OllamaSettingsSubTab>('embed')
  const [raptorHelpOpen, setRaptorHelpOpen] = useState(false)
  const raptorHelpHtml =
    i18n.language.startsWith('zh') ? RAPTOR_CONCEPT_HELP_HTML_ZH : RAPTOR_CONCEPT_HELP_HTML_EN

  const embedPanel = (
    <>
      <div className="admin-settings-ollama-embed-notice">
        <Trans
          i18nKey="admin.settings.ollamaEmbedOpsNotice"
          components={{ strong: <strong />, code: <code />, br: <br /> }}
        />
      </div>
      <Row gutter={[12, 0]}>
        <Col xs={24} sm={12}>
          <Form.Item
            name="ollama_base_url"
            label={
              <StatLabelWithHelp
                label={t('admin.settings.ollamaBaseUrl')}
                help={t('admin.settings.ollamaBaseUrlHelp')}
              />
            }
            extra={t('admin.settings.ollamaBaseUrlHint')}
          >
            <Input placeholder="http://filex-ollama:11434" />
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item
            name="ollama_embed_model"
            label={
              <StatLabelWithHelp
                label={t('admin.settings.ollamaEmbedModel')}
                help={t('admin.settings.ollamaEmbedModelHelp')}
              />
            }
          >
            <Input placeholder="bge-m3:latest" />
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item
            name="ollama_embed_dim"
            label={
              <StatLabelWithHelp
                label={t('admin.settings.ollamaEmbedDim')}
                help={t('admin.settings.ollamaEmbedDimHelp')}
              />
            }
            extra={t('admin.settings.ollamaEmbedDimHint')}
          >
            <InputNumber min={128} max={4096} step={1} precision={0} className="admin-settings-number" />
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item
            name="ollama_chat_model"
            label={
              <StatLabelWithHelp
                label={t('admin.settings.ollamaChatModel')}
                help={t('admin.settings.ollamaChatModelHelp')}
              />
            }
          >
            <Input placeholder="qwen2.5:7b" />
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item shouldUpdate noStyle>
            {({ getFieldValue }) => (
              <Form.Item
                name="ollama_api_key"
                label={
                  <StatLabelWithHelp
                    label={t('admin.settings.ollamaApiKey')}
                    help={t('admin.settings.ollamaApiKeyHelp')}
                  />
                }
                extra={
                  getFieldValue('ollama_has_api_key')
                    ? t('admin.settings.secretConfigured')
                    : t('admin.settings.ollamaApiKeyEmptyHint')
                }
              >
                <Input.Password autoComplete="new-password" placeholder="Ollama API Key" />
              </Form.Item>
            )}
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item shouldUpdate noStyle>
            {({ getFieldValue }) =>
              getFieldValue('ollama_has_api_key') ? (
                <Form.Item
                  name="clear_ollama_api_key"
                  label={
                    <StatLabelWithHelp
                      label={t('admin.settings.ollamaClearApiKey')}
                      help={t('admin.settings.ollamaClearApiKeyHelp')}
                    />
                  }
                  valuePropName="checked"
                >
                  <Switch />
                </Form.Item>
              ) : null
            }
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item
            name="ollama_timeout_sec"
            label={
              <StatLabelWithHelp
                label={t('admin.settings.ollamaTimeoutSec')}
                help={t('admin.settings.ollamaTimeoutSecHelp')}
              />
            }
          >
            <InputNumber min={10} max={600} step={1} className="admin-settings-number" />
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item
            name="ollama_embed_batch_size"
            label={
              <StatLabelWithHelp
                label={t('admin.settings.ollamaEmbedBatchSize')}
                help={t('admin.settings.ollamaEmbedBatchSizeHelp')}
              />
            }
          >
            <InputNumber min={1} max={64} step={1} precision={0} className="admin-settings-number" />
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item
            name="ollama_num_parallel"
            label={
              <StatLabelWithHelp
                label={t('admin.settings.ollamaNumParallel')}
                help={t('admin.settings.ollamaNumParallelHint')}
              />
            }
          >
            <InputNumber min={1} max={32} step={1} precision={0} className="admin-settings-number" />
          </Form.Item>
        </Col>
        <Col xs={24} sm={12}>
          <Form.Item
            name="ollama_embed_concurrency"
            label={
              <StatLabelWithHelp
                label={t('admin.settings.ollamaEmbedConcurrency')}
                help={t('admin.settings.ollamaEmbedConcurrencyHint')}
              />
            }
          >
            <InputNumber min={1} max={32} step={1} precision={0} className="admin-settings-number" />
          </Form.Item>
        </Col>
        <Col xs={24}>
          <Button loading={testingOllama} onClick={onTestOllama}>
            {t('admin.settings.testOllama')}
          </Button>
        </Col>
      </Row>
    </>
  )

  const postLlmPanel = (
    <Form.Item shouldUpdate noStyle>
      {({ getFieldValue }) => {
        const reuseChatModel = getFieldValue('kb_post_llm_provider') === 'ollama'

        return (
    <Row gutter={[12, 0]}>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_post_llm_provider"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.kbPostLlmProvider')}
              help={t('admin.settings.kbPostLlmProviderHint')}
            />
          }
        >
          <Select
            options={[
              { value: 'ollama', label: t('admin.settings.kbPostLlmProviderOllama') },
              { value: 'openai_compatible', label: t('admin.settings.kbPostLlmProviderOpenAI') },
            ]}
          />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_post_llm_json_mode"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.kbPostLlmJsonMode')}
              help={t('admin.settings.kbPostLlmJsonModeHint')}
            />
          }
        >
          <Select
            options={[
              { value: 'auto', label: t('admin.settings.kbPostLlmJsonModeAuto') },
              { value: 'response_format', label: t('admin.settings.kbPostLlmJsonModeResponseFormat') },
              { value: 'prompt_only', label: t('admin.settings.kbPostLlmJsonModePromptOnly') },
            ]}
          />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_post_llm_base_url"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.kbPostLlmBaseUrl')}
              help={t('admin.settings.kbPostLlmBaseUrlHint')}
            />
          }
        >
          <Input disabled={reuseChatModel} placeholder="https://api.example.com/v1" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_post_llm_model"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.kbPostLlmModel')}
              help={t('admin.settings.kbPostLlmModelHint')}
            />
          }
        >
          <Input disabled={reuseChatModel} placeholder="gpt-4o-mini" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item shouldUpdate noStyle>
          {({ getFieldValue }) => (
            <Form.Item
              name="kb_post_llm_api_key"
              label={
                <StatLabelWithHelp
                  label={t('admin.settings.kbPostLlmApiKey')}
                  help={t('admin.settings.kbPostLlmApiKeyHint')}
                />
              }
              extra={
                getFieldValue('kb_post_llm_has_api_key')
                  ? t('admin.settings.secretConfigured')
                  : t('admin.settings.kbPostLlmApiKeyEmptyHint')
              }
            >
              <Input.Password disabled={reuseChatModel} autoComplete="new-password" placeholder="sk-..." />
            </Form.Item>
          )}
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_post_llm_timeout_sec"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.kbPostLlmTimeoutSec')}
              help={t('admin.settings.kbPostLlmTimeoutSecHint')}
            />
          }
        >
          <InputNumber disabled={reuseChatModel} min={5} max={300} step={1} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item shouldUpdate noStyle>
          {({ getFieldValue }) =>
            getFieldValue('kb_post_llm_has_api_key') ? (
              <Form.Item
                name="clear_kb_post_llm_api_key"
                label={
                  <StatLabelWithHelp
                    label={t('admin.settings.kbPostLlmClearApiKey')}
                    help={t('admin.settings.kbPostLlmClearApiKeyHint')}
                  />
                }
                valuePropName="checked"
              >
                <Switch disabled={reuseChatModel} />
              </Form.Item>
            ) : null
          }
        </Form.Item>
      </Col>
    </Row>
        )
      }}
    </Form.Item>
  )

  const raptorPanel = (
    <Row gutter={[12, 0]}>
      <Form.Item name="kb_raptor_enabled" hidden valuePropName="checked">
        <Switch />
      </Form.Item>
      <Col xs={24} sm={12}>
        <Form.Item
          label={
            <StatLabelWithHelp
              label={t('admin.settings.kbRaptorEnabled')}
              help={t('admin.settings.kbRaptorEnabledHint')}
            />
          }
        >
          <Switch checked={kbRaptorEnabled} onChange={onRaptorEnabledChange} />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_raptor_min_chars"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.kbRaptorMinChars')}
              help={t('admin.settings.kbRaptorMinCharsHint')}
            />
          }
          extra={t('admin.settings.kbRaptorMinCharsExtra')}
        >
          <InputNumber min={1000} max={500000} step={1000} disabled className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_large_doc_char_threshold"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.kbLargeDocCharThreshold')}
              help={t('admin.settings.kbLargeDocCharThresholdHint')}
            />
          }
          extra={t('admin.settings.kbLargeDocCharThresholdExtra')}
        >
          <InputNumber min={10000} max={10000000} step={10000} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_large_doc_chunk_size"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.kbLargeDocChunkSize')}
              help={t('admin.settings.kbLargeDocChunkSizeHint')}
            />
          }
          extra={t('admin.settings.kbLargeDocChunkSizeExtra')}
        >
          <InputNumber min={200} max={8000} step={100} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_large_doc_chunk_overlap"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.kbLargeDocChunkOverlap')}
              help={t('admin.settings.kbLargeDocChunkOverlapHint')}
            />
          }
          extra={t('admin.settings.kbLargeDocChunkOverlapExtra')}
        >
          <InputNumber min={0} max={2000} step={10} className="admin-settings-number" />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_large_doc_post_enabled"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.kbLargeDocPostEnabled')}
              help={t('admin.settings.kbLargeDocPostEnabledHint')}
            />
          }
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      </Col>
      <Col xs={24} sm={12}>
        <Form.Item
          name="kb_large_doc_raptor_enabled"
          label={
            <StatLabelWithHelp
              label={t('admin.settings.kbLargeDocRaptorEnabled')}
              help={t('admin.settings.kbLargeDocRaptorEnabledHint')}
            />
          }
          valuePropName="checked"
        >
          <Switch disabled={!kbRaptorEnabled} />
        </Form.Item>
      </Col>
    </Row>
  )

  return (
    <div className="admin-settings-ollama-tabs">
      <nav
        className="wlg-help-section-nav wlg-help-section-nav--admin admin-settings-ollama-tabs__nav"
        role="tablist"
        aria-label={t('admin.settings.ollamaSubTabsAria')}
      >
        {OLLAMA_SUB_TABS.map((key) => {
          const isActive = activeSubTab === key
          if (key === 'raptor') {
            return (
              <span key={key} className="admin-settings-ollama-tabs__tab-with-help">
                <button
                  type="button"
                  role="tab"
                  id={ollamaSubTabButtonId(key)}
                  className={`wlg-help-section-btn wlg-help-section-btn--admin${isActive ? ' is-active' : ''}`}
                  aria-selected={isActive}
                  aria-controls={ollamaSubTabPanelId(key)}
                  onClick={() => setActiveSubTab(key)}
                >
                  {t(`admin.settings.ollamaSubTabs.${key}`)}
                </button>
                <button
                  type="button"
                  className="admin-settings-ollama-tabs__tab-help-btn"
                  aria-label={t('admin.settings.raptorConceptHelpTitle')}
                  onClick={() => setRaptorHelpOpen(true)}
                >
                  <QuestionCircleOutlined aria-hidden />
                </button>
              </span>
            )
          }
          return (
            <button
              key={key}
              type="button"
              role="tab"
              id={ollamaSubTabButtonId(key)}
              className={`wlg-help-section-btn wlg-help-section-btn--admin${isActive ? ' is-active' : ''}`}
              aria-selected={isActive}
              aria-controls={ollamaSubTabPanelId(key)}
              onClick={() => setActiveSubTab(key)}
            >
              {t(`admin.settings.ollamaSubTabs.${key}`)}
            </button>
          )
        })}
      </nav>
      <div className="admin-settings-ollama-tabs__panels">
        <OllamaSubTabPanel tabKey="embed" activeTab={activeSubTab}>
          {embedPanel}
        </OllamaSubTabPanel>
        <OllamaSubTabPanel tabKey="postLlm" activeTab={activeSubTab}>
          {postLlmPanel}
        </OllamaSubTabPanel>
        <OllamaSubTabPanel tabKey="raptor" activeTab={activeSubTab}>
          {raptorPanel}
        </OllamaSubTabPanel>
      </div>
      <HelpDocModal
        open={raptorHelpOpen}
        onClose={() => setRaptorHelpOpen(false)}
        title={t('admin.settings.raptorConceptHelpTitle')}
        closeLabel={t('common.close')}
        html={raptorHelpHtml}
        width={640}
      />
    </div>
  )
}
