import { useEffect } from 'react'
import { listNeedsKbStatusPoll } from '@/lib/kbStatusPoll'
import { useFilesStore } from '@/stores/filesStore'

const POLL_MS = 2000

/** 列表中存在待索引/提取中的文件时静默轮询（WebSocket 不可用时的兜底）。 */
export function useKbIndexStatusPoll(enabled: boolean) {
  const files = useFilesStore((s) => s.files)
  const loadFiles = useFilesStore((s) => s.loadFiles)

  const needsPoll = listNeedsKbStatusPoll(files)

  useEffect(() => {
    if (!enabled || !needsPoll) return
    const timer = setInterval(() => {
      void loadFiles({ silent: true })
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [enabled, needsPoll, loadFiles])
}
