/**
 * @vitest-environment jsdom
 */

import { act } from 'react-dom/test-utils'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App, ConfigProvider, Form } from 'antd'
import { I18nextProvider } from 'react-i18next'
import i18n from '@/i18n'
import AdminOllamaSettingsTabs from './AdminOllamaSettingsTabs'

function TestHost({ hasApiKey = false, provider = 'openai_compatible' }: { hasApiKey?: boolean; provider?: string }) {
  const [form] = Form.useForm()
  return (
    <ConfigProvider>
      <App>
        <I18nextProvider i18n={i18n}>
          <Form
            form={form}
            initialValues={{
              kb_post_llm_provider: provider,
              kb_post_llm_base_url: 'https://api.example.com/v1',
              kb_post_llm_model: 'deepseek-chat',
              kb_post_llm_api_key: '',
              kb_post_llm_has_api_key: hasApiKey,
              ollama_api_key: '',
              ollama_has_api_key: hasApiKey,
              clear_ollama_api_key: false,
              kb_post_llm_timeout_sec: 60,
              kb_post_llm_json_mode: 'auto',
              clear_kb_post_llm_api_key: false,
              kb_raptor_enabled: false,
            }}
          >
            <AdminOllamaSettingsTabs
              testingOllama={false}
              onTestOllama={vi.fn()}
              kbRaptorEnabled={false}
              onRaptorEnabledChange={vi.fn()}
            />
          </Form>
        </I18nextProvider>
      </App>
    </ConfigProvider>
  )
}

async function renderTabs(hasApiKey = false, provider = 'openai_compatible') {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  await act(async () => {
    root.render(<TestHost hasApiKey={hasApiKey} provider={provider} />)
  })
  return root
}

describe('AdminOllamaSettingsTabs', () => {
  const roots: Root[] = []

  beforeEach(() => {
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

  it('renders post-processing LLM settings fields', async () => {
    roots.push(await renderTabs())

    expect(document.body.textContent).toContain('后处理 LLM')
    expect(document.body.textContent).toContain('后处理 LLM Provider')
    expect(document.body.textContent).toContain('OpenAI 兼容 Base URL')
    expect(document.body.textContent).toContain('OpenAI 兼容模型')
    expect(document.body.textContent).toContain('OpenAI 兼容 API Key')
    expect(document.body.textContent).toContain('Ollama API Key')
    expect(document.body.textContent).toContain('JSON 输出模式')
  })

  it('shows clear API key switch only when a key is configured', async () => {
    roots.push(await renderTabs(false, 'openai_compatible'))
    expect(document.body.textContent).not.toContain('清除已保存 API Key')

    for (const root of roots) {
      act(() => {
        root.unmount()
      })
    }
    roots.length = 0
    document.body.innerHTML = ''

    roots.push(await renderTabs(true))
    expect(document.body.textContent).toContain('已配置；留空不修改')
    expect(document.body.textContent).toContain('清除已保存 API Key')
    expect(document.body.textContent).toContain('清除已保存 Ollama API Key')
  })

  it('disables provider-specific fields when reusing the chat model', async () => {
    roots.push(await renderTabs(false, 'openai_compatible'))
    expect((document.querySelector('input[placeholder="https://api.example.com/v1"]') as HTMLInputElement).disabled).toBe(false)
    expect((document.querySelector('input[placeholder="gpt-4o-mini"]') as HTMLInputElement).disabled).toBe(false)
    expect((document.querySelector('input[placeholder="sk-..."]') as HTMLInputElement).disabled).toBe(false)

    for (const root of roots) {
      act(() => {
        root.unmount()
      })
    }
    roots.length = 0
    document.body.innerHTML = ''

    roots.push(await renderTabs(false, 'ollama'))
    expect((document.querySelector('input[placeholder="https://api.example.com/v1"]') as HTMLInputElement).disabled).toBe(true)
    expect((document.querySelector('input[placeholder="gpt-4o-mini"]') as HTMLInputElement).disabled).toBe(true)
    expect((document.querySelector('input[placeholder="sk-..."]') as HTMLInputElement).disabled).toBe(true)
  })
})
