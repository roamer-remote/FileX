import { useEffect, useMemo, useState } from 'react'
import { ClusterOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { Empty, Input, Spin, Tag, Tree } from 'antd'
import type { DataNode } from 'antd/es/tree'
import type { DepartmentItem } from '@/api/adminRbac'
import {
  buildDepartmentTree,
  departmentNodeVisibleInSearch,
  departmentSearchMatchIds,
  displayExpandedDepartmentIds,
  expandIdsForDepartmentSearch,
  reconcileExpandedDepartmentIds,
  type DepartmentTreeNode,
} from '@/lib/departmentTree'

type DepartmentTreePanelProps = {
  departments: DepartmentItem[]
  loading: boolean
  selectedDeptId: number | null
  persistedExpandedIds: number[]
  scrollToDeptId: number | null
  onSelectDept: (id: number | null) => void
  onPersistedExpandedChange: (ids: number[]) => void
  onScrollComplete: () => void
}

function departmentsToTreeData(
  nodes: DepartmentTreeNode[],
  departments: DepartmentItem[],
  query: string,
  builtinLabel: string,
): DataNode[] {
  return nodes
    .filter((n) => departmentNodeVisibleInSearch(n, departments, query))
    .map((d) => {
      const isLeaf = d.children.length === 0
      return {
        key: String(d.id),
        title: (
          <span className="admin-org-dept-tree-title" data-dept-nav-id={d.id}>
            {isLeaf ? (
              <ClusterOutlined className="admin-org-dept-leaf-icon" aria-hidden />
            ) : null}
            <span className="admin-org-dept-tree-label">
              {d.name}
              {d.is_builtin ? (
                <Tag style={{ marginInlineStart: 8 }}>{builtinLabel}</Tag>
              ) : null}
            </span>
          </span>
        ),
        children: d.children.length
          ? departmentsToTreeData(d.children, departments, query, builtinLabel)
          : undefined,
      }
    })
}

export default function DepartmentTreePanel({
  departments,
  loading,
  selectedDeptId,
  persistedExpandedIds,
  scrollToDeptId,
  onSelectDept,
  onPersistedExpandedChange,
  onScrollComplete,
}: DepartmentTreePanelProps) {
  const { t } = useTranslation()
  const [searchInput, setSearchInput] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(searchInput), 280)
    return () => window.clearTimeout(timer)
  }, [searchInput])

  const deptTree = useMemo(() => buildDepartmentTree(departments), [departments])
  const treeData = useMemo(
    () => departmentsToTreeData(deptTree, departments, debouncedSearch, t('adminRbac.builtin')),
    [deptTree, departments, debouncedSearch, t],
  )

  const searchExpandedIds = useMemo(() => {
    const q = debouncedSearch.trim()
    if (!q) return []
    return expandIdsForDepartmentSearch(
      departments,
      departmentSearchMatchIds(departments, q),
    )
  }, [departments, debouncedSearch])

  const displayExpandedIds = useMemo(
    () => displayExpandedDepartmentIds(persistedExpandedIds, searchExpandedIds, departments),
    [departments, persistedExpandedIds, searchExpandedIds],
  )

  const searchHasMatch = !debouncedSearch.trim() || treeData.length > 0

  useEffect(() => {
    const q = debouncedSearch.trim()
    if (!q || !searchHasMatch) return
    const matchIds = departmentSearchMatchIds(departments, q)
    if (!matchIds.length) return
    const firstId = matchIds[0]
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        document
          .querySelector(`[data-dept-nav-id="${firstId}"]`)
          ?.scrollIntoView({ block: 'nearest' })
      })
    })
  }, [debouncedSearch, departments, searchHasMatch])

  useEffect(() => {
    if (scrollToDeptId == null || loading) return
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        document
          .querySelector(`[data-dept-nav-id="${scrollToDeptId}"]`)
          ?.scrollIntoView({ block: 'nearest' })
        onScrollComplete()
      })
    })
  }, [scrollToDeptId, loading, onScrollComplete])

  return (
    <div className="admin-org-tree-panel">
      <Input
        allowClear
        placeholder={t('adminRbac.departmentSearchPlaceholder')}
        value={searchInput}
        onChange={(e) => setSearchInput(e.target.value)}
        className="admin-org-tree-search"
      />
      <Spin spinning={loading}>
        <div className="admin-org-tree-scroll">
          {!loading && debouncedSearch.trim() && !searchHasMatch ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('adminRbac.departmentSearchNoMatch')}
              className="admin-org-tree-empty"
            />
          ) : (
            <Tree
              treeData={treeData}
              selectedKeys={selectedDeptId != null ? [String(selectedDeptId)] : []}
              expandedKeys={displayExpandedIds.map(String)}
              onSelect={(keys) => {
                const k = keys[0]
                onSelectDept(k != null ? Number(k) : null)
              }}
              onExpand={(_keys, { expanded, node }) => {
                const id = Number(node.key)
                const next = expanded
                  ? [...persistedExpandedIds, id]
                  : persistedExpandedIds.filter((x) => x !== id)
                onPersistedExpandedChange(reconcileExpandedDepartmentIds(departments, next))
              }}
              blockNode
            />
          )}
        </div>
      </Spin>
    </div>
  )
}
