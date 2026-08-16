/**
 * @vitest-environment jsdom
 */

import { act } from 'react-dom/test-utils'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App, ConfigProvider } from 'antd'
import { I18nextProvider } from 'react-i18next'
import { createApiKey, type ApiKeyCreateResponse } from '@/api/apiKeys'
import i18n from '@/i18n'
import ApiKeyOnboardingWizard from './ApiKeyOnboardingWizard'

vi.mock('@/lib/uiStateSync', () => ({
  patchLocaleUiState: vi.fn(),
}))

vi.mock('@/api/apiKeys', () => ({
  createApiKey: vi.fn(),
}))

vi.mock('@/utils', () => ({
  copyToClipboard: vi.fn(),
}))

vi.mock('@/lib/agentSkillInstall', () => ({
  buildDingSkillInstallPrompt: vi.fn(() => 'mocked install prompt text'),
  fetchAgentSkillInstallPrompt: vi.fn(async () => 'mocked install prompt text'),
}))

import { copyToClipboard } from '@/utils'

const MOCK_CREATED: ApiKeyCreateResponse = {
  id: 1,
  name: 'wizard-test',
  prefix: 'fb_abcd',
  plain_text_key: 'fb_test_secret_full_key_076',
  created_at: '2026-01-01T00:00:00+08:00',
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

function findButton(matcher: (text: string) => boolean): HTMLButtonElement | undefined {
  return Array.from(document.body.querySelectorAll('button')).find((button) =>
    matcher((button.textContent ?? '').replace(/\s+/g, '')),
  )
}

function findPrimaryNextButton(): HTMLButtonElement | undefined {
  return Array.from(document.body.querySelectorAll('button')).find((button) => {
    const text = (button.textContent ?? '').replace(/\s+/g, '')
    return (text === '下一步' || text === 'Next') && button.className.includes('ant-btn-primary')
  })
}

async function renderWizard(onEnsured: () => void = vi.fn()) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)

  await act(async () => {
    root.render(
      <ConfigProvider>
        <App>
          <I18nextProvider i18n={i18n}>
            <ApiKeyOnboardingWizard open onEnsured={onEnsured} />
          </I18nextProvider>
        </App>
      </ConfigProvider>,
    )
  })

  return { container, root, onEnsured }
}

async function createKeyAndShowResult() {
  const input = document.body.querySelector('input') as HTMLInputElement
  expect(input).toBeTruthy()
  setInputValue(input, 'wizard-test')

  const generateBtn = findButton((text) => text.includes('生成密钥') || text === 'Generate')
  expect(generateBtn).toBeTruthy()

  await act(async () => {
    generateBtn!.click()
  })

  await vi.waitFor(() => {
    expect(document.body.textContent).toContain(MOCK_CREATED.plain_text_key)
  })
}

async function goToStep2() {
  await createKeyAndShowResult()
  expect(document.body.querySelector('.ak-wizard-prompt')).toBeNull()

  const nextBtn = findButton((text) => text === '下一步' || text === 'Next')
  expect(nextBtn).toBeTruthy()

  await act(async () => {
    nextBtn!.click()
  })

  await vi.waitFor(() => {
    expect(document.body.querySelector('.ak-wizard-prompt')).toBeTruthy()
  })
}

describe('ApiKeyOnboardingWizard', () => {
  const roots: Root[] = []

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(createApiKey).mockResolvedValue({ data: MOCK_CREATED } as Awaited<
      ReturnType<typeof createApiKey>
    >)
    vi.mocked(copyToClipboard).mockResolvedValue(undefined)
    void i18n.changeLanguage('zh-CN')
  })

  afterEach(() => {
    for (const root of roots) {
      act(() => {
        root.unmount()
      })
    }
    roots.length = 0
    document.body.innerHTML = ''
  })

  it('SC-076-003/004: step1 shows full key and blocks step2 until next', async () => {
    const { root } = await renderWizard()
    roots.push(root)

    await createKeyAndShowResult()
    expect(document.body.querySelector('.ak-wizard-prompt')).toBeNull()

    const nextBtn = findButton((text) => text === '下一步' || text === 'Next')
    await act(async () => {
      nextBtn!.click()
    })

    await vi.waitFor(() => {
      expect(document.body.querySelector('.ak-wizard-prompt')).toBeTruthy()
    })
  })

  it('SC-076-006: step2 copy reject still allows manual continue to step3', async () => {
    vi.mocked(copyToClipboard).mockRejectedValue(new Error('clipboard denied'))
    const { root } = await renderWizard()
    roots.push(root)

    await goToStep2()

    const copyInstallBtn = findButton((text) => text.includes('复制安装指令') || text.includes('Copyinstall'))
    await act(async () => {
      copyInstallBtn!.click()
    })

    await vi.waitFor(() => {
      expect(copyToClipboard).toHaveBeenCalled()
    })

    const primaryNext = findPrimaryNextButton()
    expect(primaryNext?.disabled).toBe(true)

    const manualBtn = findButton((text) => text.includes('我已手动复制') || text.includes('copiedmanually'))
    expect(manualBtn).toBeTruthy()

    await act(async () => {
      manualBtn!.click()
    })

    await vi.waitFor(() => {
      expect(document.body.textContent).toMatch(/配置已完成|Setup is complete/)
      expect(document.body.querySelector('.ak-wizard-prompt')).toBeNull()
    })
  })

  it('SC-076-006: step2 copy success enables primary next', async () => {
    vi.mocked(copyToClipboard).mockResolvedValue(undefined)
    const { root } = await renderWizard()
    roots.push(root)

    await goToStep2()

    const primaryNextBefore = findPrimaryNextButton()
    expect(primaryNextBefore?.disabled).toBe(true)

    const copyInstallBtn = findButton((text) => text.includes('复制安装指令') || text.includes('Copyinstall'))
    await act(async () => {
      copyInstallBtn!.click()
    })

    await vi.waitFor(() => {
      const primaryNextAfter = findPrimaryNextButton()
      expect(primaryNextAfter?.disabled).toBe(false)
    })
  })

  it('SC-076-007: step3 finish calls onEnsured and clears key from wizard state', async () => {
    const onEnsured = vi.fn()
    const { root } = await renderWizard(onEnsured)
    roots.push(root)

    await goToStep2()

    const manualBtn = findButton((text) => text.includes('我已手动复制') || text.includes('copiedmanually'))
    await act(async () => {
      manualBtn!.click()
    })

    await vi.waitFor(() => {
      expect(document.body.textContent).toMatch(/配置已完成|Setup is complete/)
    })

    const finishBtn = findButton((text) => text === '开始使用' || text === 'Getstarted')
    expect(finishBtn).toBeTruthy()

    await act(async () => {
      finishBtn!.click()
    })

    expect(onEnsured).toHaveBeenCalledTimes(1)
    expect(document.body.textContent).not.toContain(MOCK_CREATED.plain_text_key)
  })
})
