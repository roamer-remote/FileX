import { describe, expect, it } from 'vitest'
import { SHARE_INACTIVE_NAV_PATH } from '@/lib/shareNavigation'

describe('shareNavigation', () => {
  it('inactive share links go to login', () => {
    expect(SHARE_INACTIVE_NAV_PATH).toBe('/login')
  })
})
