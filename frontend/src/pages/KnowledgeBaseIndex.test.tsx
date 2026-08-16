/**
 * @vitest-environment jsdom
 */

import { act } from 'react-dom/test-utils'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App, ConfigProvider } from 'antd'
import { I18nextProvider } from 'react-i18next'
import { getKnowledgeBaseIndex, rebuildKnowledgeBaseIndex } from '@/api/knowledgeBase'
import i18n from '@/i18n'
import KnowledgeBaseIndexPage from './KnowledgeBaseIndex'

vi.mock('@/api/knowledgeBase', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/knowledgeBase')>()
  return {
    ...actual,
    getKnowledgeBaseIndex: vi.fn(),
    rebuildKnowledgeBaseIndex: vi.fn(),
  }
})

vi.mock('@/components/KbIndexPreviewTable', () => ({
  default: () => <div data-testid="auto-table" />,
}))

vi.mock('@/components/KbWikiIndexPreviewTable', () => ({
  default: () => <div data-testid="wiki-table" />,
}))

vi.mock('@/components/WikiPagesTabPane', () => ({
  default: () => <div data-testid="wiki-pages" />,
}))

vi.mock('@/components/knowledge/WorkspaceBackupButton', () => ({
  default: () => <button type="button">backup</button>,
}))

async function renderPage() {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root: Root = createRoot(container)
  await act(async () => {
    root.render(
      <ConfigProvider>
        <I18nextProvider i18n={i18n}>
          <App>
            <KnowledgeBaseIndexPage />
          </App>
        </I18nextProvider>
      </ConfigProvider>,
    )
  })
  await act(async () => {
    await Promise.resolve()
  })
  return {
    container,
    root,
    async cleanup() {
      await act(async () => {
        root.unmount()
      })
      container.remove()
    },
  }
}

describe('KnowledgeBaseIndexPage', () => {
  const cleanups: Array<() => Promise<void>> = []

  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(async () => {
    for (const cleanup of cleanups.splice(0)) {
      await cleanup()
    }
  })

  it('shows a read error instead of the empty-index state for non-404 failures', async () => {
    vi.mocked(getKnowledgeBaseIndex).mockRejectedValue({
      response: { status: 409, data: { detail: '索引文件损坏，无法读取；请重建索引' } },
    })
    vi.mocked(rebuildKnowledgeBaseIndex).mockResolvedValue({
      message: 'ok',
      content: 'rebuilt content',
      file_count: 1,
    })

    const { cleanup } = await renderPage()
    cleanups.push(cleanup)

    expect(document.body.textContent).toContain('索引文件损坏，无法读取；请重建索引')
    expect(document.body.textContent).not.toContain('尚无索引文件')
  })
})
