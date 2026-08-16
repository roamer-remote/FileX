/**
 * @vitest-environment jsdom
 */

import { act } from 'react-dom/test-utils'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ConfigProvider } from 'antd'
import { I18nextProvider } from 'react-i18next'
import type { WikiLinksResponse } from '@/api/files'
import { getFileWikiLinks } from '@/api/files'
import i18n from '@/i18n'
import WikiLinksListModal from './WikiLinksListModal'

vi.mock('@/api/files', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/files')>()
  return {
    ...actual,
    getFileWikiLinks: vi.fn(),
  }
})

const MOCK_WIKI_LINKS: WikiLinksResponse = {
  file_id: 1,
  outlink_count: 1,
  backlink_count: 1,
  coref_count: 0,
  coref_files: [],
  outlinks: [
    {
      anchor_id: 'out-1',
      target_file_id: 42,
      target_name: 'Target Doc',
      link_text: 'link',
      target_wiki_slug: null,
      link_kind: 'file',
      start_offset: 0,
      end_offset: 1,
      broken: false,
      broken_reason: null,
    },
  ],
  backlinks: [
    {
      anchor_id: 'back-1',
      source_file_id: 99,
      source_name: 'Source Doc',
      link_text: 'ref',
      broken: false,
    },
  ],
}

async function renderModal(
  props: Partial<React.ComponentProps<typeof WikiLinksListModal>> & {
    onOpenFile: (fileId: number, meta?: { anchorId?: string }) => void
  },
) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root: Root = createRoot(container)

  await act(async () => {
    root.render(
      <ConfigProvider>
        <I18nextProvider i18n={i18n}>
          <WikiLinksListModal
            open
            onClose={vi.fn()}
            fileId={1}
            fileName="Test.md"
            linkKind="outlinks"
            {...props}
          />
        </I18nextProvider>
      </ConfigProvider>,
    )
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

describe('WikiLinksListModal', () => {
  const cleanups: Array<() => Promise<void>> = []

  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(async () => {
    for (const cleanup of cleanups.splice(0)) {
      await cleanup()
    }
  })

  it('uses initialData without calling getFileWikiLinks', async () => {
    const { cleanup } = await renderModal({
      initialData: MOCK_WIKI_LINKS,
      onOpenFile: vi.fn(),
    })
    cleanups.push(cleanup)

    expect(getFileWikiLinks).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('Target Doc')
  })

  it('passes anchorId when opening an outlink row', async () => {
    const onOpenFile = vi.fn()
    const { cleanup } = await renderModal({
      initialData: MOCK_WIKI_LINKS,
      linkKind: 'outlinks',
      onOpenFile,
    })
    cleanups.push(cleanup)

    const row = Array.from(document.body.querySelectorAll('[role="button"]')).find((el) =>
      (el.textContent ?? '').includes('Target Doc'),
    )
    expect(row).toBeTruthy()

    await act(async () => {
      row!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(onOpenFile).toHaveBeenCalledWith(42, { anchorId: 'out-1' })
  })

  it('passes anchorId when opening a backlink row', async () => {
    const onOpenFile = vi.fn()
    const { cleanup } = await renderModal({
      initialData: MOCK_WIKI_LINKS,
      linkKind: 'backlinks',
      onOpenFile,
    })
    cleanups.push(cleanup)

    const row = Array.from(document.body.querySelectorAll('[role="button"]')).find((el) =>
      (el.textContent ?? '').includes('Source Doc'),
    )
    expect(row).toBeTruthy()

    await act(async () => {
      row!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(onOpenFile).toHaveBeenCalledWith(99, { anchorId: 'back-1' })
  })

  it('opens slug-only outlinks via onOpenOutlink', async () => {
    const onOpenOutlink = vi.fn()
    const slugData: WikiLinksResponse = {
      ...MOCK_WIKI_LINKS,
      outlinks: [
        {
          anchor_id: 'slug-1',
          target_file_id: null,
          target_name: null,
          target_wiki_slug: 'my-wiki-topic',
          link_kind: 'wiki',
          link_text: 'topic',
          start_offset: 0,
          end_offset: 1,
          broken: false,
          broken_reason: null,
        },
      ],
    }
    const { cleanup } = await renderModal({
      initialData: slugData,
      linkKind: 'outlinks',
      onOpenFile: vi.fn(),
      onOpenOutlink,
    })
    cleanups.push(cleanup)

    const row = Array.from(document.body.querySelectorAll('[role="button"]')).find((el) =>
      (el.textContent ?? '').includes('topic'),
    )
    expect(row).toBeTruthy()

    await act(async () => {
      row!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(onOpenOutlink).toHaveBeenCalledWith(
      expect.objectContaining({
        target_wiki_slug: 'my-wiki-topic',
        anchor_id: 'slug-1',
      }),
    )
  })
})
