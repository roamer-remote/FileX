import { describe, expect, it, vi } from 'vitest'
import { formatAdminLogDetail } from './logDetail'

describe('formatAdminLogDetail', () => {
  it('translates known key labels while preserving model values and paths', () => {
    const t = vi.fn((key: string) => ({
      'admin.logs.detailFields.llmModels': 'Model',
      'admin.logs.detailFields.llmModelPaths': 'Model path',
      'admin.logs.detailFields.llmGpuUsed': 'GPU used',
      'admin.logs.values.true': 'yes',
    })[key] ?? key)

    expect(
      formatAdminLogDetail(
        'llm_models=qwen3.5%3A9b llm_model_paths=%2Froot%2Fmodels%2Fblob%20with%20spaces llm_gpu_used=true',
        t,
      ),
    ).toBe('Model=qwen3.5:9b Model path=/root/models/blob with spaces GPU used=yes')
  })
})
