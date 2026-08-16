import { describe, expect, it } from 'vitest'
import {
  buildDingSkillInstallPrompt,
  DING_SKILL_INSTALL_API_KEY_PLACEHOLDER,
  DEFAULT_AGENT_SKILL_INSTALL_PROMPT,
} from './agentSkillInstall'

const ORIGIN = 'https://ding.yyyou.top'

describe('DEFAULT_AGENT_SKILL_INSTALL_PROMPT', () => {
  it('contains template variables', () => {
    expect(DEFAULT_AGENT_SKILL_INSTALL_PROMPT).toContain('{{ORIGIN}}')
    expect(DEFAULT_AGENT_SKILL_INSTALL_PROMPT).toContain('{{API_KEY}}')
  })

  it('includes WorkBuddy in supported agents', () => {
    expect(DEFAULT_AGENT_SKILL_INSTALL_PROMPT).toContain('WorkBuddy')
  })
})

describe('buildDingSkillInstallPrompt (legacy fallback)', () => {
  it('without apiKey keeps placeholder', () => {
    const text = buildDingSkillInstallPrompt(ORIGIN)
    expect(text).toContain(DING_SKILL_INSTALL_API_KEY_PLACEHOLDER)
    expect(text).toContain(`FILEX_ORIGIN=${ORIGIN}`)
    expect(text).not.toContain('FILEX_API_KEY=fb_test')
  })

  it('with apiKey embeds full key', () => {
    const key = 'fb_test_secret_key_12345'
    const text = buildDingSkillInstallPrompt(ORIGIN, { apiKey: key })
    expect(text).toContain(`FILEX_API_KEY=${key}`)
    expect(text).not.toContain(DING_SKILL_INSTALL_API_KEY_PLACEHOLDER)
  })

  it('strips trailing slash from origin', () => {
    const text = buildDingSkillInstallPrompt(`${ORIGIN}/`)
    expect(text).toContain(`FILEX_ORIGIN=${ORIGIN}`)
  })

  it('replaces template variables', () => {
    const text = buildDingSkillInstallPrompt(ORIGIN, { apiKey: 'fb_test_secret_key_12345' })
    expect(text).not.toContain('{{ORIGIN}}')
    expect(text).not.toContain('{{API_KEY}}')
  })

  it('rendered prompt contains key installation steps', () => {
    const text = buildDingSkillInstallPrompt(ORIGIN, { apiKey: 'fb_test_secret_key_12345' })
    expect(text).toContain('钉安装备忘')
    expect(text).toContain('升级后检查版本匹配')
    expect(text).toContain('LOCAL_SKILL_VERSION')
    expect(text).toContain('SERVER_SKILL_VERSION')
    expect(text).toContain('不一致时勿宣称安装/升级完成')
  })
})
