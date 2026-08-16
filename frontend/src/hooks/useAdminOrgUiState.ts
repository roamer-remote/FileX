import { useCallback, useEffect, useRef, useState } from 'react'
import type { DepartmentItem } from '@/api/adminRbac'
import {
  ancestorDepartmentIds,
  parentDepartmentId,
  reconcileExpandedDepartmentIds,
} from '@/lib/departmentTree'
import type { AdminOrgTab } from '@/lib/uiStateTypes'
import { defaultUiStateV1 } from '@/lib/uiStateTypes'
import { getCachedUiState, patchAdminOrgUiState, setCachedUiState } from '@/lib/uiStateSync'

function readAdminOrgFromCache() {
  return getCachedUiState()?.admin_org ?? defaultUiStateV1().admin_org
}

function syncCachedAdminOrg(partial: {
  active_tab?: AdminOrgTab
  selected_department_id?: number | null
  expanded_department_ids?: number[]
}) {
  const state = getCachedUiState()
  if (!state) return
  setCachedUiState({
    ...state,
    admin_org: { ...state.admin_org, ...partial },
  })
}

export function useAdminOrgUiState(departments: DepartmentItem[], departmentsLoaded: boolean) {
  const initial = readAdminOrgFromCache()
  const [activeTab, setActiveTab] = useState<AdminOrgTab>(initial.active_tab)
  const [selectedDeptId, setSelectedDeptId] = useState<number | null>(initial.selected_department_id)
  const [persistedExpandedIds, setPersistedExpandedIds] = useState<number[]>(
    initial.expanded_department_ids,
  )
  const [scrollToDeptId, setScrollToDeptId] = useState<number | null>(null)
  const hydratedRef = useRef(false)

  // hydrate：loadDepartments 成功后 reconcile zombie id / expanded；仅更新内存态，不 debounce PATCH（规格 S-1）
  useEffect(() => {
    if (!departmentsLoaded || hydratedRef.current) return
    hydratedRef.current = true

    const cached = readAdminOrgFromCache()
    let selected = cached.selected_department_id
    if (selected != null && !departments.some((d) => d.id === selected)) {
      selected = null
    }

    let expanded = reconcileExpandedDepartmentIds(departments, cached.expanded_department_ids)
    if (selected != null) {
      const ancestors = ancestorDepartmentIds(departments, selected)
      expanded = reconcileExpandedDepartmentIds(departments, [...expanded, ...ancestors])
    }

    setActiveTab(cached.active_tab)
    setSelectedDeptId(selected)
    setPersistedExpandedIds(expanded)
    syncCachedAdminOrg({
      active_tab: cached.active_tab,
      selected_department_id: selected,
      expanded_department_ids: expanded,
    })

    if (selected != null) {
      setScrollToDeptId(selected)
    }
  }, [departments, departmentsLoaded])

  const setActiveTabAndSync = useCallback((tab: AdminOrgTab) => {
    setActiveTab(tab)
    syncCachedAdminOrg({ active_tab: tab })
    patchAdminOrgUiState({ active_tab: tab })
  }, [])

  const selectDepartment = useCallback(
    (id: number | null) => {
      setSelectedDeptId(id)
      syncCachedAdminOrg({ selected_department_id: id })
      patchAdminOrgUiState({ selected_department_id: id })
      if (id != null) {
        setScrollToDeptId(id)
        setPersistedExpandedIds((prev) => {
          const ancestors = ancestorDepartmentIds(departments, id)
          const next = reconcileExpandedDepartmentIds(departments, [...prev, ...ancestors])
          syncCachedAdminOrg({ expanded_department_ids: next })
          patchAdminOrgUiState({ expanded_department_ids: next })
          return next
        })
      }
    },
    [departments],
  )

  const updatePersistedExpanded = useCallback(
    (ids: number[]) => {
      const next = reconcileExpandedDepartmentIds(departments, ids)
      setPersistedExpandedIds(next)
      syncCachedAdminOrg({ expanded_department_ids: next })
      patchAdminOrgUiState({ expanded_department_ids: next })
    },
    [departments],
  )

  const afterDepartmentDeleted = useCallback(
    (deletedId: number) => {
      const remaining = departments.filter((d) => d.id !== deletedId)
      const parentId = parentDepartmentId(departments, deletedId)
      const nextSelected = selectedDeptId === deletedId ? parentId : selectedDeptId
      const nextExpanded = reconcileExpandedDepartmentIds(
        remaining,
        persistedExpandedIds.filter((id) => id !== deletedId),
      )
      setSelectedDeptId(nextSelected)
      setPersistedExpandedIds(nextExpanded)
      syncCachedAdminOrg({
        selected_department_id: nextSelected,
        expanded_department_ids: nextExpanded,
      })
      patchAdminOrgUiState({
        selected_department_id: nextSelected,
        expanded_department_ids: nextExpanded,
      })
      if (nextSelected != null) setScrollToDeptId(nextSelected)
    },
    [departments, persistedExpandedIds, selectedDeptId],
  )

  const clearScrollTarget = useCallback(() => {
    setScrollToDeptId(null)
  }, [])

  return {
    activeTab,
    setActiveTabAndSync,
    selectedDeptId,
    selectDepartment,
    persistedExpandedIds,
    updatePersistedExpanded,
    afterDepartmentDeleted,
    scrollToDeptId,
    clearScrollTarget,
  }
}
