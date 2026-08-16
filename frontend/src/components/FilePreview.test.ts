import { describe, expect, it, vi } from 'vitest'
import { getFileMd } from '@/api/files'
import { getAdminFileMd } from '@/api/adminWorkspaces'
import { loadPreviewMarkdown, resolveMdPreviewHydrationState } from './FilePreview'

vi.mock('@/api/files', async () => {
  const actual = await vi.importActual<typeof import('@/api/files')>('@/api/files')
  return { ...actual, getFileMd: vi.fn() }
})

vi.mock('@/api/adminWorkspaces', async () => {
  const actual = await vi.importActual<typeof import('@/api/adminWorkspaces')>('@/api/adminWorkspaces')
  return { ...actual, getAdminFileMd: vi.fn() }
})

describe('resolveMdPreviewHydrationState', () => {
  it('waits until markdown loading finishes before hydrating extract images', () => {
    const mdHtml = '<p>note</p><img data-extract-asset-key="a.jpg" />'

    const loading = resolveMdPreviewHydrationState({
      open: true,
      fileId: 389,
      mdHtml,
      mdFileLoading: true,
    })
    const ready = resolveMdPreviewHydrationState({
      open: true,
      fileId: 389,
      mdHtml,
      mdFileLoading: false,
    })

    expect(loading.enabled).toBe(false)
    expect(ready.enabled).toBe(true)
    expect(ready.contentKey).not.toBe(loading.contentKey)
  })
})

describe('loadPreviewMarkdown', () => {
  it('loads EML preview content from the extracted Markdown endpoint', async () => {
    vi.mocked(getFileMd).mockResolvedValue({ data: '# Mail subject' } as never)
    const fetchSpy = vi.spyOn(globalThis, 'fetch')

    await expect(
      loadPreviewMarkdown({
        id: 42,
        original_name: 'mail.eml',
        mime_type: 'message/rfc822',
      } as never),
    ).resolves.toBe('# Mail subject')

    expect(getFileMd).toHaveBeenCalledWith(42)
    expect(fetchSpy).not.toHaveBeenCalled()
    fetchSpy.mockRestore()
  })

  it('uses the admin Markdown endpoint for admin EML preview', async () => {
    vi.mocked(getAdminFileMd).mockResolvedValue({ data: '# Admin mail' } as never)

    await expect(
      loadPreviewMarkdown(
        { id: 43, original_name: 'admin.eml', mime_type: 'message/rfc822' } as never,
        true,
      ),
    ).resolves.toBe('# Admin mail')

    expect(getAdminFileMd).toHaveBeenCalledWith(43)
    expect(getFileMd).not.toHaveBeenCalledWith(43)
  })
})
