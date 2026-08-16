import { Tooltip } from 'antd'
import { FlTableMarqueeText } from '@/components/FileListComponents'
import { storageFilenameDisplayName } from '@/utils/storageFilename'
import '@/components/FileList.css'

type Props = {
  filename: string | null | undefined
  fallback?: string
}

/** MQ 监控：走马灯展示去前缀文件名，悬停 Tooltip 显示存储全名 */
export default function MqStorageFilenameCell({ filename, fallback = '—' }: Props) {
  const full = filename?.trim() || fallback
  if (full === fallback && !filename?.trim()) {
    return <span>{fallback}</span>
  }
  const display = storageFilenameDisplayName(full)
  return (
    <Tooltip title={full} placement="topLeft" mouseEnterDelay={0.35}>
      <FlTableMarqueeText text={display} className="mq-filename-marquee" tooltip={false} />
    </Tooltip>
  )
}
