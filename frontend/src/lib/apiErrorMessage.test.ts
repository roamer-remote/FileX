import { beforeAll, describe, expect, it } from 'vitest'

let resolveApiErrorDetail: (detail: string) => string
let i18n: Awaited<typeof import('@/i18n')>['default']

beforeAll(async () => {
  Object.defineProperty(globalThis, 'localStorage', {
    value: {
      getItem: (key: string) => (key === 'filex_locale' ? 'zh-CN' : null),
      setItem: () => {},
      removeItem: () => {},
    },
    configurable: true,
  })
  i18n = (await import('@/i18n')).default
  resolveApiErrorDetail = (await import('./apiErrorMessage')).resolveApiErrorDetail
  await i18n.changeLanguage('zh-CN')
})

describe('resolveApiErrorDetail', () => {
  it('maps folder error codes to zh-CN', () => {
    expect(resolveApiErrorDetail('folder.root_create_forbidden')).toContain('根')
    expect(resolveApiErrorDetail('folder.depth_exceeded')).toContain('10')
  })

  it('maps legacy Chinese folder messages', () => {
    expect(resolveApiErrorDetail('无权创建根级目录')).toBe(
      resolveApiErrorDetail('folder.root_create_forbidden'),
    )
  })

  it('returns unknown detail as-is', () => {
    expect(resolveApiErrorDetail('custom backend message')).toBe('custom backend message')
  })

  it('maps folder error codes to en', async () => {
    await i18n.changeLanguage('en')
    expect(resolveApiErrorDetail('folder.root_create_forbidden')).toContain('root-level')
    await i18n.changeLanguage('zh-CN')
  })

  it('maps workspace backup error codes', async () => {
    expect(resolveApiErrorDetail('workspaceBackup.sharedNotSupported')).toContain('共享空间')
    await i18n.changeLanguage('en')
    expect(resolveApiErrorDetail('workspaceBackup.notOwner')).toContain('personal workspace')
    expect(resolveApiErrorDetail('workspaceBackup.tooLarge')).toContain('size limit')
    await i18n.changeLanguage('zh-CN')
  })

  it('maps workspace backup tooLarge structured detail with sizes', async () => {
    const { resolveApiErrorDetailUnknown } = await import('./apiErrorMessage')
    const msg = resolveApiErrorDetailUnknown({
      code: 'workspaceBackup.tooLarge',
      total_bytes: 200,
      max_bytes: 50,
    })
    expect(msg).toContain('200')
    expect(msg).toContain('50')
    await i18n.changeLanguage('en')
    const enMsg = resolveApiErrorDetailUnknown({
      code: 'workspaceBackup.tooLarge',
      total_bytes: 1048576 + 100,
      max_bytes: 1048576,
    })
    expect(enMsg).toContain('1.00 MB')
    expect(enMsg).toContain('exceeds')
    await i18n.changeLanguage('zh-CN')
  })

  it('maps workspace backup tooLarge structured detail with file_count', async () => {
    const { resolveApiErrorDetailUnknown } = await import('./apiErrorMessage')
    const msg = resolveApiErrorDetailUnknown({
      code: 'workspaceBackup.tooLarge',
      total_bytes: 200,
      max_bytes: 50,
      file_count: 3,
    })
    expect(msg).toContain('3')
    expect(msg).toContain('200')
    await i18n.changeLanguage('en')
    const enMsg = resolveApiErrorDetailUnknown({
      code: 'workspaceBackup.tooLarge',
      total_bytes: 200,
      max_bytes: 50,
      file_count: 3,
    })
    expect(enMsg).toContain('3 files')
    await i18n.changeLanguage('zh-CN')
  })
})

describe('formatApiError fetch-style errors', () => {
  it('maps Error.message workspace backup codes via i18n', async () => {
    const { formatApiError } = await import('@/api/index')
    await i18n.changeLanguage('en')
    expect(formatApiError(new Error('workspaceBackup.tooLarge'))).toContain('size limit')
    await i18n.changeLanguage('zh-CN')
    expect(formatApiError(new Error('workspaceBackup.tooLarge'))).toContain('上限')
  })

  it('maps fetch-style workspace backup tooLarge payload', async () => {
    const { formatApiError } = await import('@/api/index')
    const err = new Error('workspaceBackup.tooLarge') as Error & {
      workspaceBackupDetail: { code: string; total_bytes: number; max_bytes: number }
    }
    err.workspaceBackupDetail = {
      code: 'workspaceBackup.tooLarge',
      total_bytes: 200,
      max_bytes: 50,
    }
    const msg = formatApiError(err)
    expect(msg).toContain('200')
    expect(msg).toContain('50')
  })
})
