import { describe, expect, it, vi } from 'vitest'
import { runFileBatchDelete } from './fileBatchDelete'

describe('runFileBatchDelete', () => {
  it('deletes selected files without reading the knowledge-base index first and rebuilds once', async () => {
    const deleteFile = vi.fn().mockResolvedValue(undefined)
    const rebuildKnowledgeBaseIndex = vi.fn().mockResolvedValue(undefined)
    const getKnowledgeBaseIndex = vi.fn().mockRejectedValue(new Error('corrupt index'))

    const result = await runFileBatchDelete({
      selectedIds: [1, 2, 3],
      deleteFile,
      rebuildKnowledgeBaseIndex,
      getKnowledgeBaseIndex,
    })

    expect(getKnowledgeBaseIndex).not.toHaveBeenCalled()
    expect(deleteFile).toHaveBeenCalledTimes(3)
    expect(deleteFile).toHaveBeenNthCalledWith(1, 1, { deferKbIndexSync: true })
    expect(deleteFile).toHaveBeenNthCalledWith(2, 2, { deferKbIndexSync: true })
    expect(deleteFile).toHaveBeenNthCalledWith(3, 3, { deferKbIndexSync: true })
    expect(rebuildKnowledgeBaseIndex).toHaveBeenCalledTimes(1)
    expect(result).toEqual({ ok: 3, fail: 0, rebuildFailed: false })
  })

  it('reports successful deletes even when the follow-up rebuild fails', async () => {
    const deleteFile = vi.fn().mockResolvedValue(undefined)
    const rebuildKnowledgeBaseIndex = vi.fn().mockRejectedValue(new Error('rebuild failed'))

    const result = await runFileBatchDelete({
      selectedIds: [4],
      deleteFile,
      rebuildKnowledgeBaseIndex,
    })

    expect(result).toEqual({ ok: 1, fail: 0, rebuildFailed: true })
  })
})
