import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import {
  App,
  Alert,
  Button,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Radio,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { FileItem } from '@/api/files'
import { getAdminSystemSettings } from '@/api/admin'
import {
  getWorkspaceMemberRoles,
  listAdminDepartments,
  listEnterpriseRoles,
  listAdminGroups,
  listWorkspaceFolderAcl,
  putWorkspaceFolderAcl,
  putWorkspaceMemberRoles,
  type DepartmentItem,
  type EnterpriseRoleItem,
  type FolderAclEntryInput,
  type FolderAclEntryItem,
  type GroupItem,
} from '@/api/adminRbac'
import {
  createWorkspaceGrant,
  deleteWorkspaceGrant,
  downloadGlobalSearchAuditExport,
  downloadWorkspaceSearchAuditExport,
  getAdminFiles,
  getAdminUsers,
  listAdminMdVersions,
  listAdminWorkspaces,
  listWorkspaceGrants,
  listWorkspaceMembers,
  listWorkspaceSearchAudit,
  removeWorkspaceMember,
  restoreAdminMdVersion,
  setAdminFilePublishStatus,
  updateAdminWorkspace,
  upsertWorkspaceMember,
  type AdminUserOption,
  type AdminWorkspaceItem,
  type KbSearchAuditItem,
  type MdVersionItem,
  type ResourceGrantItem,
  type WorkspaceMemberItem,
} from '@/api/adminWorkspaces'
import RoleNotPermissionPackNotice from '@/components/admin/RoleNotPermissionPackNotice'
import { DeleteActionIcon } from '@/components/DeleteActionIcon'
import { formatApiError, isFormValidationError } from '@/api/index'
import { formatDate } from '@/utils'
import './AdminPage.css'

const ROLES = ['viewer', 'contributor', 'curator', 'admin', 'auditor'] as const
const SUBJECT_TYPES = ['user', 'role', 'group', 'department'] as const
const ACL_PERMISSIONS = ['list', 'read', 'write', 'manage'] as const

type AclFormValues = {
  folder_scope: 'root' | 'folder'
  folder_id?: number
  subject_type: (typeof SUBJECT_TYPES)[number]
  subject_id: number
  permission: (typeof ACL_PERMISSIONS)[number]
}

function entriesToInputs(entries: FolderAclEntryItem[]): FolderAclEntryInput[] {
  return entries.map((e) => ({
    folder_id: e.folder_id,
    subject_type: e.subject_type,
    subject_id: e.subject_id,
    permission: e.permission,
  }))
}

export default function AdminWorkspaceDetailPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>()
  const wsId = Number(workspaceId)
  const { t } = useTranslation()
  const { message, modal } = App.useApp()

  const [workspace, setWorkspace] = useState<AdminWorkspaceItem | null>(null)
  const [workspaceLoadState, setWorkspaceLoadState] = useState<'loading' | 'ready' | 'error' | 'not_found'>(
    'loading',
  )
  const [workspaceLoadError, setWorkspaceLoadError] = useState<string | null>(null)
  const [enterpriseRbacEnabled, setEnterpriseRbacEnabled] = useState(false)
  const [users, setUsers] = useState<AdminUserOption[]>([])
  const [rename, setRename] = useState('')
  const [savingName, setSavingName] = useState(false)

  const [members, setMembers] = useState<WorkspaceMemberItem[]>([])
  const [memberRoleSlugs, setMemberRoleSlugs] = useState<Record<number, string[]>>({})
  const [enterpriseRoles, setEnterpriseRoles] = useState<EnterpriseRoleItem[]>([])
  const [memberOpen, setMemberOpen] = useState(false)
  const [memberEditingUserId, setMemberEditingUserId] = useState<number | null>(null)
  const [memberForm] = Form.useForm<{ user_id: number; role: string; role_ids: number[] }>()

  const [grants, setGrants] = useState<ResourceGrantItem[]>([])
  const [grantOpen, setGrantOpen] = useState(false)
  const [grantForm] = Form.useForm<{
    resource_type: 'file' | 'folder'
    resource_id: number
    grantee_user_id: number
    permission: 'view' | 'edit'
  }>()

  const [aclEntries, setAclEntries] = useState<FolderAclEntryItem[]>([])
  const [aclLoading, setAclLoading] = useState(false)
  const [departments, setDepartments] = useState<DepartmentItem[]>([])
  const [groups, setGroups] = useState<GroupItem[]>([])
  const [aclModalOpen, setAclModalOpen] = useState(false)
  const [aclEditingIndex, setAclEditingIndex] = useState<number | null>(null)
  const [aclForm] = Form.useForm<AclFormValues>()
  const aclSubjectType = Form.useWatch('subject_type', aclForm)
  const aclFolderScope = Form.useWatch('folder_scope', aclForm)
  const [aclSaving, setAclSaving] = useState(false)

  const [files, setFiles] = useState<FileItem[]>([])
  const [filesTotal, setFilesTotal] = useState(0)
  const [filesPage, setFilesPage] = useState(1)
  const [filesLoading, setFilesLoading] = useState(false)

  const [audit, setAudit] = useState<KbSearchAuditItem[]>([])
  const [auditLoading, setAuditLoading] = useState(false)

  const [versionFile, setVersionFile] = useState<FileItem | null>(null)
  const [versions, setVersions] = useState<MdVersionItem[]>([])
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [previewVersion, setPreviewVersion] = useState<MdVersionItem | null>(null)

  const showFolderAclTab = workspace?.kind === 'shared' && enterpriseRbacEnabled

  const loadWorkspace = useCallback(async () => {
    setWorkspaceLoadState('loading')
    setWorkspaceLoadError(null)
    try {
      const res = await listAdminWorkspaces()
      const found = res.data.find((w) => w.id === wsId) ?? null
      if (!found) {
        setWorkspace(null)
        setWorkspaceLoadState('not_found')
        return
      }
      setWorkspace(found)
      setRename(found.name)
      setWorkspaceLoadState('ready')
    } catch (e) {
      setWorkspace(null)
      const detail = formatApiError(e)
      setWorkspaceLoadError(detail)
      setWorkspaceLoadState('error')
      message.error(detail)
    }
  }, [wsId, message])

  const loadMemberEnterpriseRoles = useCallback(
    async (memberRows: WorkspaceMemberItem[]) => {
      if (!enterpriseRbacEnabled || workspace?.kind !== 'shared') {
        setMemberRoleSlugs({})
        return
      }
      try {
        const results = await Promise.all(
          memberRows.map(async (m) => {
            const res = await getWorkspaceMemberRoles(wsId, m.user_id)
            return [m.user_id, res.data.role_slugs] as const
          }),
        )
        setMemberRoleSlugs(Object.fromEntries(results))
      } catch (e) {
        message.error(formatApiError(e))
      }
    },
    [wsId, message, enterpriseRbacEnabled, workspace?.kind],
  )

  const loadMembers = useCallback(async () => {
    try {
      const res = await listWorkspaceMembers(wsId)
      setMembers(res.data)
      await loadMemberEnterpriseRoles(res.data)
    } catch (e) {
      message.error(formatApiError(e))
    }
  }, [wsId, message, loadMemberEnterpriseRoles])

  const loadGrants = useCallback(async () => {
    try {
      const res = await listWorkspaceGrants(wsId)
      setGrants(res.data)
    } catch (e) {
      message.error(formatApiError(e))
    }
  }, [wsId, message])

  const loadAcl = useCallback(async () => {
    if (!showFolderAclTab) return
    setAclLoading(true)
    try {
      const res = await listWorkspaceFolderAcl(wsId)
      setAclEntries(res.data)
    } catch (e) {
      message.error(formatApiError(e))
    } finally {
      setAclLoading(false)
    }
  }, [wsId, message, showFolderAclTab])

  const loadAclLookups = useCallback(async () => {
    try {
      const [deptRes, groupRes, roleRes] = await Promise.all([
        listAdminDepartments(),
        listAdminGroups(),
        listEnterpriseRoles(),
      ])
      setDepartments(deptRes.data)
      setGroups(groupRes.data)
      setEnterpriseRoles(roleRes.data)
    } catch (e) {
      message.error(formatApiError(e))
    }
  }, [message])

  const loadFiles = useCallback(async () => {
    setFilesLoading(true)
    try {
      const res = await getAdminFiles({ workspace_id: wsId, page: filesPage, page_size: 20 })
      setFiles(res.data.items)
      setFilesTotal(res.data.total)
    } catch (e) {
      message.error(formatApiError(e))
    } finally {
      setFilesLoading(false)
    }
  }, [wsId, filesPage, message])

  const loadAudit = useCallback(async () => {
    setAuditLoading(true)
    try {
      const res = await listWorkspaceSearchAudit(wsId, 200)
      setAudit(res.data)
    } catch (e) {
      message.error(formatApiError(e))
    } finally {
      setAuditLoading(false)
    }
  }, [wsId, message])

  useEffect(() => {
    if (!Number.isFinite(wsId)) return
    void loadWorkspace()
    void getAdminSystemSettings()
      .then((r) => setEnterpriseRbacEnabled(!!r.data.enterprise_rbac_enabled))
      .catch((e) => message.error(formatApiError(e)))
    void getAdminUsers()
      .then((r) => setUsers(r.data.items))
      .catch((e) => message.error(formatApiError(e)))
    void listEnterpriseRoles()
      .then((r) => setEnterpriseRoles(r.data))
      .catch((e) => message.error(formatApiError(e)))
    void loadMembers()
    void loadAudit()
    void loadAclLookups()
  }, [wsId, loadWorkspace, loadMembers, loadAudit, loadAclLookups, message])

  useEffect(() => {
    if (!Number.isFinite(wsId)) return
    if (workspace?.kind === 'shared' && enterpriseRbacEnabled) return
    void loadGrants()
  }, [wsId, workspace?.kind, enterpriseRbacEnabled, loadGrants])

  useEffect(() => {
    if (!Number.isFinite(wsId)) return
    void loadFiles()
  }, [wsId, loadFiles])

  useEffect(() => {
    if (showFolderAclTab) void loadAcl()
  }, [showFolderAclTab, loadAcl])

  useEffect(() => {
    if (workspace?.kind === 'shared' && enterpriseRbacEnabled && members.length) {
      void loadMemberEnterpriseRoles(members)
    }
    // members 由 loadMembers 内同步加载角色，此处仅响应 RBAC 开关切换
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace?.kind, enterpriseRbacEnabled, loadMemberEnterpriseRoles])

  async function saveName() {
    if (!workspace || !rename.trim()) return
    setSavingName(true)
    try {
      const res = await updateAdminWorkspace(workspace.id, rename.trim())
      setWorkspace(res.data)
      message.success(t('adminWorkspaces.saved'))
    } catch (e) {
      message.error(formatApiError(e))
    } finally {
      setSavingName(false)
    }
  }

  async function openMemberModal(row?: WorkspaceMemberItem) {
    if (row) {
      setMemberEditingUserId(row.user_id)
      memberForm.setFieldsValue({ user_id: row.user_id, role: row.role, role_ids: [] })
      if (workspace?.kind === 'shared' && enterpriseRbacEnabled) {
        try {
          const res = await getWorkspaceMemberRoles(wsId, row.user_id)
          memberForm.setFieldValue('role_ids', res.data.role_ids)
        } catch (e) {
          message.error(formatApiError(e))
        }
      }
    } else {
      setMemberEditingUserId(null)
      memberForm.resetFields()
    }
    setMemberOpen(true)
  }

  function legacyMemberRoleForSubmit(values: { user_id: number; role?: string }): string {
    return values.role ?? 'viewer'
  }

  async function submitMember() {
    try {
      const v = await memberForm.validateFields()
      const legacyRole = legacyMemberRoleForSubmit(v)
      await upsertWorkspaceMember(wsId, v.user_id, legacyRole)
      if (workspace?.kind === 'shared' && enterpriseRbacEnabled) {
        await putWorkspaceMemberRoles(wsId, v.user_id, v.role_ids ?? [])
      }
      message.success(t('adminWorkspaces.memberSaved'))
      setMemberOpen(false)
      memberForm.resetFields()
      setMemberEditingUserId(null)
      await loadMembers()
    } catch (e) {
      if (isFormValidationError(e)) return
      message.error(formatApiError(e))
      throw e
    }
  }

  function subjectLabel(type: string, id: number): string {
    if (type === 'user') return users.find((u) => u.id === id)?.username ?? String(id)
    if (type === 'role') {
      const r = enterpriseRoles.find((x) => x.id === id)
      return r ? `${r.name} (${r.slug})` : String(id)
    }
    if (type === 'group') return groups.find((g) => g.id === id)?.name ?? String(id)
    if (type === 'department') return departments.find((d) => d.id === id)?.name ?? String(id)
    return String(id)
  }

  function openAclModal(index: number | null = null) {
    setAclEditingIndex(index)
    if (index != null) {
      const row = aclEntries[index]
      aclForm.setFieldsValue({
        folder_scope: row.folder_id == null ? 'root' : 'folder',
        folder_id: row.folder_id ?? undefined,
        subject_type: row.subject_type,
        subject_id: row.subject_id,
        permission: row.permission,
      })
    } else {
      aclForm.setFieldsValue({
        folder_scope: 'root',
        subject_type: 'role',
        permission: 'read',
      })
    }
    setAclModalOpen(true)
  }

  async function submitAclEntry() {
    try {
      const v = await aclForm.validateFields()
      setAclSaving(true)
      const folderId = v.folder_scope === 'root' ? null : v.folder_id ?? null
      if (v.folder_scope === 'folder' && folderId == null) {
        message.error(t('adminRbac.folderIdRequired'))
        return
      }
      const newEntry: FolderAclEntryInput = {
        folder_id: folderId,
        subject_type: v.subject_type,
        subject_id: v.subject_id,
        permission: v.permission,
      }
      const next = [...aclEntries]
      if (aclEditingIndex != null) {
        next.splice(aclEditingIndex, 1)
      }
      const dupIndex = next.findIndex(
        (e) =>
          e.folder_id === newEntry.folder_id &&
          e.subject_type === newEntry.subject_type &&
          e.subject_id === newEntry.subject_id &&
          e.permission === newEntry.permission,
      )
      if (dupIndex >= 0) next.splice(dupIndex, 1)
      next.push({
        id: 0,
        ...newEntry,
        created_at: '',
        updated_at: '',
      })
      await putWorkspaceFolderAcl(wsId, entriesToInputs(next))
      message.success(t('adminRbac.aclSaved'))
      setAclModalOpen(false)
      aclForm.resetFields()
      await loadAcl()
    } catch (e) {
      if (isFormValidationError(e)) return
      message.error(formatApiError(e))
    } finally {
      setAclSaving(false)
    }
  }

  async function deleteAclEntry(index: number) {
    modal.confirm({
      title: t('adminRbac.aclDeleteTitle'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okType: 'danger',
      centered: true,
      onOk: async () => {
        try {
          const next = aclEntries.filter((_, i) => i !== index)
          await putWorkspaceFolderAcl(wsId, entriesToInputs(next))
          message.success(t('adminRbac.aclDeleted'))
          await loadAcl()
        } catch (e) {
          message.error(formatApiError(e))
          return Promise.reject(e)
        }
      },
    })
  }

  async function submitGrant() {
    try {
      const v = await grantForm.validateFields()
      await createWorkspaceGrant(wsId, v)
      message.success(t('adminWorkspaces.grantSaved'))
      setGrantOpen(false)
      grantForm.resetFields()
      await loadGrants()
    } catch (e) {
      if (isFormValidationError(e)) return
      message.error(formatApiError(e))
      throw e
    }
  }

  async function togglePublish(file: FileItem) {
    try {
      const next = file.publish_status === 'published' ? 'draft' : 'published'
      await setAdminFilePublishStatus(file.id, next)
      message.success(t('adminWorkspaces.publishUpdated'))
      await loadFiles()
    } catch (e) {
      message.error(formatApiError(e))
    }
  }

  async function openVersions(file: FileItem) {
    setVersionFile(file)
    setVersionsLoading(true)
    try {
      const res = await listAdminMdVersions(file.id)
      setVersions(res.data)
    } catch (e) {
      message.error(formatApiError(e))
    } finally {
      setVersionsLoading(false)
    }
  }

  async function restoreVersion(ver: MdVersionItem) {
    if (!versionFile) return
    modal.confirm({
      title: t('adminWorkspaces.restoreConfirm', { version: ver.version }),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        try {
          await restoreAdminMdVersion(versionFile.id, ver.id)
          message.success(t('adminWorkspaces.restored'))
          await openVersions(versionFile)
        } catch (e) {
          message.error(formatApiError(e))
          return Promise.reject(e)
        }
      },
    })
  }

  async function exportWorkspaceAudit() {
    try {
      await downloadWorkspaceSearchAuditExport(wsId)
    } catch (e) {
      message.error(formatApiError(e))
    }
  }

  async function exportGlobalAudit() {
    try {
      await downloadGlobalSearchAuditExport()
    } catch (e) {
      message.error(formatApiError(e))
    }
  }

  const roleLabel = useMemo(
    () =>
      Object.fromEntries(ROLES.map((r) => [r, t(`adminWorkspaces.roles.${r}`)])) as Record<string, string>,
    [t],
  )

  const activeEnterpriseRoleOptions = useMemo(
    () =>
      enterpriseRoles
        .filter((r) => r.is_active)
        .map((r) => ({ value: r.id, label: `${r.name} (${r.slug})` })),
    [enterpriseRoles],
  )

  if (!Number.isFinite(wsId)) {
    return <div className="admin-page">{t('adminWorkspaces.invalidId')}</div>
  }

  if (workspaceLoadState === 'loading') {
    return <div className="admin-page">{t('adminWorkspaces.loading')}</div>
  }

  if (workspaceLoadState === 'error') {
    return (
      <div className="admin-page">
        <Alert
          type="error"
          showIcon
          message={t('adminWorkspaces.loadFailed')}
          description={workspaceLoadError ?? t('adminWorkspaces.operationFailed')}
          action={
            <Button size="small" onClick={() => void loadWorkspace()}>
              {t('common.retry')}
            </Button>
          }
        />
      </div>
    )
  }

  if (workspaceLoadState === 'not_found' || !workspace) {
    return (
      <div className="admin-page">
        <Alert type="warning" showIcon message={t('adminWorkspaces.notFound')} />
      </div>
    )
  }

  const showLegacyMemberRole =
    workspace.kind !== 'shared' || !enterpriseRbacEnabled
  const showLegacyGrantsUi = workspace.kind !== 'shared' || !enterpriseRbacEnabled

  const memberColumns: ColumnsType<WorkspaceMemberItem> = [
    { title: t('adminWorkspaces.colUser'), dataIndex: 'username', key: 'username' },
    ...(showLegacyMemberRole
      ? [
          {
            title: t('adminWorkspaces.colRole'),
            dataIndex: 'role',
            key: 'role',
            render: (r: string) => roleLabel[r] ?? r,
          } as ColumnsType<WorkspaceMemberItem>[number],
        ]
      : []),
    ...(workspace.kind === 'shared'
      ? [
          {
            title: t('adminRbac.colEnterpriseRoles'),
            key: 'enterprise_roles',
            render: (_: unknown, row: WorkspaceMemberItem) => {
              const slugs = memberRoleSlugs[row.user_id] ?? []
              if (!slugs.length) return '—'
              return slugs.map((s) => <Tag key={s}>{s}</Tag>)
            },
          } as ColumnsType<WorkspaceMemberItem>[number],
        ]
      : []),
    {
      title: t('adminWorkspaces.colActions'),
      key: 'actions',
      render: (_, row) => (
        <Space>
          <Button type="link" size="small" onClick={() => void openMemberModal(row)}>
            {t('adminWorkspaces.edit')}
          </Button>
          {workspace.kind === 'personal' && workspace.owner_user_id === row.user_id ? null : (
            <Tooltip title={t('adminWorkspaces.remove')}>
              <Button
                type="link"
                danger
                size="small"
                icon={<DeleteActionIcon />}
                aria-label={t('adminWorkspaces.remove')}
                onClick={() => {
                  modal.confirm({
                    title: t('adminWorkspaces.removeMemberTitle'),
                    content: t('adminWorkspaces.removeMemberConfirm', { username: row.username }),
                    okText: t('common.confirm'),
                    cancelText: t('common.cancel'),
                    okType: 'danger',
                    centered: true,
                    onOk: async () => {
                      try {
                        await removeWorkspaceMember(wsId, row.user_id)
                        message.success(t('adminWorkspaces.memberRemoved'))
                        await loadMembers()
                      } catch (e) {
                        message.error(formatApiError(e))
                        return Promise.reject(e)
                      }
                    },
                  })
                }}
              />
            </Tooltip>
          )}
        </Space>
      ),
    },
  ]

  const grantColumns: ColumnsType<ResourceGrantItem> = [
    { title: t('adminWorkspaces.colResourceType'), dataIndex: 'resource_type', key: 'resource_type' },
    { title: t('adminWorkspaces.colResourceId'), dataIndex: 'resource_id', key: 'resource_id' },
    { title: t('adminWorkspaces.colGrantee'), dataIndex: 'grantee_username', key: 'grantee_username' },
    { title: t('adminWorkspaces.colPermission'), dataIndex: 'permission', key: 'permission' },
    {
      title: t('adminWorkspaces.colActions'),
      key: 'actions',
      render: (_, row) => (
        <Tooltip title={t('adminWorkspaces.delete')}>
          <Button
            type="link"
            danger
            size="small"
            icon={<DeleteActionIcon />}
            aria-label={t('adminWorkspaces.delete')}
            onClick={() => {
              modal.confirm({
                title: t('adminWorkspaces.deleteGrantTitle'),
                okText: t('common.confirm'),
                cancelText: t('common.cancel'),
                okType: 'danger',
                centered: true,
                onOk: async () => {
                  try {
                    await deleteWorkspaceGrant(wsId, row.id)
                    message.success(t('adminWorkspaces.grantDeleted'))
                    await loadGrants()
                  } catch (e) {
                    message.error(formatApiError(e))
                    return Promise.reject(e)
                  }
                },
              })
            }}
          />
        </Tooltip>
      ),
    },
  ]

  const aclColumns: ColumnsType<FolderAclEntryItem> = [
    {
      title: t('adminRbac.colFolder'),
      key: 'folder_id',
      render: (_, row) =>
        row.folder_id == null ? t('adminRbac.workspaceRoot') : String(row.folder_id),
    },
    { title: t('adminRbac.colSubjectType'), dataIndex: 'subject_type', key: 'subject_type' },
    {
      title: t('adminRbac.colSubject'),
      key: 'subject',
      render: (_, row) => subjectLabel(row.subject_type, row.subject_id),
    },
    { title: t('adminRbac.colPermission'), dataIndex: 'permission', key: 'permission' },
    {
      title: t('adminRbac.colActions'),
      key: 'actions',
      render: (_, row, index) => (
        <Space>
          <Button type="link" size="small" onClick={() => openAclModal(index)}>
            {t('adminRbac.edit')}
          </Button>
          <Tooltip title={t('adminRbac.delete')}>
            <Button
              type="link"
              danger
              size="small"
              icon={<DeleteActionIcon />}
              aria-label={t('adminRbac.delete')}
              onClick={() => void deleteAclEntry(index)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  const fileColumns: ColumnsType<FileItem> = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 72 },
    { title: t('adminWorkspaces.colFileName'), dataIndex: 'original_name', key: 'original_name' },
    { title: t('adminWorkspaces.colOwner'), dataIndex: 'username', key: 'username' },
    {
      title: t('adminWorkspaces.colPublish'),
      key: 'publish_status',
      render: (_, row) => (
        <Tag color={row.publish_status === 'published' ? 'green' : 'orange'}>
          {row.publish_status === 'published'
            ? t('adminWorkspaces.published')
            : t('adminWorkspaces.draft')}
        </Tag>
      ),
    },
    {
      title: t('adminWorkspaces.colActions'),
      key: 'actions',
      render: (_, row) => (
        <Space wrap>
          <Button type="link" size="small" onClick={() => void togglePublish(row)}>
            {row.publish_status === 'published'
              ? t('adminWorkspaces.setDraft')
              : t('adminWorkspaces.setPublished')}
          </Button>
          {row.has_md ? (
            <Button type="link" size="small" onClick={() => void openVersions(row)}>
              {t('adminWorkspaces.versions')}
            </Button>
          ) : null}
        </Space>
      ),
    },
  ]

  const auditColumns: ColumnsType<KbSearchAuditItem> = [
    { title: t('adminWorkspaces.colUser'), dataIndex: 'username', key: 'username', width: 100 },
    { title: t('adminWorkspaces.colQuery'), dataIndex: 'query', key: 'query', ellipsis: true },
    { title: t('adminWorkspaces.colHits'), dataIndex: 'hit_file_ids', key: 'hit_file_ids', ellipsis: true },
    { title: 'top_k', dataIndex: 'top_k', key: 'top_k', width: 64 },
    {
      title: t('adminWorkspaces.colCreated'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatDate(v),
    },
  ]

  const tabItems = [
    {
      key: 'overview',
      label: t('adminWorkspaces.tabOverview'),
      children: (
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="ID">{workspace.id}</Descriptions.Item>
            <Descriptions.Item label={t('adminWorkspaces.colSlug')}>{workspace.slug}</Descriptions.Item>
            <Descriptions.Item label={t('adminWorkspaces.colKind')}>
              {workspace.kind === 'shared'
                ? t('adminWorkspaces.kindShared')
                : t('adminWorkspaces.kindPersonal')}
            </Descriptions.Item>
            <Descriptions.Item label={t('adminWorkspaces.colOwner')}>
              {workspace.owner_username ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t('adminWorkspaces.colCreated')}>
              {formatDate(workspace.created_at)}
            </Descriptions.Item>
          </Descriptions>
          <Space>
            <Input
              value={rename}
              onChange={(e) => setRename(e.target.value)}
              style={{ width: 280 }}
              placeholder={t('adminWorkspaces.fieldName')}
            />
            <Button type="primary" loading={savingName} onClick={() => void saveName()}>
              {t('adminWorkspaces.saveName')}
            </Button>
          </Space>
        </Space>
      ),
    },
    {
      key: 'members',
      label: t('adminWorkspaces.tabMembers'),
      children: (
        <>
          <RoleNotPermissionPackNotice className="admin-rbac-notice" style={{ marginBottom: 16 }} />
          {workspace.kind === 'shared' && !enterpriseRbacEnabled ? (
            <Alert
              type="warning"
              showIcon
              message={t('adminRbac.rbacDisabledTitle')}
              description={t('adminRbac.rbacDisabledMembersHint')}
              style={{ marginBottom: 16 }}
            />
          ) : null}
          {workspace.kind === 'shared' && enterpriseRbacEnabled ? (
            <Alert
              type="info"
              showIcon
              message={t('adminRbac.rbacLegacyHiddenTitle')}
              description={t('adminRbac.rbacLegacyHiddenMembersHint')}
              style={{ marginBottom: 16 }}
            />
          ) : null}
          <Button type="primary" style={{ marginBottom: 16 }} onClick={() => void openMemberModal()}>
            {t('adminWorkspaces.addMember')}
          </Button>
          <Table rowKey="user_id" columns={memberColumns} dataSource={members} pagination={false} />
        </>
      ),
    },
    ...(showLegacyGrantsUi
      ? [
          {
            key: 'grants',
            label: t('adminWorkspaces.tabGrants'),
            children: (
              <>
                <Button type="primary" style={{ marginBottom: 16 }} onClick={() => setGrantOpen(true)}>
                  {t('adminWorkspaces.addGrant')}
                </Button>
                <Table rowKey="id" columns={grantColumns} dataSource={grants} pagination={false} />
              </>
            ),
          },
        ]
      : []),
    ...(showFolderAclTab
      ? [
          {
            key: 'folder-acl',
            label: t('adminRbac.tabFolderAcl'),
            children: (
              <>
                <RoleNotPermissionPackNotice className="admin-rbac-notice" style={{ marginBottom: 16 }} />
                <Button type="primary" style={{ marginBottom: 16 }} onClick={() => openAclModal()}>
                  {t('adminRbac.addAclEntry')}
                </Button>
                <Table
                  rowKey={(row, index) => `${row.id}-${index}`}
                  loading={aclLoading}
                  columns={aclColumns}
                  dataSource={aclEntries}
                  pagination={false}
                />
              </>
            ),
          },
        ]
      : []),
    {
      key: 'governance',
      label: t('adminWorkspaces.tabGovernance'),
      children: (
        <Table
          rowKey="id"
          loading={filesLoading}
          columns={fileColumns}
          dataSource={files}
          pagination={{
            current: filesPage,
            pageSize: 20,
            total: filesTotal,
            onChange: (p) => setFilesPage(p),
          }}
        />
      ),
    },
    {
      key: 'audit',
      label: t('adminWorkspaces.tabAudit'),
      children: (
        <>
          <Space style={{ marginBottom: 16 }}>
            <Button onClick={() => void exportWorkspaceAudit()}>
              {t('adminWorkspaces.exportWorkspace')}
            </Button>
            <Button onClick={() => void exportGlobalAudit()}>
              {t('adminWorkspaces.exportAll')}
            </Button>
          </Space>
          <Table
            rowKey="id"
            loading={auditLoading}
            columns={auditColumns}
            dataSource={audit}
            pagination={{ pageSize: 20 }}
            scroll={{ x: 'max-content' }}
          />
        </>
      ),
    },
  ]

  function subjectOptions(type: string) {
    if (type === 'user') {
      const memberIds = new Set(members.map((m) => m.user_id))
      return users.filter((u) => memberIds.has(u.id)).map((u) => ({ value: u.id, label: u.username }))
    }
    if (type === 'role')
      return enterpriseRoles
        .filter((r) => r.is_active)
        .map((r) => ({ value: r.id, label: `${r.name} (${r.slug})` }))
    if (type === 'group') return groups.map((g) => ({ value: g.id, label: g.name }))
    if (type === 'department')
      return departments.filter((d) => d.name !== '未分配').map((d) => ({ value: d.id, label: d.name }))
    return []
  }

  return (
    <div className="admin-page">
      <div className="admin-card">
        <div className="admin-header">
          <div>
            <Link to="/admin/workspaces" className="admin-subtitle">
              ← {t('adminWorkspaces.backList')}
            </Link>
            <h1 className="admin-title">{workspace.name}</h1>
          </div>
        </div>
        <Tabs items={tabItems} />
      </div>

      <Modal
        title={
          memberEditingUserId != null
            ? t('adminRbac.editMemberTitle')
            : t('adminWorkspaces.addMember')
        }
        open={memberOpen}
        onCancel={() => {
          setMemberOpen(false)
          memberForm.resetFields()
          setMemberEditingUserId(null)
        }}
        onOk={() => void submitMember()}
        destroyOnClose
      >
        <Form form={memberForm} layout="vertical">
          <Form.Item name="user_id" label={t('adminWorkspaces.colUser')} rules={[{ required: true }]}>
            <Select
              disabled={memberEditingUserId != null}
              showSearch
              optionFilterProp="label"
              options={users.map((u) => ({ value: u.id, label: u.username }))}
            />
          </Form.Item>
          {showLegacyMemberRole ? (
            <Form.Item name="role" label={t('adminWorkspaces.colRole')} rules={[{ required: true }]}>
              <Select options={ROLES.map((r) => ({ value: r, label: roleLabel[r] }))} />
            </Form.Item>
          ) : null}
          {workspace.kind === 'shared' && enterpriseRbacEnabled ? (
            <Form.Item name="role_ids" label={t('adminRbac.fieldEnterpriseRoleIds')}>
              <Select mode="multiple" options={activeEnterpriseRoleOptions} />
            </Form.Item>
          ) : null}
        </Form>
      </Modal>

      <Modal
        title={t('adminWorkspaces.addGrant')}
        open={grantOpen}
        onCancel={() => setGrantOpen(false)}
        onOk={() => void submitGrant()}
        destroyOnClose
      >
        <Form form={grantForm} layout="vertical" initialValues={{ permission: 'view', resource_type: 'file' }}>
          <Form.Item name="resource_type" label={t('adminWorkspaces.colResourceType')} rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'file', label: 'file' },
                { value: 'folder', label: 'folder' },
              ]}
            />
          </Form.Item>
          <Form.Item name="resource_id" label={t('adminWorkspaces.colResourceId')} rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} min={1} />
          </Form.Item>
          <Form.Item name="grantee_user_id" label={t('adminWorkspaces.colGrantee')} rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label" options={users.map((u) => ({ value: u.id, label: u.username }))} />
          </Form.Item>
          <Form.Item name="permission" label={t('adminWorkspaces.colPermission')} rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'view', label: 'view' },
                { value: 'edit', label: 'edit' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={aclEditingIndex != null ? t('adminRbac.editAclTitle') : t('adminRbac.addAclEntry')}
        open={aclModalOpen}
        onCancel={() => {
          setAclModalOpen(false)
          aclForm.resetFields()
        }}
        onOk={() => void submitAclEntry()}
        confirmLoading={aclSaving}
        destroyOnClose
      >
        <Form form={aclForm} layout="vertical" initialValues={{ folder_scope: 'root', permission: 'read' }}>
          <Form.Item name="folder_scope" label={t('adminRbac.fieldFolderScope')}>
            <Radio.Group>
              <Radio value="root">{t('adminRbac.workspaceRoot')}</Radio>
              <Radio value="folder">{t('adminRbac.specificFolder')}</Radio>
            </Radio.Group>
          </Form.Item>
          {aclFolderScope === 'folder' ? (
            <Form.Item
              name="folder_id"
              label={t('adminRbac.fieldFolderId')}
              rules={[{ required: true, message: t('validation.required') }]}
            >
              <InputNumber style={{ width: '100%' }} min={1} />
            </Form.Item>
          ) : null}
          <Form.Item name="subject_type" label={t('adminRbac.colSubjectType')} rules={[{ required: true }]}>
            <Select options={SUBJECT_TYPES.map((s) => ({ value: s, label: t(`adminRbac.subjectTypes.${s}`) }))} />
          </Form.Item>
          <Form.Item name="subject_id" label={t('adminRbac.colSubject')} rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label" options={subjectOptions(aclSubjectType ?? 'role')} />
          </Form.Item>
          <Form.Item name="permission" label={t('adminRbac.colPermission')} rules={[{ required: true }]}>
            <Select options={ACL_PERMISSIONS.map((p) => ({ value: p, label: p }))} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={versionFile ? t('adminWorkspaces.versionsTitle', { name: versionFile.original_name }) : ''}
        open={versionFile !== null}
        onClose={() => {
          setVersionFile(null)
          setPreviewVersion(null)
        }}
        width={640}
      >
        <Table
          rowKey="id"
          loading={versionsLoading}
          dataSource={versions}
          pagination={false}
          columns={[
            { title: t('adminWorkspaces.colVersion'), dataIndex: 'version', key: 'version' },
            {
              title: t('adminWorkspaces.colCreated'),
              dataIndex: 'created_at',
              key: 'created_at',
              render: (v: string) => formatDate(v),
            },
            {
              title: t('adminWorkspaces.colActions'),
              key: 'actions',
              render: (_, row) => (
                <Space>
                  <Button type="link" size="small" onClick={() => setPreviewVersion(row)}>
                    {t('adminWorkspaces.preview')}
                  </Button>
                  <Button type="link" size="small" onClick={() => void restoreVersion(row)}>
                    {t('adminWorkspaces.restore')}
                  </Button>
                </Space>
              ),
            },
          ]}
        />
        {previewVersion ? (
          <pre className="admin-md-preview" style={{ marginTop: 16, maxHeight: 360, overflow: 'auto' }}>
            {previewVersion.content}
          </pre>
        ) : null}
      </Drawer>
    </div>
  )
}
