import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { fileTypeIcon } from './fileIcons'

describe('fileTypeIcon', () => {
  it('uses a mail icon for eml files even when the MIME type is generic', () => {
    const markup = renderToStaticMarkup(fileTypeIcon('application/octet-stream', 'message.eml'))

    expect(markup).toContain('anticon-mail')
    expect(markup).not.toContain('anticon-folder-open')
  })
})
