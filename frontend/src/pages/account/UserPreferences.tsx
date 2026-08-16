import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { App, Button, Form, Modal, Spin } from 'antd'
import { ArrowLeftOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import {
  getUserPreferences,
  putUserPreferences,
  resetUserPreferences,
  type UserPreferencesResponse,
  type UserPreferencesUpdate,
} from '@/api/settings'
import { formatApiError } from '@/api/index'
import KbPreferencesForm, {
  type KbPreferencesFormValues,
} from '@/components/settings/KbPreferencesForm'
import { useSystemSettingsStore } from '@/stores/systemSettingsStore'
import '@/pages/admin/AdminPage.css'
import './UserPreferences.css'

function effectiveToFormValues(
  effective: UserPreferencesResponse['effective'],
): KbPreferencesFormValues {
  return {
    tag_graph_enabled: Boolean(effective.tag_graph_enabled),
    tag_graph_single_node_symbol_size: Number(effective.tag_graph_single_node_symbol_size),
    tag_graph_node_display_ratio: Number(effective.tag_graph_node_display_ratio),
    tag_graph_edge_line_width: Number(effective.tag_graph_edge_line_width),
    kb_extract_provider: String(effective.kb_extract_provider ?? 'legacy'),
    kb_chunk_profile: String(effective.kb_chunk_profile ?? 'default'),
    kb_index_max_attempts: Number(effective.kb_index_max_attempts),
    kb_voice_notify_enabled: Boolean(effective.kb_voice_notify_enabled),
    kb_voice_notify_playback_ttl_seconds: Number(
      effective.kb_voice_notify_playback_ttl_seconds ?? 120,
    ),
    kb_search_hybrid_enabled: Boolean(effective.kb_search_hybrid_enabled),
    kb_fts_config: String(effective.kb_fts_config ?? 'zh_cn'),
    kb_search_min_score: Number(effective.kb_search_min_score),
    kb_search_boost_keyword_bonus: Number(effective.kb_search_boost_keyword_bonus),
    kb_search_mmr_lambda: Number(effective.kb_search_mmr_lambda),
    kb_search_filename_boost: Number(effective.kb_search_filename_boost),
    kb_search_modality_boost_enabled: Boolean(effective.kb_search_modality_boost_enabled),
    kb_search_modality_boost: Number(effective.kb_search_modality_boost),
    kb_search_default_top_k: Number(effective.kb_search_default_top_k),
    kb_wiki_compile_min_sources: Number(effective.kb_wiki_compile_min_sources),
  }
}

function buildSavePatch(
  current: KbPreferencesFormValues,
  baseline: KbPreferencesFormValues,
): UserPreferencesUpdate {
  const patch: UserPreferencesUpdate = {}
  ;(Object.keys(current) as (keyof KbPreferencesFormValues)[]).forEach((key) => {
    if (current[key] !== baseline[key]) {
      ;(patch as Record<string, unknown>)[key] = current[key]
    }
  })
  return patch
}

function notifyUserSettingsChanged() {
  window.dispatchEvent(new CustomEvent('filex:user-settings-changed'))
}

export default function UserPreferencesPage() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [form] = Form.useForm<KbPreferencesFormValues>()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [inheritedKeys, setInheritedKeys] = useState<string[]>([])
  const baselineRef = useRef<KbPreferencesFormValues | null>(null)

  const applyPayload = useCallback(
    (body: UserPreferencesResponse) => {
      const values = effectiveToFormValues(body.effective)
      baselineRef.current = values
      setInheritedKeys(body.inherited_keys)
      form.setFieldsValue(values)
    },
    [form],
  )

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getUserPreferences()
      applyPayload(res.data)
    } catch (err) {
      message.error(formatApiError(err))
    } finally {
      setLoading(false)
    }
  }, [applyPayload, message])

  useEffect(() => {
    void reload()
  }, [reload])

  async function onSave() {
    try {
      const current = await form.validateFields()
      const baseline = baselineRef.current
      if (!baseline) return
      const patch = buildSavePatch(current, baseline)
      if (Object.keys(patch).length === 0) {
        message.info(t('account.preferences.noChanges'))
        return
      }
      setSaving(true)
      const res = await putUserPreferences(patch)
      applyPayload(res.data)
      await useSystemSettingsStore.getState().load()
      notifyUserSettingsChanged()
      message.success(t('account.preferences.saveSuccess'))
    } catch (err) {
      if (err && typeof err === 'object' && 'errorFields' in err) return
      message.error(formatApiError(err))
    } finally {
      setSaving(false)
    }
  }

  function onResetAll() {
    Modal.confirm({
      title: t('account.preferences.resetConfirmTitle'),
      content: t('account.preferences.resetConfirmBody'),
      okText: t('account.preferences.resetConfirmOk'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      onOk: async () => {
        setResetting(true)
        try {
          const res = await resetUserPreferences()
          applyPayload(res.data)
          await useSystemSettingsStore.getState().load()
          notifyUserSettingsChanged()
          message.success(t('account.preferences.resetSuccess'))
        } catch (err) {
          message.error(formatApiError(err))
          throw err
        } finally {
          setResetting(false)
        }
      },
    })
  }

  return (
    <div className="user-preferences-page admin-root">
      <div className="admin-panel admin-panel--settings user-preferences-panel">
        <header className="admin-header">
          <button type="button" className="ah-back" onClick={() => navigate(-1)}>
            <ArrowLeftOutlined />
            {t('common.back')}
          </button>
          <div className="ah-title-group user-preferences-title-group">
            <div className="user-preferences-title-row">
              <h1 className="ah-title">{t('account.preferences.title')}</h1>
              <p className="ah-sub">{t('account.preferences.subtitle')}</p>
            </div>
            <div className="ah-title-actions">
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={saving}
                disabled={loading || resetting}
                onClick={() => void onSave()}
              >
                {t('account.preferences.save')}
              </Button>
              <Button
                icon={<ReloadOutlined />}
                loading={resetting}
                disabled={loading || saving}
                onClick={onResetAll}
              >
                {t('account.preferences.resetAll')}
              </Button>
            </div>
          </div>
        </header>

        <Spin spinning={loading} wrapperClassName="user-preferences-spin admin-settings-spin">
          <div className="user-preferences-body admin-settings-body">
            <KbPreferencesForm form={form} inheritedKeys={inheritedKeys} />
          </div>
        </Spin>
      </div>
    </div>
  )
}
