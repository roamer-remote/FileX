import { describe, expect, it } from 'vitest'
import {
  ancestorFolderIds,
  buildFolderTree,
  expandedFolderIdsForSelection,
  FOLDER_NAV_ID_MY_MATERIALS,
  folderNavDataId,
  folderPanelContentHeight,
  folderPanelDimensions,
  folderPathLabel,
  folderSearchMatchIds,
  folderSelectionLabel,
  folderTextMatchesQuery,
  expandIdsForFolderSearch,
  folderDisplayLabel,
  measureTreeLayout,
  myMaterialsMatchesSearch,
  reconcileExpandedFolderIds,
  virtualRootDisplayLabel,
} from './folderTree'
import type { FolderItem } from '@/api/folders'

function folder(id: number, name: string, parent_id: number | null = null): FolderItem {
  return { id, name, parent_id, sort_order: id, user_id: 1, created_at: '2026-01-01T00:00:00' }
}

describe('folderDisplayLabel', () => {
  it('appends count when positive', () => {
    expect(folderDisplayLabel('发票', 5)).toBe('发票 (5)')
  })

  it('omits count when zero or missing', () => {
    expect(folderDisplayLabel('发票', 0)).toBe('发票')
    expect(folderDisplayLabel('发票')).toBe('发票')
  })
})

describe('buildFolderTree', () => {
  it('builds three levels', () => {
    const folders = [folder(1, 'A'), folder(2, 'B', 1), folder(3, 'C', 2)]
    const tree = buildFolderTree(folders)
    expect(tree).toHaveLength(1)
    expect(tree[0].children[0].children[0].id).toBe(3)
  })
})

describe('folderPathLabel', () => {
  it('joins ancestor names', () => {
    const folders = [folder(1, 'A'), folder(2, 'B', 1), folder(3, 'C', 2)]
    expect(folderPathLabel(folders, 3)).toBe('A / B / C')
  })
})

describe('reconcileExpandedFolderIds', () => {
  it('keeps only expandable nodes that still exist', () => {
    const folders = [
      folder(1, 'A'),
      folder(2, 'B'),
      folder(10, 'A1', 1),
      folder(20, 'B1', 2),
    ]
    const tree = buildFolderTree(folders)
    expect(reconcileExpandedFolderIds(tree, [1, 2, 99])).toEqual([1, 2])
  })
})

describe('expandedFolderIdsForSelection', () => {
  it('expands ancestors for deep selection', () => {
    const folders = [folder(1, 'A'), folder(10, 'A1', 1), folder(100, 'A1a', 10)]
    const tree = buildFolderTree(folders)
    expect(expandedFolderIdsForSelection(tree, 100, folders)).toEqual([1, 10])
  })
})

describe('ancestorFolderIds', () => {
  it('returns root to leaf chain', () => {
    const folders = [folder(1, 'A'), folder(10, 'A1', 1)]
    expect(ancestorFolderIds(folders, 10)).toEqual([1, 10])
  })
})

describe('measureTreeLayout', () => {
  it('returns zeros for empty tree', () => {
    expect(measureTreeLayout([], [])).toEqual({
      maxDepth: 1,
      maxVisibleRows: 0,
      widestLevel: 0,
      longestLabelChars: 0,
    })
  })

  it('counts visible rows when expanded', () => {
    const folders = [folder(1, 'A'), folder(2, 'B', 1)]
    const tree = buildFolderTree(folders)
    const layout = measureTreeLayout(tree, [1])
    expect(layout.maxVisibleRows).toBe(2)
    expect(layout.maxDepth).toBe(2)
  })
})

describe('folderNavDataId', () => {
  it('maps all selection to virtual root nav id', () => {
    expect(folderNavDataId('all')).toBe(FOLDER_NAV_ID_MY_MATERIALS)
    expect(folderNavDataId('uncategorized')).toBe('uncategorized')
    expect(folderNavDataId(42)).toBe('42')
  })
})

describe('folderSelectionLabel', () => {
  it('uses myMaterials label for all selection', () => {
    const t = (key: string) => (key === 'folders.myMaterials' ? '我的资料' : key)
    expect(folderSelectionLabel('all', [], t)).toBe('我的资料')
  })

  it('uses custom root label when provided', () => {
    const t = (key: string) => (key === 'folders.myMaterials' ? '我的资料' : key)
    expect(folderSelectionLabel('all', [], t, '研发资料库')).toBe('研发资料库')
  })
})

describe('virtualRootDisplayLabel', () => {
  const t = (key: string) => (key === 'folders.myMaterials' ? '我的资料' : key)

  it('uses workspace name for shared kind', () => {
    expect(virtualRootDisplayLabel({ kind: 'shared', name: '  研发资料库  ' }, t)).toBe('研发资料库')
  })

  it('falls back to myMaterials for personal kind', () => {
    expect(virtualRootDisplayLabel({ kind: 'personal', name: '张三的空间' }, t)).toBe('我的资料')
  })

  it('falls back to myMaterials when workspace missing', () => {
    expect(virtualRootDisplayLabel(undefined, t)).toBe('我的资料')
  })
})

describe('myMaterialsMatchesSearch', () => {
  it('matches my materials label', () => {
    expect(myMaterialsMatchesSearch('资料', '我的资料')).toBe(true)
    expect(myMaterialsMatchesSearch('xyz', '我的资料')).toBe(false)
  })
})

describe('folderPanelContentHeight', () => {
  it('collapsed virtual root is shorter than expanded', () => {
    const layout = {
      maxDepth: 2,
      maxVisibleRows: 3,
      widestLevel: 1,
      longestLabelChars: 8,
    }
    const expanded = folderPanelContentHeight(layout, { virtualRootExpanded: true })
    const collapsed = folderPanelContentHeight(layout, { virtualRootExpanded: false })
    expect(collapsed).toBeLessThan(expanded)
  })
})

describe('folderPanelDimensions', () => {
  it('height follows visible rows; caps at viewport max', () => {
    const layout = {
      maxDepth: 3,
      maxVisibleRows: 5,
      widestLevel: 2,
      longestLabelChars: 12,
    }
    const fewRows = folderPanelDimensions({ ...layout, maxVisibleRows: 2 }, { viewportHeight: 900 })
    const manyRows = folderPanelDimensions({ ...layout, maxVisibleRows: 30 }, { viewportHeight: 900 })
    expect(fewRows.width).toBe(manyRows.width)
    expect(fewRows.height).toBeLessThan(manyRows.height)
    expect(manyRows.contentOverflows).toBe(true)
    expect(fewRows.height).toBeLessThanOrEqual(420)
  })
})

describe('folderTextMatchesQuery', () => {
  it('matches substring', () => {
    expect(folderTextMatchesQuery('发票', '票')).toBe(true)
  })

  it('matches subsequence fuzzy', () => {
    expect(folderTextMatchesQuery('学习资料', '学料')).toBe(true)
  })

  it('rejects unrelated query', () => {
    expect(folderTextMatchesQuery('java', 'python')).toBe(false)
  })
})

describe('folderSearchMatchIds', () => {
  it('finds by folder name', () => {
    const folders = [folder(1, '个人资料'), folder(37, '发票', 1)]
    expect(folderSearchMatchIds(folders, '发票')).toEqual([37])
  })

  it('finds by full path', () => {
    const folders = [folder(1, '个人资料'), folder(37, '发票', 1)]
    expect(folderSearchMatchIds(folders, '个人资料 / 发票')).toEqual([37])
  })

  it('expandIdsForFolderSearch opens ancestors', () => {
    const folders = [folder(1, '个人资料'), folder(37, '发票', 1)]
    expect(expandIdsForFolderSearch(folders, [37])).toEqual([1])
  })
})

describe('buildFolderTree sort_order', () => {
  it('sorts siblings by sort_order', () => {
    const folders = [
      folder(1, 'C', null),
      folder(2, 'A', null),
      folder(3, 'B', null),
    ]
    folders[0].sort_order = 2
    folders[1].sort_order = 0
    folders[2].sort_order = 1
    const tree = buildFolderTree(folders)
    expect(tree.map((n) => n.name)).toEqual(['A', 'B', 'C'])
  })
})
