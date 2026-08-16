/** 笔记 Modal 正文是否应因 has_md 从 false→true 而重新拉取（例如后台生成完成）。 */
export function shouldReloadMdOnHasMdReady(
  prevHasMd: boolean | null,
  nextHasMd: boolean,
  isDirty: boolean,
): boolean {
  return prevHasMd === false && nextHasMd && !isDirty
}

/** 稳定化 MD 正文加载 effect 的依赖键（避免 store 轮询替换 FileItem 引用导致反复 reload）。 */
export function mdNoteContentLoadKey(input: {
  open: boolean
  fileId: number | undefined
  hasMd: boolean
  reloadToken: number
  scrollToAnchorId: string | null
  adminMdApi: boolean
  effectiveReadOnly: boolean
}): string | null {
  if (!input.open || input.fileId == null) return null
  return [
    input.fileId,
    input.hasMd,
    input.reloadToken,
    input.scrollToAnchorId ?? '',
    input.adminMdApi ? '1' : '0',
    input.effectiveReadOnly ? '1' : '0',
  ].join(':')
}
