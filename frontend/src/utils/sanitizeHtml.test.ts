import { describe, expect, it } from 'vitest'
import { markdownToSafeHtml } from '@/utils/markdownPreview'
import { preprocessExtractAssetImages } from '@/utils/extractAssetHtml'
import { sanitizeMarkdownHtml, sanitizeSpreadsheetHtml } from '@/utils/sanitizeHtml'

describe('sanitizeMarkdownHtml', () => {
  it('strips script tags', () => {
    const dirty = '<p>ok</p><script>alert(1)</script>'
    expect(sanitizeMarkdownHtml(dirty)).toBe('<p>ok</p>')
  })

  it('keeps wiki-link data attributes', () => {
    const dirty =
      '<a href="#file-1" class="wiki-link" data-wiki-file-id="1">note</a>'
    expect(sanitizeMarkdownHtml(dirty)).toContain('data-wiki-file-id="1"')
    expect(sanitizeMarkdownHtml(dirty)).toContain('class="wiki-link"')
  })

  it('keeps sync block data-source-line', () => {
    const dirty = '<div class="me-sync-block" data-source-line="3"><p>x</p></div>'
    expect(sanitizeMarkdownHtml(dirty)).toContain('data-source-line="3"')
  })

  it('keeps katex html output classes', () => {
    const dirty =
      '<span class="katex"><span class="katex-html" aria-hidden="true"><span class="mord">x</span></span></span>'
    const clean = sanitizeMarkdownHtml(dirty)
    expect(clean).toContain('class="katex"')
    expect(clean).toContain('katex-html')
    expect(clean).toContain('aria-hidden="true"')
  })

  it('strips script inside katex-like markup', () => {
    const dirty = '<span class="katex"><script>alert(1)</script></span>'
    expect(sanitizeMarkdownHtml(dirty)).not.toContain('script')
  })
})

describe('sanitizeSpreadsheetHtml', () => {
  it('keeps table cells and strips script', () => {
    const dirty = '<table><tr><td>1</td></tr></table><script>x</script>'
    const clean = sanitizeSpreadsheetHtml(dirty)
    expect(clean).toContain('<table')
    expect(clean).not.toContain('script')
  })
})

describe('markdownToSafeHtml', () => {
  it('renders markdown and removes inline event handlers', () => {
    const md = '**bold**<img src=x onerror=alert(1)>'
    const html = markdownToSafeHtml(md, { wikiLinks: false })
    expect(html).toContain('<strong>bold</strong>')
    expect(html.toLowerCase()).not.toContain('onerror')
  })

  it('renders inline katex', () => {
    const html = markdownToSafeHtml('Energy $E=mc^2$ units.', { wikiLinks: false })
    expect(html).toContain('katex')
    expect(html).toContain('class="katex"')
  })

  it('renders block katex', () => {
    const html = markdownToSafeHtml('$$\n\\frac{a}{b}\n$$', { wikiLinks: false })
    expect(html).toContain('katex')
  })

  it('does not treat currency as math', () => {
    const html = markdownToSafeHtml('The cost is $100 per month.', { wikiLinks: false })
    expect(html).not.toContain('class="katex"')
    expect(html).toContain('$100')
  })

  it('renders OCR-style math glued to Chinese text', () => {
    const html = markdownToSafeHtml('点$\\mathsf { A } _ { 2 0 1 8 }$的坐标是', { wikiLinks: false })
    expect(html).toContain('class="katex"')
    expect(html).toContain('的坐标是')
  })

  it('renders nested mathsf subscripts from OCR', () => {
    const html = markdownToSafeHtml(
      '经 $\\triangle \\mathsf { A } _ { \\mathsf { n } - 1 } \\mathsf { B } _ { \\mathsf { n } - 1 } \\mathsf { C } _ { \\mathsf { n } - 1 }$ 变换',
      { wikiLinks: false },
    )
    expect(html).toContain('class="katex"')
  })

  it('renders MinerU filex equation fenced block as display math', () => {
    const md = `<!-- filex:content kind=equation page=4 -->
\`\`\`
$$
\\mathsf { a ^ { 2 } + 2 a b + b ^ { 2 } }
$$
\`\`\``
    const html = markdownToSafeHtml(md, { wikiLinks: false })
    expect(html).toContain('class="katex"')
    expect(html).not.toContain('<pre><code>')
  })

  it('shows fallback when OCR equation latex is invalid', () => {
    const md = `<!-- filex:content kind=equation page=9 -->
\`\`\`
$$
\\frac { \\frac { \\mathbb { H } } { 2 } \\frac  \\cdot x
$$
\`\`\``
    const html = markdownToSafeHtml(md, { wikiLinks: false })
    expect(html).toContain('filex-equation-fallback')
    expect(html).toContain('公式无法自动渲染')
    expect(html).not.toContain('katex-error')
  })

  it('does not render math inside fenced code', () => {
    const html = markdownToSafeHtml('```\n$x^2$\n```', { wikiLinks: false })
    expect(html).toContain('$x^2$')
    expect(html).not.toContain('class="katex"')
  })

  it('does not render math inside inline code', () => {
    const html = markdownToSafeHtml('Use `$x^2$` literal.', { wikiLinks: false })
    expect(html).toContain('$x^2$')
    expect(html).not.toContain('class="katex"')
  })

  it('keeps extract asset file id through markdown sanitization', () => {
    const md =
      '![invoice](2/2026-07/.extract_assets/367/images/c64a4cb5ee1423195077c1b0f56bf92de6fe150f13fcc7a0c9838fedc5ac62c7.jpg)'
    const html = markdownToSafeHtml(md, { fileId: 389, wikiLinks: false })
    expect(html).toContain('data-extract-asset-file-id="367"')
    expect(html).toContain(
      'data-extract-asset-fallback-src="/api/files/367/extract-assets/c64a4cb5ee1423195077c1b0f56bf92de6fe150f13fcc7a0c9838fedc5ac62c7.jpg"',
    )
    expect(html).toContain(
      'data-extract-asset-key="c64a4cb5ee1423195077c1b0f56bf92de6fe150f13fcc7a0c9838fedc5ac62c7.jpg"',
    )
  })
})

describe('preprocessExtractAssetImages', () => {
  it('rewrites nested extract_assets image paths to API URLs', () => {
    const md =
      '![fig](2/2026-06/.extract_assets/250/images/abc.jpg)'
    const out = preprocessExtractAssetImages(md, 250)
    expect(out).toContain('/api/files/250/extract-assets/abc.jpg')
    expect(out).not.toContain('token=')
    expect(out).not.toContain('.extract_assets/250/images')
  })
})
