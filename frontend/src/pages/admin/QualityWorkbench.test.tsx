import { App as AntdApp } from 'antd'
import { useEffect } from 'react'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act } from 'react-dom/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import i18n from '@/i18n'
import QualityWorkbenchPage, { safeQualityData } from './QualityWorkbench'

const qualityWorkbenchStyles = readFileSync(resolve(process.cwd(), 'src/pages/admin/QualityWorkbench.css'), 'utf8')

const {
  getQualityWorkbenchMock,
  getQualityWorkbenchOptionsMock,
  listKnowledgeBaseFileChunksMock,
  patchKnowledgeBaseChunkMock,
  searchKnowledgeBaseMock,
} = vi.hoisted(() => ({
  getQualityWorkbenchMock: vi.fn(),
  getQualityWorkbenchOptionsMock: vi.fn(),
  listKnowledgeBaseFileChunksMock: vi.fn(),
  patchKnowledgeBaseChunkMock: vi.fn(),
  searchKnowledgeBaseMock: vi.fn(),
}))

vi.mock('@/api/knowledgeBase', async () => {
  const actual = await vi.importActual<typeof import('@/api/knowledgeBase')>('@/api/knowledgeBase')
  return {
    ...actual,
    getQualityWorkbench: getQualityWorkbenchMock,
    getQualityWorkbenchOptions: getQualityWorkbenchOptionsMock,
    listKnowledgeBaseFileChunks: listKnowledgeBaseFileChunksMock,
    patchKnowledgeBaseChunk: patchKnowledgeBaseChunkMock,
    searchKnowledgeBase: searchKnowledgeBaseMock,
  }
})

describe('QualityWorkbenchPage', () => {
  let container: HTMLDivElement | null = null

  it('keeps long workbench content in a scrollable body', () => {
    expect(qualityWorkbenchStyles).toMatch(/\.quality-workbench-body\s*\{[^}]*overflow-y:\s*auto/s)
  })

  beforeEach(() => {
    listKnowledgeBaseFileChunksMock.mockResolvedValue({ items: [] })
  })

  afterEach(() => {
    container?.remove()
    container = null
    vi.clearAllMocks()
  })

  it('shows an explicit empty scope state before a file is selected', async () => {
    container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={['/admin/knowledge-base/quality-workbench']}>
          <I18nextProvider i18n={i18n}>
            <AntdApp><QualityWorkbenchPage /></AntdApp>
          </I18nextProvider>
        </MemoryRouter>,
      )
    })
    expect(container.textContent).toContain('请输入资料 ID')
    expect(container.textContent).toContain('RAG 质量工作台')
    await act(async () => {
      root.unmount()
    })
  })

  it('loads file-scoped extraction jobs for dependent task and trace selectors', async () => {
    getQualityWorkbenchMock.mockResolvedValue({
      schema_version: '187.1',
      correlation: {
        file_id: 358,
        job_id: null,
        trace_id: null,
        query_hash: null,
        request_scope_id: 'scope-1',
        versions: {},
      },
      extraction: { state: 'missing' },
      retrieval: { state: 'missing' },
      evidence: { state: 'missing' },
      answer: { state: 'missing' },
      failures: [],
      truncated: false,
      truncated_sections: [],
    })
    getQualityWorkbenchOptionsMock.mockResolvedValue({
      schema_version: '187.1',
      file_id: 358,
      jobs: [
        {
          job_id: 1069,
          status: 'done',
          provider: 'mineru',
          traces: [
            {
              trace_id: 'a'.repeat(32),
              status: 'completed',
              query_hash: 'b'.repeat(16),
              created_at: '2026-08-14T10:00:00Z',
              finished_at: '2026-08-14T10:00:01Z',
            },
          ],
        },
      ],
    })
    container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={['/admin/knowledge-base/quality-workbench?file_id=358']}>
          <I18nextProvider i18n={i18n}>
            <AntdApp><QualityWorkbenchPage /></AntdApp>
          </I18nextProvider>
        </MemoryRouter>,
      )
      await new Promise((resolve) => setTimeout(resolve, 50))
    })
    expect(getQualityWorkbenchOptionsMock).toHaveBeenCalledWith(358)
    const jobSelect = container.querySelector('[aria-label="任务 ID"]') as HTMLElement | null
    const traceSelect = container.querySelector('[aria-label="Trace ID"]') as HTMLElement | null
    expect(jobSelect).not.toBeNull()
    expect(traceSelect).not.toBeNull()
    expect(traceSelect?.classList.contains('ant-select-disabled')).toBe(true)

    await act(async () => {
      const selector = jobSelect?.querySelector('.ant-select-selector') as HTMLElement | null
      selector?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await Promise.resolve()
    })
    const jobOption = Array.from(document.body.querySelectorAll('.ant-select-item-option-content')).find((node) =>
      node.textContent?.includes('#1069'),
    ) as HTMLElement | undefined
    expect(jobOption).not.toBeUndefined()
    await act(async () => {
      jobOption?.click()
      await new Promise((resolve) => setTimeout(resolve, 0))
    })

    await act(async () => {
      const selector = traceSelect?.querySelector('.ant-select-selector') as HTMLElement | null
      selector?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    const traceId = 'a'.repeat(32)
    const traceOption = Array.from(document.body.querySelectorAll('.ant-select-item-option-content')).find((node) =>
      node.textContent?.includes(traceId),
    ) as HTMLElement | undefined
    expect(traceOption).not.toBeUndefined()
    await act(async () => {
      traceOption?.click()
      await Promise.resolve()
    })

    const loadButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('加载'),
    ) as HTMLButtonElement | undefined
    await act(async () => {
      loadButton?.click()
      await Promise.resolve()
    })
    expect(getQualityWorkbenchMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ file_id: 358, job_id: 1069, trace_id: traceId }),
    )
    expect(container.textContent).toContain('RAG 质量工作台')
    await act(async () => {
      root.unmount()
    })
  })

  it('keeps the rendered projection field whitelist bounded', () => {
    expect(safeQualityData({ file_id: 42, provider: 'ollama', prompt: 'secret', text: 'private' })).toEqual({
      file_id: 42,
      provider: 'ollama',
    })
  })

  it('recursively removes unsafe nested projection fields', () => {
    expect(safeQualityData({ counts: { final_results: 2, prompt: 'secret' } })).toEqual({ counts: { final_results: 2 } })
  })

  it('keeps bounded source locations while excluding source text', () => {
    expect(safeQualityData({
      source_locations: [{ chunk_id: 7, loc_type: 'page', loc_label: 'p. 3', text: 'private body' }],
    })).toEqual({
      source_locations: [{ chunk_id: 7, loc_type: 'page', loc_label: 'p. 3' }],
    })
  })

  it('loads a file-scoped chunk outline and previews the selected chunk', async () => {
    getQualityWorkbenchMock.mockResolvedValue({
      schema_version: '187.1',
      correlation: { file_id: 358, job_id: null, trace_id: null, query_hash: null, request_scope_id: 'scope-1', versions: {} },
      extraction: { state: 'missing' }, retrieval: { state: 'missing' }, evidence: { state: 'missing' }, answer: { state: 'missing' },
      failures: [], truncated: false, truncated_sections: [],
    })
    getQualityWorkbenchOptionsMock.mockResolvedValue({ schema_version: '187.1', file_id: 358, jobs: [] })
    listKnowledgeBaseFileChunksMock.mockResolvedValue({
      file_id: 358,
      original_name: '复合报表.pdf',
      index_status: 'ready',
      chunk_count: 2,
      embedding_dim: 3,
      items: [
        {
          id: 701, chunk_index: 0, source: '复合报表.pdf', text: '第一段正文', char_start: 0, char_end: 5,
          embedding_model: 'test', embedding_dim: 3, embedding_preview: { dim: 3, head: [1], norm: 1 },
          created_at: null, heading_path: '第一章', block_type: 'paragraph', content_kind: 'text', loc_label: '第 1 页',
        },
      ],
      total: 1, page: 1, page_size: 100,
    })
    container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={['/admin/knowledge-base/quality-workbench?file_id=358']}>
          <I18nextProvider i18n={i18n}><AntdApp><QualityWorkbenchPage /></AntdApp></I18nextProvider>
        </MemoryRouter>,
      )
      await new Promise((resolve) => setTimeout(resolve, 50))
    })
    expect(listKnowledgeBaseFileChunksMock).toHaveBeenCalledWith(358, { page: 1, page_size: 100 })
    expect(container.textContent).toContain('Chunk #1')
    expect(container.textContent).toContain('第一段正文')
    expect(container.textContent).toContain('第 1 页')
    await act(async () => root.unmount())
  })

  it('loads the next chunk page when the material has more than 100 chunks', async () => {
    getQualityWorkbenchMock.mockResolvedValue({
      schema_version: '187.1',
      correlation: { file_id: 358, job_id: null, trace_id: null, query_hash: null, request_scope_id: 'scope-1', versions: {} },
      extraction: { state: 'missing' }, retrieval: { state: 'missing' }, evidence: { state: 'missing' }, answer: { state: 'missing' },
      failures: [], truncated: false, truncated_sections: [],
    })
    getQualityWorkbenchOptionsMock.mockResolvedValue({ schema_version: '187.1', file_id: 358, jobs: [] })
    const chunk = (id: number, index: number) => ({
      id, chunk_index: index, source: '长文档.pdf', text: `正文 ${index + 1}`, char_start: index, char_end: index + 1,
      embedding_model: 'test', embedding_dim: 3, embedding_preview: { dim: 3, head: [1], norm: 1 }, created_at: null,
    })
    listKnowledgeBaseFileChunksMock
      .mockResolvedValueOnce({ file_id: 358, original_name: '长文档.pdf', index_status: 'ready', chunk_count: 101, embedding_dim: 3, items: [chunk(701, 0)], total: 101, page: 1, page_size: 100 })
      .mockResolvedValueOnce({ file_id: 358, original_name: '长文档.pdf', index_status: 'ready', chunk_count: 101, embedding_dim: 3, items: [chunk(801, 100)], total: 101, page: 2, page_size: 100 })
    container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    await act(async () => {
      root.render(<MemoryRouter initialEntries={['/admin/knowledge-base/quality-workbench?file_id=358']}><I18nextProvider i18n={i18n}><AntdApp><QualityWorkbenchPage /></AntdApp></I18nextProvider></MemoryRouter>)
      await new Promise((resolve) => setTimeout(resolve, 50))
    })
    expect(container.textContent).toContain('已加载 1 / 101')
    const loadMoreButton = Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.includes('加载更多 Chunk')) as HTMLButtonElement | undefined
    expect(loadMoreButton).not.toBeUndefined()
    await act(async () => {
      loadMoreButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    expect(listKnowledgeBaseFileChunksMock).toHaveBeenLastCalledWith(358, { page: 2, page_size: 100 })
    const secondChunkButton = Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.includes('#101')) as HTMLButtonElement | undefined
    expect(secondChunkButton).not.toBeUndefined()
    await act(async () => {
      secondChunkButton?.click()
      await Promise.resolve()
    })
    expect(container.textContent).toContain('正文 101')
    expect(container.textContent).toContain('已加载 2 / 101')
    await act(async () => root.unmount())
  })

  it('saves a bounded chunk correction without reindexing the source file', async () => {
    getQualityWorkbenchMock.mockResolvedValue({
      schema_version: '187.1',
      correlation: { file_id: 358, job_id: null, trace_id: null, query_hash: null, request_scope_id: 'scope-1', versions: {} },
      extraction: { state: 'missing' }, retrieval: { state: 'missing' }, evidence: { state: 'missing' }, answer: { state: 'missing' },
      failures: [], truncated: false, truncated_sections: [],
    })
    getQualityWorkbenchOptionsMock.mockResolvedValue({ schema_version: '187.1', file_id: 358, jobs: [] })
    listKnowledgeBaseFileChunksMock.mockResolvedValue({
      file_id: 358, original_name: '复合报表.pdf', index_status: 'ready', chunk_count: 1, embedding_dim: 3,
      items: [{ id: 701, chunk_index: 0, source: '复合报表.pdf', text: '第一段正文', char_start: 0, char_end: 5, embedding_model: 'test', embedding_dim: 3, embedding_preview: { dim: 3, head: [1], norm: 1 }, created_at: null }],
      total: 1, page: 1, page_size: 100,
    })
    patchKnowledgeBaseChunkMock.mockResolvedValue({ chunk_id: 701, file_id: 358, chunk_index: 0, text: '修订后的正文', embedding_model: 'test' })
    container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    await act(async () => {
      root.render(<MemoryRouter initialEntries={['/admin/knowledge-base/quality-workbench?file_id=358']}><I18nextProvider i18n={i18n}><AntdApp><QualityWorkbenchPage /></AntdApp></I18nextProvider></MemoryRouter>)
      await new Promise((resolve) => setTimeout(resolve, 50))
    })
    const editor = container.querySelector('[aria-label="修订后的 Chunk 文本"]') as HTMLTextAreaElement | null
    expect(editor).not.toBeNull()
    expect(container.textContent).toContain('owner 或管理员权限校验')
    await act(async () => {
      if (editor) {
        const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set
        setter?.call(editor, '修订后的正文')
        editor.dispatchEvent(new Event('input', { bubbles: true }))
        editor.dispatchEvent(new Event('change', { bubbles: true }))
      }
    })
    const saveButton = Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.includes('保存纠偏')) as HTMLButtonElement | undefined
    await act(async () => {
      saveButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    expect(patchKnowledgeBaseChunkMock).toHaveBeenCalledWith(358, 701, { text: '修订后的正文', reembed: true })
    await act(async () => root.unmount())
  })

  it('runs retrieval diagnostics scoped to the selected file', async () => {
    getQualityWorkbenchMock.mockResolvedValue({
      schema_version: '187.1',
      correlation: { file_id: 358, job_id: null, trace_id: null, query_hash: null, request_scope_id: 'scope-1', versions: {} },
      extraction: { state: 'missing' }, retrieval: { state: 'missing' }, evidence: { state: 'missing' }, answer: { state: 'missing' },
      failures: [], truncated: false, truncated_sections: [],
    })
    getQualityWorkbenchOptionsMock.mockResolvedValue({ schema_version: '187.1', file_id: 358, jobs: [] })
    listKnowledgeBaseFileChunksMock.mockResolvedValue({ file_id: 358, original_name: '复合报表.pdf', index_status: 'ready', chunk_count: 0, embedding_dim: 3, items: [], total: 0, page: 1, page_size: 100 })
    searchKnowledgeBaseMock.mockResolvedValue({ items: [], embedding_model: 'test', top_k: 5, fetched_at: '2026-08-15T00:00:00Z' })
    container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    await act(async () => {
      root.render(<MemoryRouter initialEntries={['/admin/knowledge-base/quality-workbench?file_id=358']}><I18nextProvider i18n={i18n}><AntdApp><QualityWorkbenchPage /></AntdApp></I18nextProvider></MemoryRouter>)
      await new Promise((resolve) => setTimeout(resolve, 50))
    })
    const retrievalTab = Array.from(container.querySelectorAll('[role="tab"]')).find((tab) => tab.textContent?.includes('检索测试')) as HTMLElement | undefined
    await act(async () => {
      retrievalTab?.click()
      await Promise.resolve()
    })
    const queryInput = container.querySelector('[aria-label="检索测试问题"]') as HTMLInputElement | null
    expect(queryInput).not.toBeNull()
    await act(async () => {
      if (queryInput) {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
        setter?.call(queryInput, '报表主题')
        queryInput.dispatchEvent(new Event('input', { bubbles: true }))
        queryInput.dispatchEvent(new Event('change', { bubbles: true }))
      }
    })
    const searchButton = Array.from(container.querySelectorAll('button')).find((button) => button.textContent?.includes('运行检索测试')) as HTMLButtonElement | undefined
    await act(async () => {
      searchButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    expect(searchKnowledgeBaseMock).toHaveBeenCalledWith(expect.objectContaining({ query: '报表主题', file_ids: [358], top_k: 5, debug: true, return_search_trace: true }))
    await act(async () => root.unmount())
  })

  it('clears prior material results when the URL scope changes', async () => {
    const qualityResponse = (fileId: number) => ({
      schema_version: '187.1',
      correlation: { file_id: fileId, job_id: null, trace_id: null, query_hash: null, request_scope_id: 'scope-1', versions: {} },
      extraction: { state: 'missing' }, retrieval: { state: 'missing' }, evidence: { state: 'missing' }, answer: { state: 'missing' },
      failures: [], truncated: false, truncated_sections: [],
    })
    getQualityWorkbenchMock.mockResolvedValueOnce(qualityResponse(358)).mockResolvedValueOnce(qualityResponse(359))
    getQualityWorkbenchOptionsMock.mockResolvedValue({ schema_version: '187.1', file_id: 358, jobs: [] })
    listKnowledgeBaseFileChunksMock
      .mockResolvedValueOnce({ file_id: 358, original_name: '旧资料.pdf', index_status: 'ready', chunk_count: 1, embedding_dim: 3, items: [{ id: 701, chunk_index: 0, source: '旧资料.pdf', text: '旧资料 Chunk', char_start: 0, char_end: 6, embedding_model: 'test', embedding_dim: 3, embedding_preview: { dim: 3, head: [1], norm: 1 }, created_at: null }], total: 1, page: 1, page_size: 100 })
      .mockResolvedValueOnce({ file_id: 359, original_name: '新资料.pdf', index_status: 'ready', chunk_count: 0, embedding_dim: 3, items: [], total: 0, page: 1, page_size: 100 })
    container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    function ScopeChanger() {
      const navigate = useNavigate()
      useEffect(() => {
        const timer = window.setTimeout(() => navigate('/admin/knowledge-base/quality-workbench?file_id=359'), 10)
        return () => window.clearTimeout(timer)
      }, [navigate])
      return <QualityWorkbenchPage />
    }
    await act(async () => {
      root.render(<MemoryRouter initialEntries={['/admin/knowledge-base/quality-workbench?file_id=358']}><I18nextProvider i18n={i18n}><AntdApp><ScopeChanger /></AntdApp></I18nextProvider></MemoryRouter>)
      await new Promise((resolve) => setTimeout(resolve, 100))
    })
    expect(getQualityWorkbenchMock).toHaveBeenLastCalledWith(expect.objectContaining({ file_id: 359 }))
    expect(container.textContent).not.toContain('旧资料 Chunk')
    expect(container.textContent).toContain('当前资料没有可见 Chunk')
    await act(async () => root.unmount())
  })
})
