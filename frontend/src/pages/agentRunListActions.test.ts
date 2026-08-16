import { describe, expect, it } from 'vitest'
import {
  canDeleteAgentRuns,
  isAgentRunRowSelectionClick,
  planRefreshAfterDelete,
} from './agentRunListActions'

describe('agentRunListActions', () => {
  describe('planRefreshAfterDelete', () => {
    it('reloads current page when it remains valid', () => {
      expect(
        planRefreshAfterDelete({ page: 2, pageSize: 20, total: 45, deletedCount: 2 }),
      ).toEqual({
        nextPage: null,
        shouldReloadCurrentPage: true,
      })
    })

    it('moves to last page when current page becomes empty', () => {
      expect(
        planRefreshAfterDelete({ page: 3, pageSize: 20, total: 41, deletedCount: 2 }),
      ).toEqual({
        nextPage: 2,
        shouldReloadCurrentPage: false,
      })
    })

    it('returns page 1 when all records are deleted', () => {
      expect(
        planRefreshAfterDelete({ page: 2, pageSize: 20, total: 25, deletedCount: 25 }),
      ).toEqual({
        nextPage: 1,
        shouldReloadCurrentPage: false,
      })
    })
  })

  describe('isAgentRunRowSelectionClick', () => {
    it('detects checkbox wrapper clicks', () => {
      const label = {
        closest: (selector: string) =>
          selector.includes('checkbox') || selector.includes('label') ? label : null,
      } as unknown as HTMLElement
      expect(isAgentRunRowSelectionClick(label)).toBe(true)
    })

    it('allows row body clicks to navigate', () => {
      const cell = {
        closest: () => null,
      } as unknown as HTMLElement
      expect(isAgentRunRowSelectionClick(cell)).toBe(false)
    })
  })

  describe('canDeleteAgentRuns', () => {
    it('requires selection and idle state', () => {
      expect(canDeleteAgentRuns(['run-1'], false)).toBe(true)
      expect(canDeleteAgentRuns([], false)).toBe(false)
      expect(canDeleteAgentRuns(['run-1'], true)).toBe(false)
    })
  })
})
