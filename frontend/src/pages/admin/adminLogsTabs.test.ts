import { describe, expect, it } from 'vitest'
import {
  adminLogsOperationPath,
  applyAdminLogsUserIdToSearch,
  parseAdminLogsTabFromSearch,
  parseAdminLogsUserIdFromSearch,
} from './adminLogsTabs'

describe('adminLogsTabs', () => {
  it('builds operation logs deep link with tab and optional user_id', () => {
    expect(adminLogsOperationPath()).toBe('/admin/logs?tab=logs')
    expect(adminLogsOperationPath(42)).toBe('/admin/logs?tab=logs&user_id=42')
  })

  describe('parseAdminLogsTabFromSearch', () => {
    it('maps tab query and user_id to tab id', () => {
      expect(parseAdminLogsTabFromSearch(new URLSearchParams('tab=monitor'))).toBe('monitor')
      expect(parseAdminLogsTabFromSearch(new URLSearchParams('tab=logs'))).toBe('logs')
      expect(parseAdminLogsTabFromSearch(new URLSearchParams('user_id=1'))).toBe('logs')
      expect(parseAdminLogsTabFromSearch(new URLSearchParams())).toBe('logs')
    })
  })

  describe('parseAdminLogsUserIdFromSearch', () => {
    it('parses positive user_id only', () => {
      expect(parseAdminLogsUserIdFromSearch(new URLSearchParams('user_id=7'))).toBe(7)
      expect(parseAdminLogsUserIdFromSearch(new URLSearchParams())).toBeUndefined()
      expect(parseAdminLogsUserIdFromSearch(new URLSearchParams('user_id=0'))).toBeUndefined()
      expect(parseAdminLogsUserIdFromSearch(new URLSearchParams('user_id=abc'))).toBeUndefined()
    })
  })

  describe('applyAdminLogsUserIdToSearch', () => {
    it('sets or removes user_id while preserving other params', () => {
      const base = new URLSearchParams('tab=logs&user_id=3')
      expect(applyAdminLogsUserIdToSearch(base, 9).toString()).toBe('tab=logs&user_id=9')
      expect(applyAdminLogsUserIdToSearch(base, undefined).toString()).toBe('tab=logs')
    })
  })
})
