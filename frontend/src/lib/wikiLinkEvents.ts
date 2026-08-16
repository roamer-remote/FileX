export const WIKI_LINK_NAVIGATE = 'filex:wiki-link-navigate'

export type WikiLinkNavigateDetail = {
  fileId: number
  anchorId?: string
}

export function dispatchWikiLinkNavigate(detail: WikiLinkNavigateDetail) {
  window.dispatchEvent(new CustomEvent<WikiLinkNavigateDetail>(WIKI_LINK_NAVIGATE, { detail }))
}

/** 资料库索引页 `/knowledge-base` */
export function isKbIndexRoute(pathname: string): boolean {
  return pathname === '/knowledge-base'
}

/** 展示资料库文件列表（含 Tab）的路由；点选目录后无需再 navigate */
export function isKnowledgeFileListRoute(pathname: string): boolean {
  return pathname === '/' || pathname === '/files' || pathname.startsWith('/files/')
}

/** 目录选择需要打开资料页时，使用带面板参数的单次导航，避免先短暂渲染资料大厅。 */
export function knowledgeFileListPathForFolderSelection(pathname: string): string | null {
  return isKnowledgeFileListRoute(pathname) ? null : '/?panel=files'
}

/** 资料库大厅（仅根路径 `/`）；保持全幅大厅布局，不使用单页卡片壳 */
export function isKnowledgeLobbyRoute(pathname: string): boolean {
  return pathname === '/' || pathname === ''
}

/** AppLayout 内展示目录浮动面板（任意已登录界面均可弹出） */
export function showsFolderFloatingPanel(_pathname: string): boolean {
  return true
}

export const FOLDER_NAV_TO_FILE_LIST = 'filex:folder-nav-to-file-list'

/** 侧栏点选目录后：切到「文件」Tab 并刷新列表（同页重复点同一目录也会触发） */
export function dispatchFolderNavToFileList() {
  window.dispatchEvent(new CustomEvent(FOLDER_NAV_TO_FILE_LIST))
}
