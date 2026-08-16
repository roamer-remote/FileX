import { act } from 'react-dom/test-utils'
import { createRoot } from 'react-dom/client'
import { describe, expect, it } from 'vitest'
import type { FileItem } from '@/api/files'
import { FilePreviewBody } from './FilePreviewBody'

function baseFile(overrides: Partial<FileItem>): FileItem {
  return {
    id: 1,
    filename: 'topic.md',
    original_name: 'topic.md',
    file_size: 100,
    mime_type: 'text/markdown',
    folder_id: null,
    user_id: 1,
    created_at: '2026-01-01T00:00:00Z',
    has_md: true,
    md_has_content: true,
    index_status: 'ready',
    extract_status: 'ready',
    page_kind: 'source',
    ...overrides,
  } as FileItem
}

describe('FilePreviewBody markdown source preview', () => {
  it('renders extracted eml markdown as a read-only preview', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    const root = createRoot(host)

    await act(async () => {
      root.render(
        <FilePreviewBody
          file={baseFile({ original_name: 'mail.eml', mime_type: 'message/rfc822', has_md: true })}
          previewUrl="/api/files/1/preview"
          pdfBlobUrl={null}
          pdfLoadError={false}
          htmlBlobUrl={null}
          htmlLoadError={false}
          officeLoading={false}
          officeError={false}
          excelTabs={[]}
          docxBodyRef={{ current: null }}
          pptxWrapperRef={{ current: null }}
          mdFileSource="# Mail subject"
          mdHtml="<h1>Mail subject</h1>"
          mdFileLoading={false}
          mdContainerRef={{ current: null }}
          txtContent=""
          onDownload={() => undefined}
          t={(key) => key}
        />,
      )
    })

    expect(host.querySelector('.pv-md-source-readonly')).not.toBeNull()
    expect(host.querySelector('.pv-md')?.textContent).toContain('Mail subject')
    expect(host.querySelector('.pv-fallback')).toBeNull()

    await act(async () => {
      root.unmount()
    })
    host.remove()
  })

  it('renders source markdown as read-only preview without editor textarea', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    const root = createRoot(host)

    await act(async () => {
      root.render(
        <FilePreviewBody
          file={baseFile({})}
          previewUrl="/api/files/1/preview"
          pdfBlobUrl={null}
          pdfLoadError={false}
          htmlBlobUrl={null}
          htmlLoadError={false}
          officeLoading={false}
          officeError={false}
          excelTabs={[]}
          docxBodyRef={{ current: null }}
          pptxWrapperRef={{ current: null }}
          mdFileSource="# Source Markdown"
          mdHtml="<h1>Source Markdown</h1>"
          mdFileLoading={false}
          mdContainerRef={{ current: null }}
          txtContent=""
          onDownload={() => undefined}
          t={(key) => key}
        />,
      )
    })

    expect(host.querySelector('textarea')).toBeNull()
    expect(host.querySelector('.pv-md-source-readonly')).not.toBeNull()
    expect(host.querySelector('.pv-md')?.textContent).toContain('Source Markdown')

    await act(async () => {
      root.unmount()
    })
    host.remove()
  })
})

describe('FilePreviewBody office pdf preview', () => {
  it('renders pptx with pdf preview mime through the pdf iframe', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)
    const root = createRoot(host)

    await act(async () => {
      root.render(
        <FilePreviewBody
          file={baseFile({
            original_name: 'deck.pptx',
            mime_type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            preview_mime_type: 'application/pdf',
          })}
          previewUrl="/api/files/1/preview"
          pdfBlobUrl="blob:pdf-preview"
          pdfLoadError={false}
          htmlBlobUrl={null}
          htmlLoadError={false}
          officeLoading={false}
          officeError={false}
          excelTabs={[]}
          docxBodyRef={{ current: null }}
          pptxWrapperRef={{ current: null }}
          mdFileSource=""
          mdHtml=""
          mdFileLoading={false}
          mdContainerRef={{ current: null }}
          txtContent=""
          onDownload={() => undefined}
          t={(key) => key}
        />,
      )
    })

    expect(host.querySelector('iframe.pv-pdf')).not.toBeNull()
    expect(host.querySelector('.pv-pptx-host')).toBeNull()

    await act(async () => {
      root.unmount()
    })
    host.remove()
  })
})
