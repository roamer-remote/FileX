import { describe, expect, it } from 'vitest'
import i18n from '@/i18n'
import { qualityWorkbenchPath } from './FileList'

describe('FileList quality workbench entry', () => {
  it('builds a file-scoped quality workbench path', () => {
    expect(qualityWorkbenchPath(358)).toBe('/admin/knowledge-base/quality-workbench?file_id=358')
  })

  it('provides localized quality workbench labels', () => {
    expect(i18n.t('knowledgeIndex.qualityWorkbench', { lng: 'zh-CN' })).toBe('质量工作台')
    expect(i18n.t('knowledgeIndex.qualityWorkbench', { lng: 'en' })).toBe('Quality workbench')
  })
})
