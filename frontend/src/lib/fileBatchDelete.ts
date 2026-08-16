type DeleteFileFn = (id: number, options?: { deferKbIndexSync?: boolean }) => Promise<unknown>
type RebuildKnowledgeBaseIndexFn = () => Promise<unknown>
type GetKnowledgeBaseIndexFn = () => Promise<string | null>

export type FileBatchDeleteResult = {
  ok: number
  fail: number
  rebuildFailed: boolean
}

export async function runFileBatchDelete({
  selectedIds,
  deleteFile,
  rebuildKnowledgeBaseIndex,
}: {
  selectedIds: number[]
  deleteFile: DeleteFileFn
  rebuildKnowledgeBaseIndex: RebuildKnowledgeBaseIndexFn
  getKnowledgeBaseIndex?: GetKnowledgeBaseIndexFn
}): Promise<FileBatchDeleteResult> {
  const results = await Promise.allSettled(
    selectedIds.map((id) => deleteFile(id, { deferKbIndexSync: true })),
  )
  const ok = results.filter((r) => r.status === 'fulfilled').length
  const fail = selectedIds.length - ok
  let rebuildFailed = false
  if (ok > 0) {
    try {
      await rebuildKnowledgeBaseIndex()
    } catch {
      rebuildFailed = true
    }
  }
  return { ok, fail, rebuildFailed }
}
