import type { DepartmentItem } from '@/api/adminRbac'

export type DepartmentTreeNode = DepartmentItem & { children: DepartmentTreeNode[] }

export function buildDepartmentTree(departments: DepartmentItem[]): DepartmentTreeNode[] {
  const byParent = new Map<number | null, DepartmentItem[]>()
  for (const d of departments) {
    const key = d.parent_id ?? null
    const list = byParent.get(key) ?? []
    list.push(d)
    byParent.set(key, list)
  }
  const attach = (parentId: number | null): DepartmentTreeNode[] => {
    const items = (byParent.get(parentId) ?? []).slice().sort((a, b) => {
      const so = a.sort_order - b.sort_order
      if (so !== 0) return so
      return a.id - b.id
    })
    return items.map((d) => ({
      ...d,
      children: attach(d.id),
    }))
  }
  return attach(null)
}

export type DepartmentSelectOption = {
  value: number
  label: string
  disabled?: boolean
}

export function departmentSelectOptions(
  departments: DepartmentItem[],
  opts?: { excludeUnassigned?: boolean },
): DepartmentSelectOption[] {
  const excludeUnassigned = opts?.excludeUnassigned ?? true
  const tree = buildDepartmentTree(departments)
  const out: DepartmentSelectOption[] = []

  const walk = (nodes: DepartmentTreeNode[], depth: number) => {
    for (const node of nodes) {
      if (excludeUnassigned && node.name === '未分配') continue
      const prefix = depth > 0 ? `${'—'.repeat(depth)} ` : ''
      out.push({
        value: node.id,
        label: `${prefix}${node.name}`,
        disabled: node.name === '未分配',
      })
      if (node.children.length) walk(node.children, depth + 1)
    }
  }

  walk(tree, 0)
  return out
}


export function departmentById(departments: DepartmentItem[], id: number): DepartmentItem | undefined {
  return departments.find((d) => d.id === id)
}

export function ancestorDepartmentIds(departments: DepartmentItem[], deptId: number): number[] {
  const chain: number[] = []
  let current = departmentById(departments, deptId)
  const seen = new Set<number>()
  while (current) {
    if (seen.has(current.id)) break
    seen.add(current.id)
    chain.unshift(current.id)
    if (current.parent_id == null) break
    current = departmentById(departments, current.parent_id)
  }
  return chain
}

export function departmentPathLabel(
  departments: DepartmentItem[],
  deptId: number,
  separator = ' / ',
): string {
  const parts: string[] = []
  for (const id of ancestorDepartmentIds(departments, deptId)) {
    const d = departmentById(departments, id)
    if (d) parts.push(d.name)
  }
  return parts.join(separator)
}

export function expandableDepartmentIds(tree: DepartmentTreeNode[]): number[] {
  const ids: number[] = []
  const walk = (nodes: DepartmentTreeNode[]) => {
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

export function reconcileExpandedDepartmentIds(
  departments: DepartmentItem[],
  stored: number[],
): number[] {
  const tree = buildDepartmentTree(departments)
  const expandable = new Set(expandableDepartmentIds(tree))
  return stored.filter((id) => expandable.has(id))
}

export function departmentTextMatchesQuery(text: string, query: string): boolean {
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

export function departmentMatchesSearch(
  departments: DepartmentItem[],
  deptId: number,
  query: string,
): boolean {
  const q = query.trim()
  if (!q) return true
  const d = departmentById(departments, deptId)
  if (!d) return false
  if (departmentTextMatchesQuery(d.name, q)) return true
  return departmentTextMatchesQuery(departmentPathLabel(departments, deptId), q)
}

export function departmentSearchMatchIds(departments: DepartmentItem[], query: string): number[] {
  const q = query.trim()
  if (!q) return []
  return departments.filter((d) => departmentMatchesSearch(departments, d.id, q)).map((d) => d.id)
}

export function expandIdsForDepartmentSearch(
  departments: DepartmentItem[],
  matchIds: number[],
): number[] {
  const ids = new Set<number>()
  for (const id of matchIds) {
    for (const aid of ancestorDepartmentIds(departments, id)) {
      if (aid !== id) ids.add(aid)
    }
  }
  return [...ids]
}

export function departmentNodeVisibleInSearch(
  node: DepartmentTreeNode,
  departments: DepartmentItem[],
  query: string,
): boolean {
  const q = query.trim()
  if (!q) return true
  if (departmentMatchesSearch(departments, node.id, q)) return true
  return node.children.some((c) => departmentNodeVisibleInSearch(c, departments, query))
}

export function displayExpandedDepartmentIds(
  persisted: number[],
  searchExpanded: number[],
  departments: DepartmentItem[],
): number[] {
  const merged = [...new Set([...persisted, ...searchExpanded])]
  return reconcileExpandedDepartmentIds(departments, merged)
}

export function parentDepartmentId(
  departments: DepartmentItem[],
  deptId: number,
): number | null {
  const d = departmentById(departments, deptId)
  return d?.parent_id ?? null
}
