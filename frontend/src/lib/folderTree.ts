import type { FolderItem } from '@/api/folders'

export type FolderSelection = 'all' | 'uncategorized' | number

export const FOLDER_ID_UNCATEGORIZED = 0

/** 虚拟根「我的资料」— `data-folder-nav-id` / scroll-into-view（非 DB id） */
export const FOLDER_NAV_ID_MY_MATERIALS = 'my-materials'

export type FolderTreeNode = FolderItem & { children: FolderTreeNode[] }

export type FolderTreeRoot = FolderTreeNode

export function folderDisplayLabel(name: string, directFileCount?: number): string {
  if (directFileCount != null && directFileCount > 0) {
    return `${name} (${directFileCount})`
  }
  return name
}

export function buildFolderTree(folders: FolderItem[]): FolderTreeNode[] {
  const byParent = new Map<number | null, FolderItem[]>()
  for (const f of folders) {
    const key = f.parent_id ?? null
    const list = byParent.get(key) ?? []
    list.push(f)
    byParent.set(key, list)
  }
  const attach = (parentId: number | null): FolderTreeNode[] => {
    const items = (byParent.get(parentId) ?? []).slice().sort((a, b) => {
      const so = a.sort_order - b.sort_order
      if (so !== 0) return so
      return a.id - b.id
    })
    return items.map((f) => ({
      ...f,
      children: attach(f.id),
    }))
  }
  return attach(null)
}

export function folderById(folders: FolderItem[], id: number): FolderItem | undefined {
  return folders.find((x) => x.id === id)
}

export function ancestorFolderIds(folders: FolderItem[], folderId: number): number[] {
  const chain: number[] = []
  let current = folderById(folders, folderId)
  const seen = new Set<number>()
  while (current) {
    if (seen.has(current.id)) break
    seen.add(current.id)
    chain.unshift(current.id)
    if (current.parent_id == null) break
    current = folderById(folders, current.parent_id)
  }
  return chain
}

export function folderPathLabel(
  folders: FolderItem[],
  folderId: number,
  separator = ' / ',
): string {
  const parts: string[] = []
  for (const id of ancestorFolderIds(folders, folderId)) {
    const f = folderById(folders, id)
    if (f) parts.push(f.name)
  }
  return parts.join(separator)
}

export type VirtualRootWorkspace = {
  kind: 'personal' | 'shared'
  name: string
}

/** 虚拟根展示名：企业资料库用空间自定义名，个人空间仍用「我的资料」 */
export function virtualRootDisplayLabel(
  workspace: VirtualRootWorkspace | null | undefined,
  t: (key: string) => string,
): string {
  if (workspace?.kind === 'shared') {
    const name = workspace.name.trim()
    if (name) return name
  }
  return t('folders.myMaterials')
}

export function folderSelectionLabel(
  selection: FolderSelection,
  folders: FolderItem[],
  t: (key: string) => string,
  rootLabel?: string,
): string {
  const fallbackRoot = rootLabel ?? t('folders.myMaterials')
  if (selection === 'all') return fallbackRoot
  if (selection === 'uncategorized') return t('folders.uncategorized')
  const f = folders.find((x) => x.id === selection)
  if (!f) return fallbackRoot
  return folderPathLabel(folders, f.id)
}

export function expandableFolderIds(tree: FolderTreeNode[]): number[] {
  const ids: number[] = []
  const walk = (nodes: FolderTreeNode[]) => {
    for (const n of nodes) {
      if (n.children.length > 0) {
        ids.push(n.id)
        walk(n.children)
      }
    }
  }
  walk(tree)
  return ids
}

export function reconcileExpandedFolderIds(
  tree: FolderTreeNode[],
  stored: number[],
): number[] {
  const expandable = new Set(expandableFolderIds(tree))
  return stored.filter((id) => expandable.has(id))
}

export function folderNavDataId(selection: FolderSelection): string | null {
  if (selection === 'all') return FOLDER_NAV_ID_MY_MATERIALS
  if (selection === 'uncategorized') return 'uncategorized'
  return String(selection)
}


/** 目录名/路径模糊匹配：子串（忽略大小写）或按序子序列 */
export function folderTextMatchesQuery(text: string, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const t = text.toLowerCase()
  if (t.includes(q)) return true
  let ti = 0
  for (let qi = 0; qi < q.length; qi += 1) {
    const idx = t.indexOf(q[qi], ti)
    if (idx < 0) return false
    ti = idx + 1
  }
  return true
}

export function folderMatchesSearch(
  folders: FolderItem[],
  folderId: number,
  query: string,
): boolean {
  const q = query.trim()
  if (!q) return true
  const f = folderById(folders, folderId)
  if (!f) return false
  if (folderTextMatchesQuery(f.name, q)) return true
  return folderTextMatchesQuery(folderPathLabel(folders, folderId), q)
}

/** 按名称或完整路径匹配的所有目录 id */
export function folderSearchMatchIds(folders: FolderItem[], query: string): number[] {
  const q = query.trim()
  if (!q) return []
  return folders.filter((f) => folderMatchesSearch(folders, f.id, q)).map((f) => f.id)
}

/** 展开搜索命中目录所需的祖先 id */
export function expandIdsForFolderSearch(
  folders: FolderItem[],
  matchIds: number[],
): number[] {
  const ids = new Set<number>()
  for (const id of matchIds) {
    for (const aid of ancestorFolderIds(folders, id)) {
      if (aid !== id) ids.add(aid)
    }
  }
  return [...ids]
}

export function folderNodeVisibleInSearch(
  node: FolderTreeNode,
  folders: FolderItem[],
  query: string,
): boolean {
  const q = query.trim()
  if (!q) return true
  if (folderMatchesSearch(folders, node.id, q)) return true
  return node.children.some((c) => folderNodeVisibleInSearch(c, folders, q))
}

export function uncategorizedMatchesSearch(
  query: string,
  uncategorizedLabel: string,
): boolean {
  const q = query.trim()
  if (!q) return true
  return folderTextMatchesQuery(uncategorizedLabel, q)
}

export function myMaterialsMatchesSearch(query: string, myMaterialsLabel: string): boolean {
  const q = query.trim()
  if (!q) return true
  return folderTextMatchesQuery(myMaterialsLabel, q)
}

/** 目录搜索时是否展示虚拟根及其可展开子树 */
export function virtualRootVisibleInSearch(
  query: string,
  myMaterialsLabel: string,
  uncategorizedLabel: string,
  tree: FolderTreeNode[],
  folders: FolderItem[],
): boolean {
  const q = query.trim()
  if (!q) return true
  if (myMaterialsMatchesSearch(q, myMaterialsLabel)) return true
  if (uncategorizedMatchesSearch(q, uncategorizedLabel)) return true
  return tree.some((n) => folderNodeVisibleInSearch(n, folders, q))
}

export function defaultExpandedFolderIds(
  tree: FolderTreeNode[],
  selection: FolderSelection,
  folders: FolderItem[],
): number[] {
  const ids = new Set(expandableFolderIds(tree))
  if (typeof selection === 'number') {
    for (const id of ancestorFolderIds(folders, selection)) {
      ids.add(id)
    }
  }
  return reconcileExpandedFolderIds(tree, [...ids])
}

export function expandedFolderIdsForSelection(
  tree: FolderTreeNode[],
  selection: FolderSelection,
  folders: FolderItem[],
): number[] {
  if (typeof selection !== 'number') return []
  return ancestorFolderIds(folders, selection).filter((id) => {
    const find = (nodes: FolderTreeNode[]): FolderTreeNode | undefined => {
      for (const n of nodes) {
        if (n.id === id) return n
        const hit = find(n.children)
        if (hit) return hit
      }
      return undefined
    }
    const node = find(tree)
    return node != null && node.children.length > 0
  })
}

export type FolderTreeLayout = {
  maxDepth: number
  maxVisibleRows: number
  widestLevel: number
  longestLabelChars: number
}

function walkTreeMetrics(
  nodes: FolderTreeNode[],
  depth: number,
  expanded: Set<number>,
  acc: { rows: number; levelCounts: Map<number, number>; maxLabel: number },
) {
  for (const n of nodes) {
    acc.rows += 1
    acc.levelCounts.set(depth, (acc.levelCounts.get(depth) ?? 0) + 1)
    acc.maxLabel = Math.max(acc.maxLabel, n.name.length)
    if (expanded.has(n.id) && n.children.length > 0) {
      walkTreeMetrics(n.children, depth + 1, expanded, acc)
    }
  }
}

export function measureTreeLayout(
  tree: FolderTreeNode[],
  expandedFolderIds: number[],
): FolderTreeLayout {
  const expanded = new Set(expandedFolderIds)
  const acc = { rows: 0, levelCounts: new Map<number, number>(), maxLabel: 0 }
  walkTreeMetrics(tree, 1, expanded, acc)
  let maxDepth = 1
  let widestLevel = 0
  for (const [level, count] of acc.levelCounts) {
    maxDepth = Math.max(maxDepth, level)
    widestLevel = Math.max(widestLevel, count)
  }
  return {
    maxDepth,
    maxVisibleRows: acc.rows,
    widestLevel,
    longestLabelChars: acc.maxLabel,
  }
}

/** 面板允许的最大高度（超出后仅在 body 内滚动） */
export function folderPanelMaxHeight(viewportHeight?: number): number {
  const vh = viewportHeight ?? (typeof window !== 'undefined' ? window.innerHeight : 800)
  return Math.min(Math.max(280, Math.floor(vh * 0.52)), 420)
}

/** 顶栏 + 搜索 + 工具条 + 底栏 + 内边距（不含树行） */
export const FOLDER_PANEL_CHROME_PX = 148

export function folderPanelContentHeight(
  layout: FolderTreeLayout,
  opts?: { includeUncategorized?: boolean; virtualRootExpanded?: boolean },
): number {
  const virtualRootExpanded = opts?.virtualRootExpanded !== false
  if (!virtualRootExpanded) {
    return FOLDER_PANEL_CHROME_PX + 36
  }
  const includeUncategorized = opts?.includeUncategorized !== false
  const rows = layout.maxVisibleRows + (includeUncategorized ? 1 : 0) + 1
  return FOLDER_PANEL_CHROME_PX + rows * 36
}

export function folderPanelDimensions(
  layout: FolderTreeLayout,
  opts?: { includeUncategorized?: boolean; virtualRootExpanded?: boolean; viewportHeight?: number },
): { width: number; height: number; contentOverflows: boolean } {
  const virtualRootExpanded = opts?.virtualRootExpanded !== false
  const depthForWidth = layout.maxDepth + (virtualRootExpanded ? 1 : 0)
  const width = Math.min(
    520,
    Math.max(280, 80 + depthForWidth * 20 + Math.min(320, layout.longestLabelChars * 9)),
  )
  const maxH = folderPanelMaxHeight(opts?.viewportHeight)
  const contentH = folderPanelContentHeight(layout, opts)
  const height = Math.min(maxH, contentH)
  return { width, height, contentOverflows: contentH > maxH }
}

/** @deprecated 使用 folderPanelMaxHeight */
export function folderPanelHeight(viewportHeight?: number): number {
  return folderPanelMaxHeight(viewportHeight)
}

export function showKnowledgeGraphTabs(selection: FolderSelection): boolean {
  return selection === 'all'
}

export function uploadTargetFolderId(selection: FolderSelection): number | undefined {
  if (typeof selection === 'number') return selection
  return undefined
}

export function folderDisplayNameForFile(
  folderId: number | null | undefined,
  folders: FolderItem[],
  t: (key: string) => string,
): string {
  if (folderId == null) return t('folders.uncategorized')
  const f = folders.find((x) => x.id === folderId)
  if (!f) return t('fileList.folderUnknown')
  return folderPathLabel(folders, f.id)
}

export function reconcileExpandedRootIds(tree: FolderTreeNode[], stored: number[]) {
  return reconcileExpandedFolderIds(tree, stored)
}

export function expandableRootIds(tree: FolderTreeNode[]) {
  return expandableFolderIds(tree)
}

export function defaultExpandedRootIds(tree: FolderTreeNode[], selection: FolderSelection) {
  return defaultExpandedFolderIds(tree, selection, [])
}

export function expandedRootIdsForSelection(tree: FolderTreeNode[], selection: FolderSelection) {
  return expandedFolderIdsForSelection(tree, selection, [])
}
