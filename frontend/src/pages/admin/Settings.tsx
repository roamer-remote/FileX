import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { App, Button, Col, Divider, Form, Input, InputNumber, Row, Select, Spin, Switch } from 'antd'
import { useTranslation } from 'react-i18next'
import { getAdminSystemSettings, putAdminSystemSettings, testAdminInsavloSettings, testAdminOllamaSettings, type SystemSettingsPayload } from '@/api/admin'
import AdminKbPipelineSettingsTabs from '@/components/admin/AdminKbPipelineSettingsTabs'
import AdminOllamaSettingsTabs from '@/components/admin/AdminOllamaSettingsTabs'
import AdminLicenseSection from '@/components/admin/AdminLicenseSection'
import AdminSettingsTabNav from '@/components/admin/AdminSettingsTabNav'
import SettingsSection from '@/components/admin/SettingsSection'
import StatLabelWithHelp from '@/components/StatLabelWithHelp'
import {
  ADMIN_SETTINGS_TAB_BY_ID,
  resolveAdminSettingsTabFromHash,
  tabButtonId,
  tabPanelId,
  type AdminSettingsTabDef,
  type AdminSettingsTabId,
} from '@/pages/admin/adminSettingsTabs'
import { useSystemSettingsStore } from '@/stores/systemSettingsStore'
import './AdminPage.css'

type SettingsFormValues = SystemSettingsPayload

const SAVE_DEBOUNCE_MS = 500
const KB_POST_LLM_FIELDS = new Set([
  'kb_post_llm_provider',
  'kb_post_llm_base_url',
  'kb_post_llm_api_key',
  'clear_kb_post_llm_api_key',
  'kb_post_llm_model',
  'kb_post_llm_timeout_sec',
  'kb_post_llm_json_mode',
])
const KB_RAGAS_LLM_FIELDS = new Set([
  'kb_ragas_llm_provider',
  'kb_ragas_llm_base_url',
  'kb_ragas_llm_api_key',
  'clear_kb_ragas_llm_api_key',
  'kb_ragas_llm_model',
  'kb_ragas_llm_timeout_seconds',
])

type AdminSettingsTabPanelProps = {
  tab: AdminSettingsTabDef
  activeTabId: AdminSettingsTabId
  children: ReactNode
}

function AdminSettingsTabPanel({ tab, activeTabId, children }: AdminSettingsTabPanelProps) {
  return (
    <div
      role="tabpanel"
      id={tabPanelId(tab.hash)}
      aria-labelledby={tabButtonId(tab.hash)}
      hidden={activeTabId !== tab.tabId}
      className="admin-settings-tab-panel"
    >
      {children}
    </div>
  )
}

function currentPageOrigin(): string {
  return window.location.origin.replace(/\/$/, '')
}

function withDefaultInsavloCallbackOrigin(data: SystemSettingsPayload): {
  values: SystemSettingsPayload
  filledDefault: boolean
} {
  const raw = String(data.kb_extract_insavlo_callback_origin ?? '').trim()
  if (raw) return { values: data, filledDefault: false }
  const origin = currentPageOrigin()
  if (!origin) return { values: data, filledDefault: false }
  return {
    values: { ...data, kb_extract_insavlo_callback_origin: origin },
    filledDefault: true,
  }
}

function hasKbPostLlmChange(changed: Partial<SettingsFormValues>): boolean {
  return Object.keys(changed).some((key) => KB_POST_LLM_FIELDS.has(key))
}

function hasRagasLlmChange(changed: Partial<SettingsFormValues>): boolean {
  return Object.keys(changed).some((key) => KB_RAGAS_LLM_FIELDS.has(key))
}

export function patchFromKbPostLlmValues(
  values: Partial<SettingsFormValues>,
  changed: Partial<SettingsFormValues>,
): Partial<SystemSettingsPayload> {
  const provider = String(values.kb_post_llm_provider ?? '').trim()
  if (provider !== 'ollama' && provider !== 'openai_compatible') return {}

  const patch: Partial<SystemSettingsPayload> = { kb_post_llm_provider: provider }

  const jsonMode = String(values.kb_post_llm_json_mode ?? 'auto')
  if (jsonMode === 'auto' || jsonMode === 'response_format' || jsonMode === 'prompt_only') {
    patch.kb_post_llm_json_mode = jsonMode
  }

  const timeout = Number(values.kb_post_llm_timeout_sec)
  if (Number.isFinite(timeout) && timeout >= 5 && timeout <= 300) {
    patch.kb_post_llm_timeout_sec = Math.round(timeout * 10) / 10
  }

  const baseUrl = String(values.kb_post_llm_base_url ?? '').trim()
  const model = String(values.kb_post_llm_model ?? '').trim()
  if (provider === 'openai_compatible') {
    if (!baseUrl || !model) return {}
    patch.kb_post_llm_base_url = baseUrl
    patch.kb_post_llm_model = model
  } else {
    if ('kb_post_llm_base_url' in changed) patch.kb_post_llm_base_url = baseUrl
    if ('kb_post_llm_model' in changed) patch.kb_post_llm_model = model
  }

  const apiKey = String(values.kb_post_llm_api_key ?? '')
  if (apiKey) {
    patch.kb_post_llm_api_key = apiKey
  }
  if (values.clear_kb_post_llm_api_key === true) {
    patch.clear_kb_post_llm_api_key = true
  }

  return patch
}

export function patchFromRagasLlmValues(
  values: Partial<SettingsFormValues>,
  changed: Partial<SettingsFormValues>,
): Partial<SystemSettingsPayload> {
  const provider = String(values.kb_ragas_llm_provider ?? '').trim()
  if (provider !== 'ollama' && provider !== 'openai_compatible') return {}

  const patch: Partial<SystemSettingsPayload> = { kb_ragas_llm_provider: provider }
  const timeout = Number(values.kb_ragas_llm_timeout_seconds)
  if (!Number.isFinite(timeout) || timeout < 10 || timeout > 300) return {}
  patch.kb_ragas_llm_timeout_seconds = Math.round(timeout)

  const baseUrl = String(values.kb_ragas_llm_base_url ?? '').trim()
  const model = String(values.kb_ragas_llm_model ?? '').trim()
  if (provider === 'openai_compatible') {
    if (!baseUrl || !model) return {}
    patch.kb_ragas_llm_base_url = baseUrl
    patch.kb_ragas_llm_model = model
  } else {
    if ('kb_ragas_llm_base_url' in changed) patch.kb_ragas_llm_base_url = baseUrl
    if ('kb_ragas_llm_model' in changed) {
      if (!model) return {}
      patch.kb_ragas_llm_model = model
    }
  }
  if ('kb_ragas_llm_api_key' in changed && values.kb_ragas_llm_api_key) {
    patch.kb_ragas_llm_api_key = String(values.kb_ragas_llm_api_key)
  }
  if ('clear_kb_ragas_llm_api_key' in changed) {
    patch.clear_kb_ragas_llm_api_key = Boolean(values.clear_kb_ragas_llm_api_key)
  }
  const budgetFields: Array<{ key: keyof SystemSettingsPayload; min: number; max: number }> = [
    { key: 'kb_ragas_eval_concurrency', min: 1, max: 4 },
    { key: 'kb_ragas_eval_context_max_count', min: 1, max: 20 },
    { key: 'kb_ragas_eval_context_max_chars_per_item', min: 200, max: 4000 },
    { key: 'kb_ragas_eval_context_max_total_chars', min: 1000, max: 40000 },
  ]
  for (const { key, min, max } of budgetFields) {
    const value = Number(values[key])
    if (!Number.isFinite(value) || value < min || value > max) return {}
    ;(patch as Record<string, number>)[key] = Math.round(value)
  }
  return patch
}

export function patchFromChanged(
  changed: Partial<SettingsFormValues>,
  currentValues: Partial<SettingsFormValues> = changed,
): Partial<SystemSettingsPayload> {
  // kb_ingestion_pipeline_json is saved via KbIngestionPipelineEditor.onSave, not auto-save.
  if ('kb_ingestion_pipeline_json' in changed) {
    return {}
  }
  const patch: Partial<SystemSettingsPayload> = {}

  if ('clipboard_prefix' in changed) {
    patch.clipboard_prefix = changed.clipboard_prefix ?? ''
  }
  if ('clipboard_suffix' in changed) {
    patch.clipboard_suffix = changed.clipboard_suffix ?? ''
  }

  if ('agent_skill_install_prompt' in changed) {
    patch.agent_skill_install_prompt = changed.agent_skill_install_prompt ?? ''
  }

  if ('tag_graph_single_node_symbol_size' in changed) {
    const n = Number(changed.tag_graph_single_node_symbol_size)
    if (!Number.isFinite(n) || n < 8 || n > 160) return {}
    patch.tag_graph_single_node_symbol_size = Math.round(n)
  }

  if ('tag_graph_edge_line_width' in changed) {
    const n = Number(changed.tag_graph_edge_line_width)
    if (!Number.isFinite(n) || n < 1 || n > 12) return {}
    patch.tag_graph_edge_line_width = Math.round(n)
  }

  if ('tag_graph_node_display_ratio' in changed) {
    const n = Number(changed.tag_graph_node_display_ratio)
    if (!Number.isFinite(n) || n < 0.1 || n > 5) return {}
    patch.tag_graph_node_display_ratio = Math.round(n * 100) / 100
  }

  if ('max_upload_size_mb' in changed) {
    const n = Number(changed.max_upload_size_mb)
    if (!Number.isFinite(n) || n < 1 || n > 10240) return {}
    patch.max_upload_size_mb = Math.round(n)
  }

  if ('workspace_backup_max_mb' in changed) {
    const n = Number(changed.workspace_backup_max_mb)
    if (!Number.isFinite(n) || n < 1 || n > 10240) return {}
    patch.workspace_backup_max_mb = Math.round(n)
  }

  if ('kb_index_max_attempts' in changed) {
    const n = Number(changed.kb_index_max_attempts)
    if (!Number.isFinite(n) || n < 1 || n > 10) return {}
    patch.kb_index_max_attempts = Math.round(n)
  }
  if ('kb_post_async_enabled' in changed) {
    patch.kb_post_async_enabled = Boolean(changed.kb_post_async_enabled)
  }
  if ('kb_post_max_attempts' in changed) {
    const n = Number(changed.kb_post_max_attempts)
    if (!Number.isFinite(n) || n < 1 || n > 10) return {}
    patch.kb_post_max_attempts = Math.round(n)
  }

  if ('agent_run_retention_days' in changed) {
    const n = Number(changed.agent_run_retention_days)
    if (!Number.isFinite(n) || n < 1 || n > 365) return {}
    patch.agent_run_retention_days = Math.round(n)
  }

  if ('shared_workspaces_enabled' in changed) {
    const enabled = Boolean(changed.shared_workspaces_enabled)
    patch.shared_workspaces_enabled = enabled
    patch.enterprise_rbac_enabled = enabled
  }

  if ('tag_graph_enabled' in changed) {
    patch.tag_graph_enabled = Boolean(changed.tag_graph_enabled)
  }

  if ('kb_voice_notify_enabled' in changed) {
    patch.kb_voice_notify_enabled = Boolean(changed.kb_voice_notify_enabled)
  }
  if ('kb_voice_notify_playback_ttl_seconds' in changed) {
    const n = Number(changed.kb_voice_notify_playback_ttl_seconds)
    if (!Number.isFinite(n) || n < 1 || n > 3600) return {}
    patch.kb_voice_notify_playback_ttl_seconds = Math.round(n)
  }

  if ('kb_search_hybrid_enabled' in changed) {
    patch.kb_search_hybrid_enabled = Boolean(changed.kb_search_hybrid_enabled)
  }

  if ('kb_chunk_size' in changed) {
    const raw = changed.kb_chunk_size
    if (raw === null || raw === undefined || String(raw).trim() === "") {
      patch.kb_chunk_size = null
    } else {
      const n = Number(raw)
      if (!Number.isFinite(n) || n <= 0) return {}
      patch.kb_chunk_size = Math.round(n)
    }
  }

  if ('kb_chunk_overlap' in changed) {
    const raw = changed.kb_chunk_overlap
    if (raw === null || raw === undefined || String(raw).trim() === "") {
      patch.kb_chunk_overlap = null
    } else {
      const n = Number(raw)
      if (!Number.isFinite(n) || n < 0) return {}
      patch.kb_chunk_overlap = Math.round(n)
    }
  }

  if ('kb_chunk_split_recursive' in changed) {
    patch.kb_chunk_split_recursive = Boolean(changed.kb_chunk_split_recursive)
  }

  if ('kb_embed_cache_enabled' in changed) {
    patch.kb_embed_cache_enabled = Boolean(changed.kb_embed_cache_enabled)
  }

  if ('kb_chunk_profile' in changed && changed.kb_chunk_profile) {
    patch.kb_chunk_profile = String(changed.kb_chunk_profile)
  }

  // T-4 large doc thresholds (for chunk enlargement and post-processing skip)
  if ('kb_large_doc_char_threshold' in changed) {
    const n = Number(changed.kb_large_doc_char_threshold)
    if (!Number.isFinite(n) || n < 10000 || n > 10000000) return {}
    patch.kb_large_doc_char_threshold = Math.round(n)
  }
  if ('kb_large_doc_chunk_size' in changed) {
    const n = Number(changed.kb_large_doc_chunk_size)
    if (!Number.isFinite(n) || n < 200 || n > 8000) return {}
    patch.kb_large_doc_chunk_size = Math.round(n)
  }
  if ('kb_large_doc_chunk_overlap' in changed) {
    const n = Number(changed.kb_large_doc_chunk_overlap)
    if (!Number.isFinite(n) || n < 0 || n > 2000) return {}
    patch.kb_large_doc_chunk_overlap = Math.round(n)
  }
  if ('kb_large_doc_post_enabled' in changed) {
    patch.kb_large_doc_post_enabled = Boolean(changed.kb_large_doc_post_enabled)
  }
  if ('kb_raptor_enabled' in changed) {
    patch.kb_raptor_enabled = Boolean(changed.kb_raptor_enabled)
    if (!patch.kb_raptor_enabled) {
      patch.kb_large_doc_raptor_enabled = false
    }
  }
  if ('kb_large_doc_raptor_enabled' in changed) {
    patch.kb_large_doc_raptor_enabled = Boolean(changed.kb_large_doc_raptor_enabled)
  }
  if ('kb_ragas_online_eval_enabled' in changed) {
    patch.kb_ragas_online_eval_enabled = Boolean(changed.kb_ragas_online_eval_enabled)
  }
  if ('kb_ragas_online_eval_sample_rate' in changed) {
    const n = Number(changed.kb_ragas_online_eval_sample_rate)
    if (!Number.isFinite(n) || n < 0 || n > 1) return {}
    patch.kb_ragas_online_eval_sample_rate = Math.round(n * 100) / 100
  }
  if ('kb_ragas_online_eval_timeout_seconds' in changed) {
    const n = Number(changed.kb_ragas_online_eval_timeout_seconds)
    if (!Number.isFinite(n) || n < 10 || n > 3000) return {}
    patch.kb_ragas_online_eval_timeout_seconds = Math.round(n)
  }
  if (hasRagasLlmChange(changed)) {
    Object.assign(patch, patchFromRagasLlmValues(currentValues, changed))
  }
  const ragasIntFields: Array<{ key: keyof SystemSettingsPayload; min: number; max: number }> = [
    { key: 'kb_ragas_eval_concurrency', min: 1, max: 4 },
    { key: 'kb_ragas_eval_context_max_count', min: 1, max: 20 },
    { key: 'kb_ragas_eval_context_max_chars_per_item', min: 200, max: 4000 },
    { key: 'kb_ragas_eval_context_max_total_chars', min: 1000, max: 40000 },
  ]
  for (const { key, min, max } of ragasIntFields) {
    if (key in changed) {
      const n = Number(changed[key])
      if (!Number.isFinite(n) || n < min || n > max) return {}
      ;(patch as Record<string, number>)[key] = Math.round(n)
    }
  }
  if ('kb_extract_provider' in changed && changed.kb_extract_provider) {
    patch.kb_extract_provider = String(changed.kb_extract_provider)
  }
  if ('kb_pdf_inspector_enabled' in changed) {
    patch.kb_pdf_inspector_enabled = Boolean(changed.kb_pdf_inspector_enabled)
  }
  if ('kb_extract_insavlo_enabled' in changed) {
    patch.kb_extract_insavlo_enabled = Boolean(changed.kb_extract_insavlo_enabled)
  }
  if ('kb_extract_insavlo_base_url' in changed) {
    patch.kb_extract_insavlo_base_url = String(changed.kb_extract_insavlo_base_url ?? '')
  }
  if ('kb_extract_insavlo_api_key' in changed) {
    patch.kb_extract_insavlo_api_key = String(changed.kb_extract_insavlo_api_key ?? '')
  }
  if ('kb_extract_insavlo_webhook_secret' in changed) {
    patch.kb_extract_insavlo_webhook_secret = String(changed.kb_extract_insavlo_webhook_secret ?? '')
  }
  if ('kb_extract_insavlo_skill_code' in changed) {
    patch.kb_extract_insavlo_skill_code = String(changed.kb_extract_insavlo_skill_code ?? '')
  }
  if ('kb_extract_insavlo_callback_origin' in changed) {
    patch.kb_extract_insavlo_callback_origin = String(changed.kb_extract_insavlo_callback_origin ?? '')
  }
  if ('kb_extract_insavlo_timeout_minutes' in changed) {
    const n = Number(changed.kb_extract_insavlo_timeout_minutes)
    if (!Number.isFinite(n) || n < 2 || n > 120) return {}
    patch.kb_extract_insavlo_timeout_minutes = Math.round(n)
  }

  if ('kb_search_min_score' in changed) {
    const n = Number(changed.kb_search_min_score)
    if (!Number.isFinite(n) || n < 0 || n > 1) return {}
    patch.kb_search_min_score = Math.round(n * 100) / 100
  }

  if ('kb_search_boost_keyword_bonus' in changed) {
    const n = Number(changed.kb_search_boost_keyword_bonus)
    if (!Number.isFinite(n) || n < 0 || n > 0.5) return {}
    patch.kb_search_boost_keyword_bonus = Math.round(n * 100) / 100
  }

  if ('kb_search_mmr_lambda' in changed) {
    const n = Number(changed.kb_search_mmr_lambda)
    if (!Number.isFinite(n) || n < 0 || n > 1) return {}
    patch.kb_search_mmr_lambda = Math.round(n * 100) / 100
  }

  if ('kb_search_filename_boost' in changed) {
    const n = Number(changed.kb_search_filename_boost)
    if (!Number.isFinite(n) || n < 0 || n > 0.5) return {}
    patch.kb_search_filename_boost = Math.round(n * 100) / 100
  }

  if ('kb_search_modality_boost' in changed) {
    const n = Number(changed.kb_search_modality_boost)
    if (!Number.isFinite(n) || n < 0 || n > 0.5) return {}
    patch.kb_search_modality_boost = Math.round(n * 100) / 100
  }

  if ('kb_search_modality_boost_enabled' in changed) {
    patch.kb_search_modality_boost_enabled = Boolean(changed.kb_search_modality_boost_enabled)
  }

  if ('kb_search_default_top_k' in changed) {
    const n = Number(changed.kb_search_default_top_k)
    if (!Number.isFinite(n) || n < 5 || n > 50) return {}
    patch.kb_search_default_top_k = Math.round(n)
  }

  if ('kb_wiki_compile_min_sources' in changed) {
    const n = Number(changed.kb_wiki_compile_min_sources)
    if (!Number.isFinite(n) || n < 1 || n > 20) return {}
    patch.kb_wiki_compile_min_sources = Math.round(n)
  }

  if ('kb_fts_config' in changed && changed.kb_fts_config) {
    const cfg = String(changed.kb_fts_config)
    if (cfg === 'zh_cn' || cfg === 'simple') {
      patch.kb_fts_config = cfg
    }
  }

  if ('ollama_base_url' in changed) {
    patch.ollama_base_url = String(changed.ollama_base_url ?? '').trim()
  }
  if ('ollama_embed_model' in changed) {
    patch.ollama_embed_model = String(changed.ollama_embed_model ?? '').trim()
  }
  if ('ollama_chat_model' in changed) {
    patch.ollama_chat_model = String(changed.ollama_chat_model ?? '').trim()
  }
  if ('ollama_api_key' in changed) {
    const apiKey = String(changed.ollama_api_key ?? '')
    if (apiKey) {
      patch.ollama_api_key = apiKey
    }
  }
  if (changed.clear_ollama_api_key === true) {
    patch.clear_ollama_api_key = true
  }
  if ('ollama_embed_dim' in changed) {
    const n = Number(changed.ollama_embed_dim)
    if (!Number.isFinite(n) || n < 128 || n > 4096) return {}
    patch.ollama_embed_dim = Math.round(n)
  }
  if ('ollama_timeout_sec' in changed) {
    const n = Number(changed.ollama_timeout_sec)
    if (!Number.isFinite(n) || n < 10 || n > 600) return {}
    patch.ollama_timeout_sec = Math.round(n * 10) / 10
  }
  if ('ollama_embed_batch_size' in changed) {
    const n = Number(changed.ollama_embed_batch_size)
    if (!Number.isFinite(n) || n < 1 || n > 64) return {}
    patch.ollama_embed_batch_size = Math.round(n)
  }
  if ('ollama_num_parallel' in changed) {
    const n = Number(changed.ollama_num_parallel)
    if (!Number.isFinite(n) || n < 1 || n > 32) return {}
    patch.ollama_num_parallel = Math.round(n)
  }
  if ('ollama_embed_concurrency' in changed) {
    const n = Number(changed.ollama_embed_concurrency)
    if (!Number.isFinite(n) || n < 1 || n > 32) return {}
    patch.ollama_embed_concurrency = Math.round(n)
  }
  if (hasKbPostLlmChange(changed)) {
    Object.assign(patch, patchFromKbPostLlmValues(currentValues, changed))
  }

  const mineruBoolKeys = [
    'mineru_formula_enable',
    'mineru_table_enable',
    'mineru_page_chunk_enabled',
    'mineru_table_auto_rotate',
  ] as const
  for (const key of mineruBoolKeys) {
    if (key in changed) {
      ;(patch as Record<string, boolean>)[key] = Boolean(changed[key])
    }
  }
  if ('mineru_min_batch_mode' in changed) {
    const mode = String(changed.mineru_min_batch_mode)
    if (mode === 'auto' || mode === 'fixed') patch.mineru_min_batch_mode = mode
  }
  if ('mineru_parse_method' in changed) {
    const method = String(changed.mineru_parse_method)
    if (method === 'auto' || method === 'txt' || method === 'ocr') patch.mineru_parse_method = method
  }
  const mineruIntFields: Array<{ key: keyof SystemSettingsPayload; min: number; max: number }> = [
    { key: 'mineru_min_batch_inference_size', min: 8, max: 384 },
    { key: 'mineru_min_batch_floor', min: 8, max: 384 },
    { key: 'mineru_parse_timeout_sec', min: 60, max: 3600 },
    { key: 'mineru_rpc_timeout_sec', min: 60, max: 7200 },
    { key: 'mineru_page_chunk_threshold', min: 1, max: 2000 },
    { key: 'mineru_page_chunk_pages', min: 8, max: 200 },
    { key: 'mineru_table_rotate_max_tables', min: 1, max: 64 },
    { key: 'mineru_table_rotate_timeout_sec', min: 1, max: 300 },
  ]
  for (const { key, min, max } of mineruIntFields) {
    if (key in changed) {
      const n = Number(changed[key])
      if (!Number.isFinite(n) || n < min || n > max) return {}
      ;(patch as Record<string, number>)[key] = Math.round(n)
    }
  }

  if ('kb_sag_event_extract_enabled' in changed) {
    patch.kb_sag_event_extract_enabled = Boolean(changed.kb_sag_event_extract_enabled)
  }
  if ('kb_multi_repr_enabled' in changed) {
    patch.kb_multi_repr_enabled = Boolean(changed.kb_multi_repr_enabled)
  }
  if ('kb_sag_event_embed_enabled' in changed) {
    patch.kb_sag_event_embed_enabled = Boolean(changed.kb_sag_event_embed_enabled)
  }
  if ('kb_sag_query_llm_enabled' in changed) {
    patch.kb_sag_query_llm_enabled = Boolean(changed.kb_sag_query_llm_enabled)
  }
  if ('kb_sag_event_extract_mode' in changed && changed.kb_sag_event_extract_mode) {
    const mode = String(changed.kb_sag_event_extract_mode)
    if (mode === 'rule' || mode === 'ollama') {
      patch.kb_sag_event_extract_mode = mode
    }
  }
  if ('kb_sag_event_prompt_version' in changed) {
    const n = Number(changed.kb_sag_event_prompt_version)
    if (!Number.isFinite(n) || n < 1 || n > 9999) return {}
    patch.kb_sag_event_prompt_version = Math.round(n)
  }

  return patch
}

function isImmediateField(key: string) {
  return (
    key === 'shared_workspaces_enabled' ||
    key === 'tag_graph_enabled' ||
    key === 'kb_voice_notify_enabled' ||
    key === 'kb_search_hybrid_enabled' ||
    key === 'kb_search_modality_boost_enabled' ||
    key === 'kb_chunk_profile' ||
    key === 'kb_extract_provider' ||
    key === 'kb_pdf_inspector_enabled' ||
    key === 'kb_extract_insavlo_enabled' ||
    key === 'kb_fts_config' ||
    key === 'kb_sag_event_extract_enabled' ||
    key === 'kb_multi_repr_enabled' ||
    key === 'kb_sag_event_embed_enabled' ||
    key === 'kb_sag_query_llm_enabled' ||
    key === 'kb_sag_event_extract_mode' ||
    key === 'kb_raptor_enabled' ||
    key === 'kb_post_async_enabled' ||
    key === 'kb_large_doc_post_enabled' ||
    key === 'kb_large_doc_raptor_enabled' ||
    key === 'kb_ragas_online_eval_enabled' ||
    key === 'clear_kb_ragas_llm_api_key' ||
    key === 'clear_kb_post_llm_api_key' ||
    key === 'clear_ollama_api_key'
  )
}

export default function AdminSettingsPage() {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savedFlash, setSavedFlash] = useState(false)
  const [testingInsavlo, setTestingInsavlo] = useState(false)
  const [testingOllama, setTestingOllama] = useState(false)
  const [activeTab, setActiveTab] = useState<AdminSettingsTabId>(() =>
    resolveAdminSettingsTabFromHash(window.location.hash),
  )
  const tabs = ADMIN_SETTINGS_TAB_BY_ID
  const [form] = Form.useForm<SettingsFormValues>()
  const { message, modal } = App.useApp()
  const hydratedRef = useRef(false)
  const loadedOllamaEmbedDimRef = useRef<number | null>(null)
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const savedFlashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    void (async () => {
      setLoading(true)
      hydratedRef.current = false
      try {
        const res = await getAdminSystemSettings()
        const { values, filledDefault } = withDefaultInsavloCallbackOrigin(res.data)
        form.setFieldsValue(values)
        const dimRaw = values.ollama_embed_dim
        const dimN = typeof dimRaw === 'number' ? dimRaw : Number(dimRaw)
        loadedOllamaEmbedDimRef.current = Number.isFinite(dimN) ? dimN : 1024
        if (filledDefault) {
          await putAdminSystemSettings({
            kb_extract_insavlo_callback_origin: values.kb_extract_insavlo_callback_origin,
          })
          await useSystemSettingsStore.getState().load()
        }
      } finally {
        setLoading(false)
        hydratedRef.current = true
      }
    })()
  }, [form])

  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
      if (savedFlashTimerRef.current) clearTimeout(savedFlashTimerRef.current)
    }
  }, [])

  useEffect(() => {
    const onHashChange = () => {
      setActiveTab(resolveAdminSettingsTabFromHash(window.location.hash))
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const handleTabChange = useCallback((tabId: AdminSettingsTabId) => {
    setActiveTab(tabId)
    const tab = ADMIN_SETTINGS_TAB_BY_ID[tabId]
    const nextHash = `#${tab.hash}`
    if (window.location.hash !== nextHash) {
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${nextHash}`)
    }
  }, [])

  const flashSaved = useCallback(() => {
    setSavedFlash(true)
    if (savedFlashTimerRef.current) clearTimeout(savedFlashTimerRef.current)
    savedFlashTimerRef.current = setTimeout(() => setSavedFlash(false), 2000)
  }, [])

  const confirmEmbedDimChange = useCallback(
    (patch: Partial<SystemSettingsPayload>): Promise<boolean> => {
      if (patch.ollama_embed_dim === undefined) return Promise.resolve(true)
      const next = Number(patch.ollama_embed_dim)
      const prev = loadedOllamaEmbedDimRef.current
      if (prev === null || !Number.isFinite(next) || next === prev) {
        return Promise.resolve(true)
      }
      return new Promise((resolve) => {
        modal.confirm({
          title: t('admin.settings.ollamaEmbedDimWarnTitle'),
          content: t('admin.settings.ollamaEmbedDimWarnContent'),
          okText: t('common.confirm'),
          cancelText: t('common.cancel'),
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        })
      })
    },
    [modal, t],
  )

  const persistPatch = useCallback(
    async (patch: Partial<SystemSettingsPayload>) => {
      if (Object.keys(patch).length === 0) return
      if (!(await confirmEmbedDimChange(patch))) {
        try {
          const res = await getAdminSystemSettings()
          form.setFieldsValue(res.data)
        } catch {
          /* revert failed — keep current form */
        }
        return
      }
      setSaving(true)
      try {
        const res = await putAdminSystemSettings(patch)
        form.setFieldsValue({
          ...res.data,
          clear_kb_post_llm_api_key: false,
          clear_kb_ragas_llm_api_key: false,
          clear_ollama_api_key: false,
        })
        if (res.data.warnings?.length) {
          message.warning(res.data.warnings.join('\n'))
        }
        if (patch.ollama_embed_dim !== undefined) {
          const dimN = Number(patch.ollama_embed_dim)
          if (Number.isFinite(dimN)) loadedOllamaEmbedDimRef.current = dimN
        }
        await useSystemSettingsStore.getState().load()
        window.dispatchEvent(new Event('filex:system-settings-changed'))
        flashSaved()
      } catch (error) {
        try {
          const latest = await getAdminSystemSettings()
          form.setFieldsValue({
            ...latest.data,
            clear_kb_post_llm_api_key: false,
            clear_kb_ragas_llm_api_key: false,
            clear_ollama_api_key: false,
          })
        } catch {
          /* 回滚请求失败时保留原错误，避免掩盖保存失败原因 */
        }
        /* axios 拦截器已提示错误；返回失败，让手动保存按钮不显示成功 */
        return false
      } finally {
        setSaving(false)
      }
    },
    [confirmEmbedDimChange, flashSaved, form, message],
  )

  const handleRaptorEnabledChange = useCallback(
    (enabled: boolean) => {
      if (!enabled) {
        form.setFieldsValue({
          kb_raptor_enabled: false,
          kb_large_doc_raptor_enabled: false,
        })
        void persistPatch({
          kb_raptor_enabled: false,
          kb_large_doc_raptor_enabled: false,
        })
        return
      }
      modal.confirm({
        title: t('admin.settings.kbRaptorEnableWarnTitle'),
        content: t('admin.settings.kbRaptorEnableWarnContent'),
        okText: t('admin.settings.kbRaptorEnableWarnOk'),
        cancelText: t('common.cancel'),
        okButtonProps: { danger: true },
        onOk: () => {
          form.setFieldValue('kb_raptor_enabled', true)
          void persistPatch({ kb_raptor_enabled: true })
        },
      })
    },
    [form, modal, persistPatch, t],
  )

  const scheduleSave = useCallback(
    (changed: Partial<SettingsFormValues>, immediate = false) => {
      if (!hydratedRef.current) return

      const run = () => {
        const patch = patchFromChanged(changed, form.getFieldsValue(true))
        void persistPatch(patch)
      }

      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current)
        saveTimerRef.current = null
      }

      if (immediate) {
        run()
        return
      }

      saveTimerRef.current = setTimeout(run, SAVE_DEBOUNCE_MS)
    },
    [form, persistPatch],
  )

  const onValuesChange = useCallback(
    (changed: Partial<SettingsFormValues>) => {
      if ('kb_raptor_enabled' in changed) return
      const keys = Object.keys(changed)
      if (keys.length === 0) return
      scheduleSave(changed, keys.every(isImmediateField))
    },
    [scheduleSave],
  )

  const statusHint = saving
    ? t('admin.settings.saving')
    : savedFlash
      ? t('admin.settings.autoSaved')
      : t('admin.settings.autoSaveHint')
  const insavloReady = Form.useWatch('kb_extract_insavlo_ready', form) ?? false
  const insavloCallbackOrigin = Form.useWatch('kb_extract_insavlo_callback_origin', form) ?? ''
  const insavloCallbackUrl = insavloCallbackOrigin
    ? `${String(insavloCallbackOrigin).replace(/\/$/, '')}/api/webhooks/insavlo/document-process`
    : '/api/webhooks/insavlo/document-process'
  const pipelineJson = Form.useWatch('kb_ingestion_pipeline_json', form) ?? ''
  const builtinRoutes = Form.useWatch('builtin_routes', form) ?? []
  const globalExtractProvider = Form.useWatch('kb_extract_provider', form) ?? 'legacy'
  const kbRaptorEnabled = Form.useWatch('kb_raptor_enabled', form) ?? false

  const insavloHelpStatus = insavloReady
    ? t('admin.settings.insavloReady')
    : t('admin.settings.insavloNotReady')
  const insavloHelpText = `${insavloHelpStatus}\n${t('admin.settings.insavloNoFallbackHint')}`

  const testInsavlo = useCallback(async () => {
    setTestingInsavlo(true)
    try {
      const res = await testAdminInsavloSettings()
      if (res.data.ok) {
        message.success(res.data.message)
      } else {
        message.warning(res.data.errors.join('；') || res.data.message)
      }
      const latest = await getAdminSystemSettings()
      form.setFieldsValue(latest.data)
      await useSystemSettingsStore.getState().load()
    } finally {
      setTestingInsavlo(false)
    }
  }, [form, message])

  const testOllama = useCallback(async () => {
    setTestingOllama(true)
    try {
      const res = await testAdminOllamaSettings()
      if (res.data.ok) {
        message.success(res.data.message)
      } else {
        const detail = [res.data.errors.join('；') || res.data.message]
        if (res.data.compose_network_hint) {
          detail.push(res.data.compose_network_hint)
        } else if (
          !res.data.ok &&
          res.data.base_url.includes('filex-ollama') &&
          res.data.errors.some((e) => e.includes('连接失败'))
        ) {
          detail.push(t('admin.settings.ollamaComposeNetworkHint'))
        }
        message.warning(detail.filter(Boolean).join(' '))
      }
    } finally {
      setTestingOllama(false)
    }
  }, [message, t])

  return (
    <div className="admin-root">
      <div className="admin-panel admin-panel--settings">
        <div className="admin-header admin-header--compact">
          <div className="ah-title-group">
            <h2 className="ah-title">{t('admin.settings.title')}</h2>
            <span className={`ah-sub${saving ? ' ah-sub--saving' : savedFlash ? ' ah-sub--saved' : ''}`}>
              {statusHint}
            </span>
          </div>
        </div>
        <Spin spinning={loading} wrapperClassName="admin-settings-spin">
          <div className="admin-settings-body">
            <div className="admin-settings-split">
              <AdminSettingsTabNav activeTabId={activeTab} onTabChange={handleTabChange} />
              <div className="admin-settings-main">
            <div className="admin-settings-tab-panels">
              <AdminSettingsTabPanel tab={tabs.license} activeTabId={activeTab}>
                <SettingsSection
                  variant="flat"
                  id={tabs.license.sectionId}
                  title={t(tabs.license.labelKey)}
                  description={t(tabs.license.descKey)}
                >
                  <AdminLicenseSection embedded />
                </SettingsSection>
              </AdminSettingsTabPanel>
            <Form
              form={form}
              component={false}
              layout="vertical"
              size="small"
              initialValues={{
                clipboard_prefix: '',
                clipboard_suffix: '',
                agent_skill_install_prompt: '',
                tag_graph_single_node_symbol_size: 48,
                tag_graph_edge_line_width: 1,
                tag_graph_node_display_ratio: 1,
                tag_graph_enabled: true,
                max_upload_size_mb: 10,
                workspace_backup_max_mb: 100,
                agent_run_retention_days: 30,
                kb_index_max_attempts: 3,
                kb_post_async_enabled: true,
                kb_post_max_attempts: 3,
                shared_workspaces_enabled: true,
                kb_search_hybrid_enabled: true,
                kb_chunk_profile: 'long_doc',
                kb_chunk_size: null,
                kb_chunk_overlap: null,
                kb_chunk_split_recursive: false,
                kb_embed_cache_enabled: true,
                kb_embed_effective_max_chars: 8192,
                // T-4 defaults (will be overridden by server response)
                kb_large_doc_char_threshold: 400000,
                kb_large_doc_chunk_size: 1800,
                kb_large_doc_chunk_overlap: 150,
                kb_large_doc_post_enabled: false,
                kb_large_doc_raptor_enabled: false,
                kb_raptor_enabled: false,
                kb_raptor_min_chars: 30000,
                ollama_api_key: '',
                ollama_has_api_key: false,
                clear_ollama_api_key: false,
                kb_post_llm_provider: 'ollama',
                kb_post_llm_base_url: '',
                kb_post_llm_api_key: '',
                kb_post_llm_has_api_key: false,
                kb_post_llm_model: '',
                kb_post_llm_timeout_sec: 60,
                kb_post_llm_json_mode: 'auto',
                clear_kb_post_llm_api_key: false,
                kb_extract_provider: 'legacy',
                kb_pdf_inspector_enabled: false,
                kb_ingestion_pipeline_json: '',
                kb_search_min_score: 0.35,
                kb_search_boost_keyword_bonus: 0.12,
                kb_search_mmr_lambda: 0.7,
                kb_search_filename_boost: 0.2,
                kb_search_modality_boost: 0.15,
                kb_search_modality_boost_enabled: false,
                kb_search_default_top_k: 8,
                kb_fts_config: 'zh_cn',
                kb_wiki_compile_min_sources: 2,
                kb_voice_notify_enabled: true,
                kb_voice_notify_playback_ttl_seconds: 120,
                kb_extract_insavlo_enabled: false,
                kb_extract_insavlo_base_url: 'https://demo.insavlo.com/insavlo/public-api',
                kb_extract_insavlo_skill_code: '',
                kb_extract_insavlo_callback_origin: '',
                kb_extract_insavlo_timeout_minutes: 120,
                kb_extract_insavlo_api_key: '',
                kb_extract_insavlo_has_api_key: false,
                kb_extract_insavlo_webhook_secret: '',
                kb_extract_insavlo_has_webhook_secret: false,
                kb_extract_insavlo_ready: false,
                kb_sag_event_extract_enabled: false,
                kb_sag_event_extract_mode: 'rule',
                kb_sag_event_prompt_version: 1,
                kb_sag_event_embed_enabled: false,
                kb_sag_query_llm_enabled: false,
                kb_multi_repr_enabled: false,  // 154
                kb_ragas_online_eval_enabled: false,
                kb_ragas_online_eval_sample_rate: 1,
                kb_ragas_online_eval_timeout_seconds: 600,
                kb_ragas_llm_provider: 'ollama',
                kb_ragas_llm_base_url: '',
                kb_ragas_llm_api_key: '',
                kb_ragas_llm_has_api_key: false,
                kb_ragas_llm_model: '',
                kb_ragas_llm_timeout_seconds: 90,
                kb_ragas_eval_concurrency: 1,
                kb_ragas_eval_context_max_count: 8,
                kb_ragas_eval_context_max_chars_per_item: 1200,
                kb_ragas_eval_context_max_total_chars: 10000,
                clear_kb_ragas_llm_api_key: false,
              }}
              onValuesChange={onValuesChange}
            >
              <div className="admin-settings-form">
              <AdminSettingsTabPanel tab={tabs.clipboard} activeTabId={activeTab}>
                <SettingsSection
                  variant="flat"
                  id={tabs.clipboard.sectionId}
                  title={t(tabs.clipboard.labelKey)}
                  description={t(tabs.clipboard.descKey)}
                >
                  <Row gutter={[12, 0]}>
                    <Col xs={24} md={12}>
                      <Form.Item
                        name="clipboard_prefix"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.prefix')}
                            help="剪贴板前缀内容。复制文件或内容时会自动添加在此之前。"
                          />
                        }
                      >
                        <Input.TextArea rows={12} placeholder={t('admin.settings.prefixHint')} />
                      </Form.Item>
                    </Col>
                    <Col xs={24} md={12}>
                      <Form.Item
                        name="clipboard_suffix"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.suffix')}
                            help="剪贴板后缀内容。复制文件或内容时会自动添加在此之后。"
                          />
                        }
                      >
                        <Input.TextArea rows={12} placeholder={t('admin.settings.suffixHint')} />
                      </Form.Item>
                    </Col>
                  </Row>
                </SettingsSection>
                </AdminSettingsTabPanel>


                <AdminSettingsTabPanel tab={tabs.agentSkillInstall} activeTabId={activeTab}>
                <SettingsSection
                  variant="flat"
                  id={tabs.agentSkillInstall.sectionId}
                  title={t(tabs.agentSkillInstall.labelKey)}
                  description={t(tabs.agentSkillInstall.descKey)}
                >
                  <Form.Item
                    name="agent_skill_install_prompt"
                    label={
                      <StatLabelWithHelp
                        label={t('admin.settings.agentSkillInstallPrompt')}
                        help={t('admin.settings.agentSkillInstallPromptHint')}
                      />
                    }
                  >
                    <Input.TextArea rows={20} />
                  </Form.Item>
                </SettingsSection>
                </AdminSettingsTabPanel>

                <AdminSettingsTabPanel tab={tabs.workspace} activeTabId={activeTab}>
                <SettingsSection
                  variant="flat"
                  id={tabs.workspace.sectionId}
                  title={t(tabs.workspace.labelKey)}
                  description={t(tabs.workspace.descKey)}
                >
                  <Row gutter={[12, 0]} className="admin-settings-row--compact">
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="shared_workspaces_enabled"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.sharedWorkspacesEnabled')}
                            help="开启后支持创建共享工作空间，允许其他用户加入并共同管理文件。"
                          />
                        }
                        extra={t('admin.settings.sharedWorkspacesEnabledHint')}
                        valuePropName="checked"
                      >
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="max_upload_size_mb"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.maxUploadSizeMb')}
                            help="单个文件上传大小上限（MB）。超过此限制的上传会被拒绝。"
                          />
                        }
                        extra={t('admin.settings.maxUploadSizeMbHint')}
                      >
                        <InputNumber min={1} max={10240} step={1} precision={0} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="workspace_backup_max_mb"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.workspaceBackupMaxMb')}
                            help="个人空间备份的最大允许体积（MB），用于限制导出/备份占用。"
                          />
                        }
                        extra={t('admin.settings.workspaceBackupMaxMbHint')}
                      >
                        <InputNumber min={1} max={10240} step={1} precision={0} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="agent_run_retention_days"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.agentRunRetentionDays')}
                            help="智能体运行记录与事件的保留天数，到期后启动时自动删除。"
                          />
                        }
                        extra={t('admin.settings.agentRunRetentionDaysHint')}
                      >
                        <InputNumber min={1} max={365} step={1} precision={0} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                  </Row>
                </SettingsSection>
                </AdminSettingsTabPanel>

                <AdminSettingsTabPanel tab={tabs.tagGraph} activeTabId={activeTab}>
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
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.tagGraphEnabled')}
                            help="是否启用标签关系图（Tag Graph）。关闭后相关可视化与分析功能将不可用。"
                          />
                        }
                        extra={t('admin.settings.tagGraphEnabledHint')}
                        valuePropName="checked"
                      >
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="tag_graph_single_node_symbol_size"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.tagGraphSingleNodeSymbolSize')}
                            help="标签图中单个节点的符号大小（像素）。影响图谱的视觉密度。"
                          />
                        }
                        extra={t('admin.settings.tagGraphSingleNodeSymbolSizeHint')}
                      >
                        <InputNumber min={8} max={160} step={1} precision={0} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="tag_graph_edge_line_width"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.tagGraphEdgeLineWidth')}
                            help="标签图中关系边的线宽。数值越大，边越粗。"
                          />
                        }
                        extra={t('admin.settings.tagGraphEdgeLineWidthHint')}
                      >
                        <InputNumber min={1} max={12} step={1} precision={0} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="tag_graph_node_display_ratio"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.tagGraphNodeDisplayRatio')}
                            help="节点显示比例因子。控制整体节点大小的缩放。"
                          />
                        }
                        extra={t('admin.settings.tagGraphNodeDisplayRatioHint')}
                      >
                        <InputNumber min={0.1} max={5} step={0.1} precision={1} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                  </Row>
                </SettingsSection>
                </AdminSettingsTabPanel>

                <AdminSettingsTabPanel tab={tabs.kbPipeline} activeTabId={activeTab}>
                <SettingsSection
                  variant="flat"
                  id={tabs.kbPipeline.sectionId}
                  title={t(tabs.kbPipeline.labelKey)}
                  description={t(tabs.kbPipeline.descKey)}
                >
                  <Form.Item name="kb_ingestion_pipeline_json" hidden>
                    <Input />
                  </Form.Item>
                  <AdminKbPipelineSettingsTabs
                    insavloReady={insavloReady}
                    pipelineJson={pipelineJson}
                    globalExtractProvider={globalExtractProvider}
                    builtinRoutes={builtinRoutes}
                    insavloCallbackUrl={insavloCallbackUrl}
                    insavloHelpStatus={insavloHelpStatus}
                    insavloHelpText={insavloHelpText}
                    testingInsavlo={testingInsavlo}
                    onTestInsavlo={() => void testInsavlo()}
                    onPipelineSave={async (json) => {
                      form.setFieldValue('kb_ingestion_pipeline_json', json)
                      const saved = await persistPatch({ kb_ingestion_pipeline_json: json })
                      if (saved === false) throw new Error('系统参数保存失败')
                    }}
                  />
                </SettingsSection>
                </AdminSettingsTabPanel>

                <AdminSettingsTabPanel tab={tabs.ollama} activeTabId={activeTab}>
                <SettingsSection
                  variant="flat"
                  id={tabs.ollama.sectionId}
                  title={t(tabs.ollama.labelKey)}
                  description={t(tabs.ollama.descKey)}
                >
                  <AdminOllamaSettingsTabs
                    testingOllama={testingOllama}
                    onTestOllama={testOllama}
                    kbRaptorEnabled={kbRaptorEnabled}
                    onRaptorEnabledChange={handleRaptorEnabledChange}
                  />
                </SettingsSection>
                </AdminSettingsTabPanel>

                <AdminSettingsTabPanel tab={tabs.kbSag} activeTabId={activeTab}>
                <SettingsSection
                  variant="flat"
                  id={tabs.kbSag.sectionId}
                  title={t(tabs.kbSag.labelKey)}
                  description={t(tabs.kbSag.descKey)}
                >
                  <Row gutter={[12, 0]}>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_sag_event_extract_enabled"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbSagEventExtractEnabled')}
                            help="是否启用语义事件抽取（SAG）。开启后会为文档构建事件图谱。"
                          />
                        }
                        extra={t('admin.settings.kbSagEventExtractEnabledHint')}
                        valuePropName="checked"
                      >
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_sag_event_extract_mode"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbSagEventExtractMode')}
                            help="事件抽取模式：rule 为规则驱动，ollama 为大模型驱动（更智能但更慢）。"
                          />
                        }
                        extra={t('admin.settings.kbSagEventExtractModeHint')}
                      >
                        <Select
                          options={[
                            { value: 'rule', label: t('admin.settings.kbSagEventExtractModeRule') },
                            { value: 'ollama', label: t('admin.settings.kbSagEventExtractModeOllama') },
                          ]}
                        />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_sag_event_prompt_version"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbSagEventPromptVersion')}
                            help="使用的大模型 Prompt 版本号。升级 Prompt 版本可获得更好的抽取效果。"
                          />
                        }
                        extra={t('admin.settings.kbSagEventPromptVersionHint')}
                      >
                        <InputNumber min={1} max={9999} step={1} precision={0} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_sag_event_embed_enabled"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbSagEventEmbedEnabled')}
                            help="是否为抽取的事件生成向量嵌入，用于事件级语义检索。"
                          />
                        }
                        extra={t('admin.settings.kbSagEventEmbedEnabledHint')}
                        valuePropName="checked"
                      >
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_sag_query_llm_enabled"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbSagQueryLlmEnabled')}
                            help="在 SAG 查询时是否使用大模型进行语义增强或重写。开启会更智能但增加延迟和成本。"
                          />
                        }
                        extra={t('admin.settings.kbSagQueryLlmEnabledHint')}
                        valuePropName="checked"
                      >
                        <Switch />
                      </Form.Item>
                    </Col>
                  </Row>
                </SettingsSection>
                </AdminSettingsTabPanel>

                <AdminSettingsTabPanel tab={tabs.kbSearch} activeTabId={activeTab}>
                <SettingsSection
                  variant="flat"
                  id={tabs.kbSearch.sectionId}
                  title={t(tabs.kbSearch.labelKey)}
                  description={t(tabs.kbSearch.descKey)}
                >
                  <Row gutter={[12, 0]}>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_multi_repr_enabled"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbMultiReprEnabled')}
                            help="是否启用 146 P2 多表征增强检索。开启后，搜索结果会合并 event_summary + raptor_summary 多表征命中。默认关闭以保持 146 P-146-01 向后兼容。"
                          />
                        }
                        extra={t('admin.settings.kbMultiReprEnabledHint')}
                        valuePropName="checked"
                      >
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_search_hybrid_enabled"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbSearchHybridEnabled')}
                            help="是否启用混合检索（向量 + 全文）。推荐开启，可显著提升召回质量。"
                          />
                        }
                        extra={t('admin.settings.kbSearchHybridEnabledHint')}
                        valuePropName="checked"
                      >
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_fts_config"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbFtsConfig')}
                            help="全文检索分词配置。zh_cn 使用中文分词器，simple 使用简单空格分词。"
                          />
                        }
                        extra={t('admin.settings.kbFtsConfigHint')}
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
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbSearchMinScore')}
                            help="向量检索的最低相似度分数。低于此分数的向量结果将被过滤。"
                          />
                        }
                        extra={t('admin.settings.kbSearchMinScoreHint')}
                      >
                        <InputNumber min={0} max={1} step={0.05} precision={2} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_search_boost_keyword_bonus"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbSearchBoostKeywordBonus')}
                            help="关键词命中时的额外加分。用于提升精确匹配的重要性。"
                          />
                        }
                        extra={t('admin.settings.kbSearchBoostKeywordBonusHint')}
                      >
                        <InputNumber min={0} max={0.5} step={0.01} precision={2} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_search_mmr_lambda"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbSearchMmrLambda')}
                            help="MMR 多样性参数。0 更注重相关性，1 更注重结果多样性。"
                          />
                        }
                        extra={t('admin.settings.kbSearchMmrLambdaHint')}
                      >
                        <InputNumber min={0} max={1} step={0.05} precision={2} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_search_filename_boost"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbSearchFilenameBoost')}
                            help="文件名匹配时的加分权重。提高此值可让文件名命中结果排得更前。"
                          />
                        }
                        extra={t('admin.settings.kbSearchFilenameBoostHint')}
                      >
                        <InputNumber min={0} max={0.5} step={0.05} precision={2} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_search_modality_boost_enabled"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbSearchModalityBoostEnabled')}
                            help="是否根据内容类型（文本、表格、图片等）给予不同加分。"
                          />
                        }
                        extra={t('admin.settings.kbSearchModalityBoostEnabledHint')}
                        valuePropName="checked"
                      >
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_search_modality_boost"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbSearchModalityBoost')}
                            help="不同模态内容的基础加分幅度。"
                          />
                        }
                        extra={t('admin.settings.kbSearchModalityBoostHint')}
                      >
                        <InputNumber min={0} max={0.5} step={0.05} precision={2} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_search_default_top_k"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbSearchDefaultTopK')}
                            help="默认返回的检索结果数量。影响召回和后续处理量。"
                          />
                        }
                        extra={t('admin.settings.kbSearchDefaultTopKHint')}
                      >
                        <InputNumber min={5} max={50} step={1} precision={0} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                  </Row>
                </SettingsSection>
                </AdminSettingsTabPanel>

                <AdminSettingsTabPanel tab={tabs.wiki} activeTabId={activeTab}>
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
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbWikiCompileMinSources')}
                            help="生成 Wiki 页面时至少需要多少个来源片段。数值越高，Wiki 质量要求越严格。"
                          />
                        }
                        extra={t('admin.settings.kbWikiCompileMinSourcesHint')}
                      >
                        <InputNumber min={1} max={20} step={1} precision={0} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                  </Row>
                </SettingsSection>
                </AdminSettingsTabPanel>

                <AdminSettingsTabPanel tab={tabs.ragasEval} activeTabId={activeTab}>
                <SettingsSection
                  variant="flat"
                  id={tabs.ragasEval.sectionId}
                  title={t(tabs.ragasEval.labelKey)}
                  description={t(tabs.ragasEval.descKey)}
                >
                  <Row gutter={[12, 0]}>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_ragas_online_eval_enabled"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbRagasEvalEnabled')}
                            help={t('admin.settings.kbRagasEvalEnabledHint')}
                          />
                        }
                        valuePropName="checked"
                      >
                        <Switch />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_ragas_online_eval_sample_rate"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbRagasEvalSampleRate')}
                            help={t('admin.settings.kbRagasEvalSampleRateHint')}
                          />
                        }
                        extra={t('admin.settings.kbRagasEvalSampleRateExtra')}
                      >
                        <InputNumber min={0} max={1} step={0.1} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item
                        name="kb_ragas_online_eval_timeout_seconds"
                        label={
                          <StatLabelWithHelp
                            label={t('admin.settings.kbRagasEvalTimeout')}
                            help={t('admin.settings.kbRagasEvalTimeoutHint')}
                          />
                        }
                        extra={t('admin.settings.kbRagasEvalTimeoutExtra')}
                      >
                        <InputNumber min={10} max={3000} step={1} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                  </Row>
                  <Divider orientation="left">{t('admin.settings.kbRagasEvalLlmSection')}</Divider>
                  <Row gutter={[12, 0]}>
                    <Col xs={24} sm={12}>
                      <Form.Item name="kb_ragas_llm_provider" label={t('admin.settings.kbRagasLlmProvider')}>
                        <Select options={[
                          { value: 'ollama', label: t('admin.settings.kbRagasLlmProviderOllama') },
                          { value: 'openai_compatible', label: t('admin.settings.kbRagasLlmProviderOpenAI') },
                        ]} />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item name="kb_ragas_llm_base_url" label={t('admin.settings.kbRagasLlmBaseUrl')}>
                        <Input placeholder="https://api.example.com/v1" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item name="kb_ragas_llm_model" label={t('admin.settings.kbRagasLlmModel')}>
                        <Input placeholder="deepseek-chat" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item name="kb_ragas_llm_timeout_seconds" label={t('admin.settings.kbRagasLlmTimeoutSeconds')}>
                        <InputNumber min={10} max={300} step={1} precision={0} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item name="kb_ragas_llm_api_key" label={t('admin.settings.kbRagasLlmApiKey')} extra={t('admin.settings.kbRagasLlmApiKeyHint')}>
                        <Input.Password autoComplete="new-password" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item shouldUpdate noStyle>
                        {({ getFieldValue }) =>
                          getFieldValue('kb_ragas_llm_has_api_key') ? (
                            <Form.Item
                              name="clear_kb_ragas_llm_api_key"
                              label={t('admin.settings.kbRagasLlmClearApiKey')}
                              valuePropName="checked"
                            >
                              <Switch />
                            </Form.Item>
                          ) : null
                        }
                      </Form.Item>
                    </Col>
                  </Row>
                  <Divider orientation="left">{t('admin.settings.kbRagasEvalContextBudgetSection')}</Divider>
                  <Row gutter={[12, 0]}>
                    <Col xs={24} sm={12}>
                      <Form.Item name="kb_ragas_eval_concurrency" label={t('admin.settings.kbRagasEvalConcurrency')}>
                        <InputNumber min={1} max={4} step={1} precision={0} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item name="kb_ragas_eval_context_max_count" label={t('admin.settings.kbRagasEvalContextMaxCount')}>
                        <InputNumber min={1} max={20} step={1} precision={0} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item name="kb_ragas_eval_context_max_chars_per_item" label={t('admin.settings.kbRagasEvalContextMaxCharsPerItem')}>
                        <InputNumber min={200} max={4000} step={100} precision={0} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                    <Col xs={24} sm={12}>
                      <Form.Item name="kb_ragas_eval_context_max_total_chars" label={t('admin.settings.kbRagasEvalContextMaxTotalChars')}>
                        <InputNumber min={1000} max={40000} step={1000} precision={0} className="admin-settings-number" />
                      </Form.Item>
                    </Col>
                  </Row>
                </SettingsSection>
                </AdminSettingsTabPanel>
              </div>
            </Form>
            </div>
              </div>
            </div>
          </div>
        </Spin>
      </div>
    </div>
  )
}
