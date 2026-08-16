import { describe, expect, it } from 'vitest'
import {
  ancestorDepartmentIds,
  buildDepartmentTree,
  departmentSearchMatchIds,
  departmentSelectOptions,
  expandIdsForDepartmentSearch,
  reconcileExpandedDepartmentIds,
} from './departmentTree' 
import type { DepartmentItem } from '@/api/adminRbac'

function dept(
  id: number,
  name: string,
  parent_id: number | null = null,
  sort_order = id,
): DepartmentItem {
  return {
    id,
    name,
    parent_id,
    sort_order,
    created_at: '2026-01-01T00:00:00',
    is_builtin: name === '根' || name === '未分配',
  }
}

describe('buildDepartmentTree', () => {
  it('builds nested hierarchy', () => {
    const departments = [dept(1, '根'), dept(2, '研发', 1), dept(3, '后端', 2)]
    const tree = buildDepartmentTree(departments)
    expect(tree).toHaveLength(1)
    expect(tree[0].children[0].children[0].id).toBe(3)
  })
})

describe('departmentSelectOptions', () => {
  it('flattens with depth prefix and excludes unassigned by default', () => {
    const departments = [
      dept(1, '根'),
      dept(2, '未分配', 1),
      dept(3, '研发', 1),
      dept(4, '后端', 3),
    ]
    const options = departmentSelectOptions(departments)
    expect(options.map((o) => o.label)).toEqual(['根', '— 研发', '—— 后端'])
    expect(options.map((o) => o.value)).toEqual([1, 3, 4])
  })

  it('can include unassigned when requested', () => {
    const departments = [dept(1, '根'), dept(2, '未分配', 1)]
    const options = departmentSelectOptions(departments, { excludeUnassigned: false })
    expect(options.some((o) => o.label.includes('未分配'))).toBe(true)
  })
})


describe('department tree navigation helpers', () => {
  const departments = [dept(1, '根'), dept(2, '研发', 1), dept(3, '后端', 2), dept(4, '财务', 1)]

  it('ancestorDepartmentIds returns root-to-node chain', () => {
    expect(ancestorDepartmentIds(departments, 3)).toEqual([1, 2, 3])
  })

  it('reconcileExpandedDepartmentIds drops invalid ids', () => {
    expect(reconcileExpandedDepartmentIds(departments, [1, 2, 999])).toEqual([1, 2])
  })

  it('departmentSearchMatchIds matches name and path', () => {
    expect(departmentSearchMatchIds(departments, '后端')).toEqual([3])
    expect(departmentSearchMatchIds(departments, '研发 / 后端')).toEqual([3])
  })

  it('expandIdsForDepartmentSearch includes ancestors only', () => {
    expect(expandIdsForDepartmentSearch(departments, [3])).toEqual([1, 2])
  })
})
