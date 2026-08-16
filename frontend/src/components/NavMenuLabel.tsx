import type { ComponentType, ReactNode } from 'react'
import {
  ApartmentOutlined,
  AppstoreOutlined,
  AuditOutlined,
  ClusterOutlined,
  ControlOutlined,
  DatabaseOutlined,
  FileOutlined,
  FolderOpenOutlined,
  HomeOutlined,
  RadarChartOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  HistoryOutlined,
  LineChartOutlined,
  FileSearchOutlined,
} from '@ant-design/icons'
import './NavMenuLabel.css'

export type NavMenuIconKey =
  | 'myFiles'
  | 'knowledgeIndex'
  | 'workspaces'
  | 'userRegistry'
  | 'allFiles'
  | 'lobby'
  | 'systemLogs'
  | 'skillEditor'
  | 'systemSettings'
  | 'kbPreferences'
  | 'mqMonitor'
  | 'organization'
  | 'enterpriseRoles'
  | 'enterpriseData'
  | 'adminOps'
  | 'agentRuns'
  | 'kbSearchEval'
  | 'qualityWorkbench'

type IconComponent = ComponentType<{ className?: string }>

const NAV_MENU_ICONS: Record<NavMenuIconKey, IconComponent> = {
  myFiles: FileOutlined,
  knowledgeIndex: DatabaseOutlined,
  workspaces: ApartmentOutlined,
  userRegistry: TeamOutlined,
  allFiles: FolderOpenOutlined,
  lobby: HomeOutlined,
  systemLogs: AuditOutlined,
  skillEditor: ThunderboltOutlined,
  systemSettings: SettingOutlined,
  kbPreferences: ControlOutlined,
  mqMonitor: RadarChartOutlined,
  organization: ClusterOutlined,
  enterpriseRoles: SafetyCertificateOutlined,
  enterpriseData: ApartmentOutlined,
  adminOps: AppstoreOutlined,
  agentRuns: HistoryOutlined,
  kbSearchEval: LineChartOutlined,
  qualityWorkbench: FileSearchOutlined,
}

type Props = {
  icon: NavMenuIconKey
  children: ReactNode
}

export default function NavMenuLabel({ icon, children }: Props) {
  const Icon = NAV_MENU_ICONS[icon]
  return (
    <span className={`nav-menu-label nav-menu-label--${icon}`}>
      <Icon className="nav-menu-label__icon" aria-hidden />
      <span className="nav-menu-label__text">{children}</span>
    </span>
  )
}
