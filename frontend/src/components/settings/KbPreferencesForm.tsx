import { useState, type ReactNode } from 'react'
import { Col, Form, InputNumber, Row, Select, Switch, Tag } from 'antd'
import type { FormInstance } from 'antd'
import { useTranslation } from 'react-i18next'
import SettingsSection from '@/components/admin/SettingsSection'
import UserPreferencesTabNav from '@/components/settings/UserPreferencesTabNav'
import {
  USER_PREFERENCES_TAB_BY_ID,
  userPreferencesTabButtonId,
  userPreferencesTabPanelId,
  type UserPreferencesTabDef,
  type UserPreferencesTabId,
} from '@/pages/account/userPreferencesTabs'
import { useSystemSettingsStore } from '@/stores/systemSettingsStore'
import { getSelectableExtractProviders } from '@/utils/extractProviders'

export type KbPreferencesFormValues = {
  tag_graph_enabled: boolean
  tag_graph_single_node_symbol_size: number
  tag_graph_node_display_ratio: number
  tag_graph_edge_line_width: number
  kb_extract_provider: string
  kb_chunk_profile: string
  kb_index_max_attempts: number
  kb_voice_notify_enabled: boolean
  kb_voice_notify_playback_ttl_seconds: number
  kb_search_hybrid_enabled: boolean
  kb_fts_config: string
  kb_search_min_score: number
  kb_search_boost_keyword_bonus: number
  kb_search_mmr_lambda: number
  kb_search_filename_boost: number
  kb_search_modality_boost_enabled: boolean
  kb_search_modality_boost: number
  kb_search_default_top_k: number
  kb_wiki_compile_min_sources: number
}

type KbPreferencesFormProps = {
  form: FormInstance<KbPreferencesFormValues>
  inheritedKeys?: string[]
}

type UserHintField = keyof KbPreferencesFormValues

const USER_HINT_KEYS: Partial<Record<UserHintField, string>> = {
  kb_fts_config: 'account.preferences.kbFtsConfigUserHint',
  kb_index_max_attempts: 'account.preferences.hints.kbIndexMaxAttempts',
  kb_extract_provider: 'account.preferences.hints.kbExtractProvider',
  kb_chunk_profile: 'account.preferences.hints.kbChunkProfile',
  kb_voice_notify_enabled: 'account.preferences.hints.kbVoiceNotifyEnabled',
  kb_voice_notify_playback_ttl_seconds:
    'account.preferences.hints.kbVoiceNotifyPlaybackTtl',
  kb_search_hybrid_enabled: 'account.preferences.hints.kbSearchHybridEnabled',
  kb_wiki_compile_min_sources: 'account.preferences.hints.kbWikiCompileMinSources',
}

type UserPreferencesTabPanelProps = {
  tab: UserPreferencesTabDef
  activeTabId: UserPreferencesTabId
  children: ReactNode
}

function UserPreferencesTabPanel({ tab, activeTabId, children }: UserPreferencesTabPanelProps) {
  return (
    <div
      role="tabpanel"
      id={userPreferencesTabPanelId(tab.hash)}
      aria-labelledby={userPreferencesTabButtonId(tab.hash)}
      hidden={activeTabId !== tab.tabId}
      className="admin-settings-tab-panel"
    >
      {children}
    </div>
  )
}

function InheritedBadge({ show }: { show: boolean }) {
  const { t } = useTranslation()
  if (!show) return null
  return (
    <Tag color="default" style={{ marginInlineStart: 8, fontWeight: 400 }}>
      {t('account.preferences.inheritedBadge')}
    </Tag>
  )
}

function useUserPreferenceCopy() {
  const { t } = useTranslation()

  function fieldExtra(field: UserHintField, adminHintKey: string): string {
    const userKey = USER_HINT_KEYS[field]
    if (userKey) return t(userKey)
    return `${t(adminHintKey)} ${t('account.preferences.userHintSuffix')}`
  }

  return { fieldExtra, t }
}

export default function KbPreferencesForm({ form, inheritedKeys = [] }: KbPreferencesFormProps) {
  const { fieldExtra, t } = useUserPreferenceCopy()
  const inherited = new Set(inheritedKeys)
  const insavloReady = useSystemSettingsStore((s) => s.kb_extract_insavlo_ready ?? false)
  const [activeTab, setActiveTab] = useState<UserPreferencesTabId>('tagGraph')
  const tabs = USER_PREFERENCES_TAB_BY_ID

  return (
    <Form
      form={form}
      layout="vertical"
      size="small"
      requiredMark={false}
      className="admin-settings-form kb-preferences-form"
    >
      <div className="admin-settings-split">
        <UserPreferencesTabNav activeTabId={activeTab} onTabChange={setActiveTab} />
        <div className="admin-settings-main">
          <div className="admin-settings-tab-panels">
            <UserPreferencesTabPanel tab={tabs.tagGraph} activeTabId={activeTab}>
              <SettingsSection
                variant="flat"
                id={tabs.tagGraph.sectionId}
                title={t(tabs.tagGraph.labelKey)}
                description={t(tabs.tagGraph.descKey)}
              >
                <Row gutter={[12, 0]}>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="tag_graph_enabled"
                      label={<>{t('admin.settings.tagGraphEnabled')}<InheritedBadge show={inherited.has('tag_graph_enabled')} /></>}
                      extra={fieldExtra('tag_graph_enabled', 'admin.settings.tagGraphEnabledHint')}
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="tag_graph_single_node_symbol_size"
                      label={<>{t('admin.settings.tagGraphSingleNodeSymbolSize')}<InheritedBadge show={inherited.has('tag_graph_single_node_symbol_size')} /></>}
                      extra={fieldExtra('tag_graph_single_node_symbol_size', 'admin.settings.tagGraphSingleNodeSymbolSizeHint')}
                    >
                      <InputNumber min={8} max={160} step={1} precision={0} className="admin-settings-number" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="tag_graph_edge_line_width"
                      label={<>{t('admin.settings.tagGraphEdgeLineWidth')}<InheritedBadge show={inherited.has('tag_graph_edge_line_width')} /></>}
                      extra={fieldExtra('tag_graph_edge_line_width', 'admin.settings.tagGraphEdgeLineWidthHint')}
                    >
                      <InputNumber min={1} max={12} step={1} precision={0} className="admin-settings-number" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="tag_graph_node_display_ratio"
                      label={<>{t('admin.settings.tagGraphNodeDisplayRatio')}<InheritedBadge show={inherited.has('tag_graph_node_display_ratio')} /></>}
                      extra={fieldExtra('tag_graph_node_display_ratio', 'admin.settings.tagGraphNodeDisplayRatioHint')}
                    >
                      <InputNumber min={0.1} max={5} step={0.1} precision={1} className="admin-settings-number" />
                    </Form.Item>
                  </Col>
                </Row>
              </SettingsSection>
            </UserPreferencesTabPanel>

            <UserPreferencesTabPanel tab={tabs.kbPipeline} activeTabId={activeTab}>
              <SettingsSection
                variant="flat"
                id={tabs.kbPipeline.sectionId}
                title={t(tabs.kbPipeline.labelKey)}
                description={t(tabs.kbPipeline.descKey)}
              >
                <Row gutter={[12, 0]}>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="kb_extract_provider"
                      label={<>{t('admin.settings.kbExtractProvider')}<InheritedBadge show={inherited.has('kb_extract_provider')} /></>}
                      tooltip={fieldExtra('kb_extract_provider', 'admin.settings.kbExtractProviderHint')}
                    >
                      <Select options={getSelectableExtractProviders(insavloReady).map((value) => ({ value, label: value }))} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="kb_chunk_profile"
                      label={<>{t('admin.settings.kbChunkProfile')}<InheritedBadge show={inherited.has('kb_chunk_profile')} /></>}
                      tooltip={fieldExtra('kb_chunk_profile', 'admin.settings.kbChunkProfileHint')}
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
                      name="kb_index_max_attempts"
                      label={<>{t('admin.settings.kbIndexMaxAttempts')}<InheritedBadge show={inherited.has('kb_index_max_attempts')} /></>}
                      extra={fieldExtra('kb_index_max_attempts', 'admin.settings.kbIndexMaxAttemptsHint')}
                    >
                      <InputNumber min={1} max={10} step={1} precision={0} className="admin-settings-number" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="kb_voice_notify_enabled"
                      label={<>{t('admin.settings.kbVoiceNotifyEnabled')}<InheritedBadge show={inherited.has('kb_voice_notify_enabled')} /></>}
                      extra={fieldExtra('kb_voice_notify_enabled', 'admin.settings.kbVoiceNotifyEnabledHint')}
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="kb_voice_notify_playback_ttl_seconds"
                      label={<>{t('admin.settings.kbVoiceNotifyPlaybackTtl')}<InheritedBadge show={inherited.has('kb_voice_notify_playback_ttl_seconds')} /></>}
                      extra={fieldExtra('kb_voice_notify_playback_ttl_seconds', 'admin.settings.kbVoiceNotifyPlaybackTtlHint')}
                    >
                      <InputNumber min={1} max={3600} step={10} precision={0} className="admin-settings-number" />
                    </Form.Item>
                  </Col>
                </Row>
              </SettingsSection>
            </UserPreferencesTabPanel>

            <UserPreferencesTabPanel tab={tabs.kbSearch} activeTabId={activeTab}>
              <SettingsSection
                variant="flat"
                id={tabs.kbSearch.sectionId}
                title={t(tabs.kbSearch.labelKey)}
                description={t(tabs.kbSearch.descKey)}
              >
                <Row gutter={[12, 0]}>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="kb_search_hybrid_enabled"
                      label={<>{t('admin.settings.kbSearchHybridEnabled')}<InheritedBadge show={inherited.has('kb_search_hybrid_enabled')} /></>}
                      extra={fieldExtra('kb_search_hybrid_enabled', 'admin.settings.kbSearchHybridEnabledHint')}
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="kb_fts_config"
                      label={<>{t('admin.settings.kbFtsConfig')}<InheritedBadge show={inherited.has('kb_fts_config')} /></>}
                      extra={fieldExtra('kb_fts_config', 'admin.settings.kbFtsConfigHint')}
                    >
                      <Select
                        options={[
                          { value: 'zh_cn', label: t('admin.settings.kbFtsConfigZhCn') },
                          { value: 'simple', label: t('admin.settings.kbFtsConfigSimple') },
                        ]}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="kb_search_min_score"
                      label={<>{t('admin.settings.kbSearchMinScore')}<InheritedBadge show={inherited.has('kb_search_min_score')} /></>}
                      extra={fieldExtra('kb_search_min_score', 'admin.settings.kbSearchMinScoreHint')}
                    >
                      <InputNumber min={0} max={1} step={0.05} precision={2} className="admin-settings-number" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="kb_search_boost_keyword_bonus"
                      label={<>{t('admin.settings.kbSearchBoostKeywordBonus')}<InheritedBadge show={inherited.has('kb_search_boost_keyword_bonus')} /></>}
                      extra={fieldExtra('kb_search_boost_keyword_bonus', 'admin.settings.kbSearchBoostKeywordBonusHint')}
                    >
                      <InputNumber min={0} max={0.5} step={0.01} precision={2} className="admin-settings-number" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="kb_search_mmr_lambda"
                      label={<>{t('admin.settings.kbSearchMmrLambda')}<InheritedBadge show={inherited.has('kb_search_mmr_lambda')} /></>}
                      extra={fieldExtra('kb_search_mmr_lambda', 'admin.settings.kbSearchMmrLambdaHint')}
                    >
                      <InputNumber min={0} max={1} step={0.05} precision={2} className="admin-settings-number" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="kb_search_filename_boost"
                      label={<>{t('admin.settings.kbSearchFilenameBoost')}<InheritedBadge show={inherited.has('kb_search_filename_boost')} /></>}
                      extra={fieldExtra('kb_search_filename_boost', 'admin.settings.kbSearchFilenameBoostHint')}
                    >
                      <InputNumber min={0} max={0.5} step={0.05} precision={2} className="admin-settings-number" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="kb_search_modality_boost_enabled"
                      label={<>{t('admin.settings.kbSearchModalityBoostEnabled')}<InheritedBadge show={inherited.has('kb_search_modality_boost_enabled')} /></>}
                      extra={fieldExtra('kb_search_modality_boost_enabled', 'admin.settings.kbSearchModalityBoostEnabledHint')}
                      valuePropName="checked"
                    >
                      <Switch />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="kb_search_modality_boost"
                      label={<>{t('admin.settings.kbSearchModalityBoost')}<InheritedBadge show={inherited.has('kb_search_modality_boost')} /></>}
                      extra={fieldExtra('kb_search_modality_boost', 'admin.settings.kbSearchModalityBoostHint')}
                    >
                      <InputNumber min={0} max={0.5} step={0.05} precision={2} className="admin-settings-number" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="kb_search_default_top_k"
                      label={<>{t('admin.settings.kbSearchDefaultTopK')}<InheritedBadge show={inherited.has('kb_search_default_top_k')} /></>}
                      extra={fieldExtra('kb_search_default_top_k', 'admin.settings.kbSearchDefaultTopKHint')}
                    >
                      <InputNumber min={5} max={50} step={1} precision={0} className="admin-settings-number" />
                    </Form.Item>
                  </Col>
                </Row>
              </SettingsSection>
            </UserPreferencesTabPanel>

            <UserPreferencesTabPanel tab={tabs.wiki} activeTabId={activeTab}>
              <SettingsSection
                variant="flat"
                id={tabs.wiki.sectionId}
                title={t(tabs.wiki.labelKey)}
                description={t(tabs.wiki.descKey)}
              >
                <Row gutter={[12, 0]}>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="kb_wiki_compile_min_sources"
                      label={<>{t('admin.settings.kbWikiCompileMinSources')}<InheritedBadge show={inherited.has('kb_wiki_compile_min_sources')} /></>}
                      extra={fieldExtra('kb_wiki_compile_min_sources', 'admin.settings.kbWikiCompileMinSourcesHint')}
                    >
                      <InputNumber min={1} max={20} step={1} precision={0} className="admin-settings-number" />
                    </Form.Item>
                  </Col>
                </Row>
              </SettingsSection>
            </UserPreferencesTabPanel>
          </div>
        </div>
      </div>
    </Form>
  )
}
