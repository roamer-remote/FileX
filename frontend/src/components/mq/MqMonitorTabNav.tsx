import { Tabs } from 'antd'
import type { MqMonitorTab } from '@/hooks/useMqMonitorTab'

type MqMonitorTabNavProps = {
  tab: MqMonitorTab
  onChange: (tab: MqMonitorTab) => void
  factoryLabel: string
  classicLabel: string
}

/** 仅 Tab 导航条（内容区由父级按 activeKey 切换） */
export default function MqMonitorTabNav({
  tab,
  onChange,
  factoryLabel,
  classicLabel,
}: MqMonitorTabNavProps) {
  return (
    <Tabs
      className="mq-monitor-tabs mq-monitor-tabs--nav-only"
      activeKey={tab}
      onChange={(key) => onChange(key as MqMonitorTab)}
      items={[
        { key: 'factory', label: factoryLabel, children: null },
        { key: 'classic', label: classicLabel, children: null },
      ]}
    />
  )
}
