import { describe, expect, it } from 'vitest'
import { patchFromChanged } from './Settings'

describe('admin Settings patchFromChanged', () => {
  it('defers openai-compatible provider save until base URL and model are present', () => {
    expect(
      patchFromChanged(
        { kb_post_llm_provider: 'openai_compatible' },
        {
          kb_post_llm_provider: 'openai_compatible',
          kb_post_llm_base_url: '',
          kb_post_llm_model: '',
          kb_post_llm_timeout_sec: 60,
          kb_post_llm_json_mode: 'auto',
        },
      ),
    ).toEqual({})
  })

  it('saves provider, endpoint, model, json mode, timeout, and key as one payload', () => {
    expect(
      patchFromChanged(
        { kb_post_llm_model: 'deepseek-chat' },
        {
          kb_post_llm_provider: 'openai_compatible',
          kb_post_llm_base_url: 'https://llm.example.com/v1',
          kb_post_llm_model: 'deepseek-chat',
          kb_post_llm_api_key: 'sk-new',
          kb_post_llm_timeout_sec: 45,
          kb_post_llm_json_mode: 'response_format',
        },
      ),
    ).toEqual({
      kb_post_llm_provider: 'openai_compatible',
      kb_post_llm_base_url: 'https://llm.example.com/v1',
      kb_post_llm_model: 'deepseek-chat',
      kb_post_llm_api_key: 'sk-new',
      kb_post_llm_timeout_sec: 45,
      kb_post_llm_json_mode: 'response_format',
    })
  })

  it('saves Ollama API key from the embed model settings panel', () => {
    expect(
      patchFromChanged({
        ollama_chat_model: 'deepseek-v4-flash:cloud',
        ollama_api_key: 'ollama-cloud-key',
      }),
    ).toEqual({
      ollama_chat_model: 'deepseek-v4-flash:cloud',
      ollama_api_key: 'ollama-cloud-key',
    })
  })

  it('does not overwrite a saved Ollama API key with an empty field', () => {
    expect(
      patchFromChanged({
        ollama_api_key: '',
      }),
    ).toEqual({})
  })

  it('clears a saved Ollama API key', () => {
    expect(
      patchFromChanged({
        clear_ollama_api_key: true,
      }),
    ).toEqual({
      clear_ollama_api_key: true,
    })
  })

  it('saves RAGAS online evaluation settings', () => {
    expect(
      patchFromChanged({
        kb_ragas_online_eval_enabled: true,
        kb_ragas_online_eval_sample_rate: 0.4,
        kb_ragas_online_eval_timeout_seconds: 3000,
      }),
    ).toEqual({
      kb_ragas_online_eval_enabled: true,
      kb_ragas_online_eval_sample_rate: 0.4,
      kb_ragas_online_eval_timeout_seconds: 3000,
    })
  })

  it('saves an isolated RAGAS LLM configuration with context budgets', () => {
    expect(
      patchFromChanged(
        { kb_ragas_llm_model: 'deepseek-chat', kb_ragas_llm_api_key: 'sk-ragas' },
        {
          kb_ragas_llm_provider: 'openai_compatible',
          kb_ragas_llm_base_url: 'https://ragas.example.com/v1',
          kb_ragas_llm_model: 'deepseek-chat',
          kb_ragas_llm_api_key: 'sk-ragas',
          kb_ragas_llm_timeout_seconds: 90,
          kb_ragas_eval_concurrency: 2,
          kb_ragas_eval_context_max_count: 12,
          kb_ragas_eval_context_max_chars_per_item: 1500,
          kb_ragas_eval_context_max_total_chars: 12000,
        },
      ),
    ).toEqual({
      kb_ragas_llm_provider: 'openai_compatible',
      kb_ragas_llm_base_url: 'https://ragas.example.com/v1',
      kb_ragas_llm_model: 'deepseek-chat',
      kb_ragas_llm_api_key: 'sk-ragas',
      kb_ragas_llm_timeout_seconds: 90,
      kb_ragas_eval_concurrency: 2,
      kb_ragas_eval_context_max_count: 12,
      kb_ragas_eval_context_max_chars_per_item: 1500,
      kb_ragas_eval_context_max_total_chars: 12000,
    })
  })

  it('does not save an incomplete OpenAI-compatible RAGAS configuration', () => {
    expect(
      patchFromChanged(
        { kb_ragas_llm_provider: 'openai_compatible' },
        {
          kb_ragas_llm_provider: 'openai_compatible',
          kb_ragas_llm_base_url: '',
          kb_ragas_llm_model: '',
          kb_ragas_llm_timeout_seconds: 90,
        },
      ),
    ).toEqual({})
  })
})


describe('admin Settings patchFromChanged (153 voice playback TTL)', () => {
  it('saves a valid TTL value', () => {
    expect(
      patchFromChanged({ kb_voice_notify_playback_ttl_seconds: 30 }),
    ).toEqual({ kb_voice_notify_playback_ttl_seconds: 30 })
  })

  it('rounds non-integer TTL values', () => {
    expect(
      patchFromChanged({ kb_voice_notify_playback_ttl_seconds: 33.7 }),
    ).toEqual({ kb_voice_notify_playback_ttl_seconds: 34 })
  })

  it('rejects out-of-range TTL values by returning empty patch', () => {
    expect(patchFromChanged({ kb_voice_notify_playback_ttl_seconds: 0 })).toEqual({})
    expect(patchFromChanged({ kb_voice_notify_playback_ttl_seconds: 3601 })).toEqual({})
  })

  it('rejects non-finite TTL values by returning empty patch', () => {
    expect(patchFromChanged({ kb_voice_notify_playback_ttl_seconds: 'abc' as never })).toEqual({})
    expect(patchFromChanged({ kb_voice_notify_playback_ttl_seconds: Number.NaN as never })).toEqual({})
  })
})

describe('pdf-inspector switch patch', () => {
  it('maps kb_pdf_inspector_enabled boolean change into the payload', () => {
    expect(patchFromChanged({ kb_pdf_inspector_enabled: true })).toEqual({
      kb_pdf_inspector_enabled: true,
    })
  })

  it('maps kb_pdf_inspector_enabled false change into the payload', () => {
    expect(patchFromChanged({ kb_pdf_inspector_enabled: false })).toEqual({
      kb_pdf_inspector_enabled: false,
    })
  })
})
