import FileUpload from './FileUpload'
import SidebarStats from './SidebarStats'
import SidebarMqQueue from './SidebarMqQueue'
import FolderPanelTrigger from './FolderPanelTrigger'
import WorkspaceSwitcher from './WorkspaceSwitcher'
import { SidebarNavAccordionProvider } from './SidebarNav'
import './Sidebar.css'

export default function Sidebar() {
  return (
    <SidebarNavAccordionProvider>
    <div className="sidebar">
      <div className="sidebar-primary-block">
        <WorkspaceSwitcher />
        <FolderPanelTrigger />
        <div className="sidebar-upload-section">
          <div className="sidebar-upload">
            <FileUpload />
          </div>
        </div>
      </div>
      <div className="sidebar-panels">
        <SidebarMqQueue />
        <SidebarStats />
      </div>
    </div>
    </SidebarNavAccordionProvider>
  )
}
