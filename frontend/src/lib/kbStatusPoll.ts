import type { FileItem } from '@/api/files'
import { EXTRACTABLE_EXT, MARKDOWN_EXT, fileExt } from '@/components/FileListComponents'

function fileMayReceiveMdNote(file: FileItem): boolean {
  const ext = fileExt(file.original_name || file.filename || '')
  return EXTRACTABLE_EXT.has(ext) || MARKDOWN_EXT.has(ext)
}

/** 是否应对该文件轮询 KB 索引/提取状态（WebSocket 不可用时的兜底）。 */
export function fileNeedsKbStatusPoll(file: FileItem): boolean {
  if (file.index_status === 'pending' || file.index_status === 'indexing') {
    return true
  }
  if (file.extract_status === 'extracting') {
    return true
  }
  // 笔记已 ready 但 md_has_content 尚未同步（WS 丢失或最后一轮 poll 过早）
  if (file.extract_status === 'ready' && !file.md_has_content && fileMayReceiveMdNote(file)) {
    return true
  }
  if (file.extract_status !== 'pending') {
    return false
  }
  // 已有笔记且已索引：extract pending 多为脏状态，依赖 WS 增量更新即可
  if (file.has_md && file.index_status === 'ready') {
    return false
  }
  return true
}

export function listNeedsKbStatusPoll(files: FileItem[]): boolean {
  return files.some(fileNeedsKbStatusPoll)
}
