import api from './index'

const adminOpts = { skipErrorToast: true } as const

export type DepartmentItem = {
  id: number
  name: string
  parent_id: number | null
  sort_order: number
  created_at: string
  is_builtin: boolean
}

export type GroupItem = {
  id: number
  name: string
  description: string | null
  created_at: string
}

export type EnterpriseRoleItem = {
  id: number
  slug: string
  name: string
  description: string | null
  is_builtin: boolean
  is_active: boolean
  created_at: string
}

export type EnterpriseRoleDeleteSummary = {
  deleted_user_role_assignments: number
  deleted_acl_rows: number
  message: string
}

export type UserOrgGroupItem = {
  id: number
  name: string
}

export type AdminUserOrg = {
  user_id: number
  primary_department_id: number
  primary_department_name: string
  groups: UserOrgGroupItem[]
}

export type WorkspaceMemberRoles = {
  user_id: number
  role_ids: number[]
  role_slugs: string[]
}

export type FolderAclEntryItem = {
  id: number
  folder_id: number | null
  subject_type: 'user' | 'role' | 'group' | 'department'
  subject_id: number
  permission: 'list' | 'read' | 'write' | 'manage'
  created_at: string
  updated_at: string
}

export type FolderAclEntryInput = {
  folder_id: number | null
  subject_type: 'user' | 'role' | 'group' | 'department'
  subject_id: number
  permission: 'list' | 'read' | 'write' | 'manage'
}

export type FolderAclPutSummary = {
  upserted: number
  updated: number
}

export function listAdminDepartments() {
  return api.get<DepartmentItem[]>('/admin/departments', adminOpts)
}

export function createAdminDepartment(body: { name: string; parent_id: number; sort_order?: number }) {
  return api.post<DepartmentItem>('/admin/departments', body, adminOpts)
}

export function updateAdminDepartment(
  id: number,
  body: { name?: string; parent_id?: number | null; sort_order?: number },
) {
  return api.put<DepartmentItem>(`/admin/departments/${id}`, body, adminOpts)
}

export function deleteAdminDepartment(id: number) {
  return api.delete(`/admin/departments/${id}`, adminOpts)
}

export function listAdminGroups() {
  return api.get<GroupItem[]>('/admin/groups', adminOpts)
}

export function createAdminGroup(body: { name: string; description?: string | null }) {
  return api.post<GroupItem>('/admin/groups', body, adminOpts)
}

export function updateAdminGroup(id: number, body: { name?: string; description?: string | null }) {
  return api.put<GroupItem>(`/admin/groups/${id}`, body, adminOpts)
}

export function deleteAdminGroup(id: number) {
  return api.delete(`/admin/groups/${id}`, adminOpts)
}

export function listEnterpriseRoles() {
  return api.get<EnterpriseRoleItem[]>('/admin/enterprise-roles', adminOpts)
}

export function createEnterpriseRole(body: { slug: string; name: string; description?: string | null }) {
  return api.post<EnterpriseRoleItem>('/admin/enterprise-roles', body, adminOpts)
}

export function updateEnterpriseRole(
  id: number,
  body: { name?: string; description?: string | null; is_active?: boolean },
) {
  return api.put<EnterpriseRoleItem>(`/admin/enterprise-roles/${id}`, body, adminOpts)
}

export function deleteEnterpriseRole(id: number) {
  return api.delete<EnterpriseRoleDeleteSummary>(`/admin/enterprise-roles/${id}`, adminOpts)
}

export function getAdminUserOrg(userId: number) {
  return api.get<AdminUserOrg>(`/admin/users/${userId}/org`, adminOpts)
}

export function putAdminUserOrg(userId: number, body: { primary_department_id: number; group_ids: number[] }) {
  return api.put<AdminUserOrg>(`/admin/users/${userId}/org`, body, adminOpts)
}

export function getWorkspaceMemberRoles(workspaceId: number, userId: number) {
  return api.get<WorkspaceMemberRoles>(
    `/admin/workspaces/${workspaceId}/members/${userId}/roles`,
    adminOpts,
  )
}

export function putWorkspaceMemberRoles(workspaceId: number, userId: number, roleIds: number[]) {
  return api.put<WorkspaceMemberRoles>(
    `/admin/workspaces/${workspaceId}/members/${userId}/roles`,
    { role_ids: roleIds },
    adminOpts,
  )
}

export function listWorkspaceFolderAcl(workspaceId: number) {
  return api.get<FolderAclEntryItem[]>(`/admin/workspaces/${workspaceId}/folder-acl`, adminOpts)
}

export function putWorkspaceFolderAcl(workspaceId: number, entries: FolderAclEntryInput[]) {
  return api.put<FolderAclPutSummary>(
    `/admin/workspaces/${workspaceId}/folder-acl`,
    { entries },
    adminOpts,
  )
}
