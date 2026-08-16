import { describe, expect, it } from 'vitest'
import i18n from '@/i18n'
import { ADMIN_OPS_PATHS } from './AdminOpsNavMenu'

describe('AdminOpsNavMenu quality workbench entry', () => {
  it('tracks the quality workbench route for active navigation state', () => {
    expect(ADMIN_OPS_PATHS).toContain('/admin/knowledge-base/quality-workbench')
  })

  it('provides localized quality workbench navigation labels', () => {
    expect(i18n.t('appLayout.qualityWorkbench', { lng: 'zh-CN' })).toBe('质量工作台')
    expect(i18n.t('appLayout.qualityWorkbench', { lng: 'en' })).toBe('Quality workbench')
  })
})
