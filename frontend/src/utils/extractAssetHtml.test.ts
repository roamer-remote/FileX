import { describe, expect, it } from 'vitest'
import { marked } from 'marked'
import {
  EXTRACT_ASSET_PLACEHOLDER_SRC,
  parseExtractAssetKeyFromApiSrc,
  preprocessExtractAssetImgTags,
} from '@/utils/extractAssetHtml'
import { preprocessExtractAssetImages } from '@/utils/extractAssetHtml'

describe('extractAssetHtml', () => {
  it('parses asset key from legacy API src', () => {
    expect(parseExtractAssetKeyFromApiSrc('/api/files/347/extract-assets/foo%20bar.jpg')).toBe(
      'foo bar.jpg',
    )
  })

  it('rewrites img tags to placeholder before DOM insert', () => {
    const html =
      '<p><img src="/api/files/347/extract-assets/abc.jpg" alt="fig"></p>'
    const out = preprocessExtractAssetImgTags(html)
    expect(out).toContain(`src="${EXTRACT_ASSET_PLACEHOLDER_SRC}"`)
    expect(out).toContain('data-extract-asset-key="abc.jpg"')
    expect(out).toContain('data-extract-asset-fallback-src="/api/files/347/extract-assets/abc.jpg"')
  })

  it('integrates with markdown extract_assets preprocessing', () => {
    const md = '![fig](2/2026-06/.extract_assets/347/images/abc.jpg)'
    const src = preprocessExtractAssetImages(md, 347)
    const rendered = marked.parse(src) as string
    const html = preprocessExtractAssetImgTags(rendered)
    expect(html).toContain(`src="${EXTRACT_ASSET_PLACEHOLDER_SRC}"`)
    expect(html).toContain('data-extract-asset-key="abc.jpg"')
    expect(html).toContain('data-extract-asset-fallback-src="/api/files/347/extract-assets/abc.jpg"')
  })

  it('handles MinerU note paths with long alt text (file 389 shape)', () => {
    const md = [
      '![712db53bacc5b6855b653844de356cbdc782e9af0298f1ceb3bb6f1fe2f81592.jpg](2/2026-07/.extract_assets/389/images/712db53bacc5b6855b653844de356cbdc782e9af0298f1ceb3bb6f1fe2f81592.jpg)',
      '![Fig. 2. PI3K/AKT signaling might be a potential target](2/2026-07/.extract_assets/389/images/feb1e3bb8592b3ed201d2256a7c804a98421a26550f95c850af16c91e85a4b3a.jpg)',
    ].join('\n\n')
    const src = preprocessExtractAssetImages(md, 389)
    const rendered = marked.parse(src) as string
    const html = preprocessExtractAssetImgTags(rendered)
    expect((html.match(/data-extract-asset-key/g) || []).length).toBe(2)
    expect((html.match(/data-extract-asset-fallback-src/g) || []).length).toBe(2)
    expect(html).toContain(`src="${EXTRACT_ASSET_PLACEHOLDER_SRC}"`)
  })

  it('preserves file id embedded in extract_assets path', () => {
    const md =
      '![invoice](2/2026-07/.extract_assets/367/images/c64a4cb5ee1423195077c1b0f56bf92de6fe150f13fcc7a0c9838fedc5ac62c7.jpg)'
    const src = preprocessExtractAssetImages(md, 389)
    expect(src).toContain('/api/files/367/extract-assets/')
    expect(src).not.toContain('/api/files/389/extract-assets/')

    const rendered = marked.parse(src) as string
    const html = preprocessExtractAssetImgTags(rendered)
    expect(html).toContain('data-extract-asset-file-id="367"')
    expect(html).toContain(
      'data-extract-asset-fallback-src="/api/files/367/extract-assets/c64a4cb5ee1423195077c1b0f56bf92de6fe150f13fcc7a0c9838fedc5ac62c7.jpg"',
    )
    expect(html).toContain(
      'data-extract-asset-key="c64a4cb5ee1423195077c1b0f56bf92de6fe150f13fcc7a0c9838fedc5ac62c7.jpg"',
    )
  })

  it('rewrites MinerU relative image paths without extract_assets prefix', () => {
    const md = [
      '![plain](images/plain.jpg)',
      '![with title](images/with-title.png "Figure title")',
    ].join('\n\n')
    const src = preprocessExtractAssetImages(md, 389)
    const rendered = marked.parse(src) as string
    const html = preprocessExtractAssetImgTags(rendered)
    expect((html.match(/data-extract-asset-key/g) || []).length).toBe(2)
    expect(html).toContain('data-extract-asset-key="plain.jpg"')
    expect(html).toContain('data-extract-asset-key="with-title.png"')
    expect(html).toContain(`src="${EXTRACT_ASSET_PLACEHOLDER_SRC}"`)
  })

  it('does not rewrite external image urls', () => {
    const md = '![remote](https://example.test/.extract_assets/389/images/remote.jpg)'
    expect(preprocessExtractAssetImages(md, 389)).toBe(md)
  })
})
