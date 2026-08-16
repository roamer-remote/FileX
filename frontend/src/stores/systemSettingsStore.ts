import { create } from 'zustand'
import { getClipboardSettings } from '@/api/settings'
import type { ClipboardSettings } from '@/api/settings'

type State = ClipboardSettings & {
  loaded: boolean
  /** 每次 load 成功递增，供标签图等组件侦听系统参数变更 */
  revision: number
  load: () => Promise<void>
}

const defaults: ClipboardSettings = {
  clipboard_prefix: '',
  clipboard_suffix: '',
  tag_graph_single_node_symbol_size: 48,
  tag_graph_node_display_ratio: 1,
  tag_graph_edge_line_width: 1,
  tag_graph_enabled: true,
  max_upload_size_mb: 10,
  shared_workspaces_enabled: true,
  kb_extract_provider: 'legacy',
  kb_extract_insavlo_ready: false,
  kb_search_default_top_k: 8,
  kb_voice_notify_enabled: true,
  kb_voice_notify_playback_ttl_seconds: 120,
  kb_sag_event_extract_enabled: false,
}

export const useSystemSettingsStore = create<State>((set, get) => ({
  ...defaults,
  loaded: false,
  revision: 0,
  load: async () => {
    const res = await getClipboardSettings()
    const raw = res.data.tag_graph_single_node_symbol_size
    const n = typeof raw === 'number' ? raw : Number(raw)
    const tag_graph_single_node_symbol_size =
      Number.isFinite(n) && n >= 8 && n <= 160 ? n : 48
    const rawEdge = res.data.tag_graph_edge_line_width
    const edgeN = typeof rawEdge === 'number' ? rawEdge : Number(rawEdge)
    const tag_graph_edge_line_width =
      Number.isFinite(edgeN) && edgeN >= 1 && edgeN <= 12 ? Math.round(edgeN) : 1
    const rawRatio = res.data.tag_graph_node_display_ratio
    const ratioN = typeof rawRatio === 'number' ? rawRatio : Number(rawRatio)
    const tag_graph_node_display_ratio =
      Number.isFinite(ratioN) && ratioN >= 0.1 && ratioN <= 5 ? Math.round(ratioN * 100) / 100 : 1
    const rawMb = res.data.max_upload_size_mb
    const mb = typeof rawMb === 'number' ? rawMb : Number(rawMb)
    const max_upload_size_mb = Number.isFinite(mb) && mb >= 1 && mb <= 10240 ? Math.round(mb) : 10
    const rawShared = res.data.shared_workspaces_enabled
    const shared_workspaces_enabled =
      rawShared === undefined || rawShared === null
        ? true
        : rawShared === true || String(rawShared).toLowerCase() === 'true'
    const rawTagGraph = res.data.tag_graph_enabled
    const tag_graph_enabled =
      rawTagGraph === undefined || rawTagGraph === null
        ? true
        : rawTagGraph === true || String(rawTagGraph).toLowerCase() === 'true'
    const rawTopK = res.data.kb_search_default_top_k
    const topKNum = typeof rawTopK === 'number' ? rawTopK : Number(rawTopK)
    const kb_search_default_top_k =
      Number.isFinite(topKNum) && topKNum >= 5 && topKNum <= 50 ? Math.round(topKNum) : 8
    const rawProvider = res.data.kb_extract_provider
    const kb_extract_provider =
      typeof rawProvider === 'string' && rawProvider.trim()
        ? rawProvider.trim().toLowerCase()
        : 'legacy'
    const rawInsavloReady = res.data.kb_extract_insavlo_ready
    const kb_extract_insavlo_ready =
      rawInsavloReady === true || String(rawInsavloReady).toLowerCase() === 'true'
    const rawVoiceNotify = res.data.kb_voice_notify_enabled
    const kb_voice_notify_enabled =
      rawVoiceNotify === undefined || rawVoiceNotify === null
        ? true
        : rawVoiceNotify === true || String(rawVoiceNotify).toLowerCase() === 'true'
    const rawPlaybackTtl = res.data.kb_voice_notify_playback_ttl_seconds
    const playbackTtlNum = typeof rawPlaybackTtl === 'number' ? rawPlaybackTtl : Number(rawPlaybackTtl)
    const kb_voice_notify_playback_ttl_seconds =
      Number.isFinite(playbackTtlNum) && playbackTtlNum >= 1 && playbackTtlNum <= 3600
        ? Math.round(playbackTtlNum)
        : 120
    const rawSagExtract = res.data.kb_sag_event_extract_enabled
    const kb_sag_event_extract_enabled =
      rawSagExtract === undefined || rawSagExtract === null
        ? false
        : rawSagExtract === true || String(rawSagExtract).toLowerCase() === 'true'
    set({
      ...res.data,
      kb_extract_provider,
      kb_extract_insavlo_ready,
      tag_graph_single_node_symbol_size,
      tag_graph_node_display_ratio,
      tag_graph_edge_line_width,
      max_upload_size_mb,
      shared_workspaces_enabled,
      tag_graph_enabled,
      kb_search_default_top_k,
      kb_voice_notify_enabled,
      kb_voice_notify_playback_ttl_seconds,
      kb_sag_event_extract_enabled,
      loaded: true,
      revision: get().revision + 1,
    })
  },
}))
