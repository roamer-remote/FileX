import { describe, expect, it } from 'vitest'
import { getGettingStartedDingHelpHtml } from './gettingStartedHelp'

describe('getGettingStartedDingHelpHtml', () => {
  it('uses the English Ding skill flow embed for English UI', () => {
    const html = getGettingStartedDingHelpHtml('en')

    expect(html).toContain('/help/ding-skill-flow.html?embed=1&lang=en')
    expect(html).toContain('title="Ding skill operation flow"')
  })

  it('uses the Chinese Ding skill flow embed for Chinese UI', () => {
    const html = getGettingStartedDingHelpHtml('zh-CN')

    expect(html).toContain('/help/ding-skill-flow.html?embed=1&lang=zh')
    expect(html).toContain('title="钉技能操作流向图"')
  })
})
