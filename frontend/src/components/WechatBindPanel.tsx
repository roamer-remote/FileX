import { useCallback, useState } from 'react'
import WechatLoginPanel from '@/components/WechatLoginPanel'

type WechatBindPanelProps = {
  onSuccess?: () => void | Promise<void>
}

/** 账户绑定专用：固定 iframe 区域，绑定轮询期间禁止刷新二维码。 */
export default function WechatBindPanel({ onSuccess }: WechatBindPanelProps) {
  const [binding, setBinding] = useState(false)

  const handleBindSuccess = useCallback(
    async (_token: string) => {
      setBinding(true)
      try {
        await onSuccess?.()
      } finally {
        setBinding(false)
      }
    },
    [onSuccess],
  )

  return (
    <div className="wechat-bind-panel wechat-embed-host">
      <div className="wechat-bind-main">
        <WechatLoginPanel mode="bind" lockRefresh={binding} onSuccess={handleBindSuccess} />
      </div>
    </div>
  )
}
