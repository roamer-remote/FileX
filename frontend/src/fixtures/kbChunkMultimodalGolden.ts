import type { KbChunkDetail } from '@/api/knowledgeBase'

/** SC-047-009 golden：figure / table chunk 列表 API 形态（合成数据） */
export const GOLDEN_FIGURE_CHUNK: Pick<
  KbChunkDetail,
  'content_kind' | 'content_meta' | 'loc_label' | 'text' | 'heading_path'
> = {
  content_kind: 'figure',
  content_meta: {
    page_idx: 1,
    asset_key: 'fig1.jpg',
    caption: '示意图',
  },
  loc_label: 'p.2',
  heading_path: '第三章 · 架构',
  text: '【report.pdf】\n\n![示意图](.extract_assets/9/fig1.jpg)',
}

export const GOLDEN_TABLE_CHUNK: Pick<
  KbChunkDetail,
  'content_kind' | 'content_meta' | 'loc_label' | 'text' | 'heading_path'
> = {
  content_kind: 'table',
  content_meta: {
    page_idx: 0,
    caption: '销售汇总',
  },
  loc_label: 'p.1',
  heading_path: '附录',
  text: '| 区域 | 销售额 |\n| --- | --- |\n| 华东 | 1200 |',
}

export const GOLDEN_FIGURE_META_SUMMARY = 'p1 · 示意图 · fig1.jpg'
export const GOLDEN_TABLE_META_SUMMARY = 'p0 · 销售汇总'
