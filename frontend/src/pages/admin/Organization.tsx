import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { App, Button, Form, Input, InputNumber, Modal, Space, Table, Tabs, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  createAdminDepartment,
  createAdminGroup,
  deleteAdminDepartment,
  deleteAdminGroup,
  listAdminDepartments,
  listAdminGroups,
  updateAdminDepartment,
  updateAdminGroup,
  type DepartmentItem,
  type GroupItem,
} from '@/api/adminRbac'
import { formatApiError, isFormValidationError } from '@/api/index'
import DepartmentDetailPane from '@/components/admin/DepartmentDetailPane'
import DepartmentTreePanel from '@/components/admin/DepartmentTreePanel'
import { DeleteActionIcon } from '@/components/DeleteActionIcon'
import { useAdminOrgUiState } from '@/hooks/useAdminOrgUiState'
import type { AdminOrgTab } from '@/lib/uiStateTypes'
import { formatDate } from '@/utils'
import './AdminPage.css'

export default function AdminOrganizationPage() {
  const { t } = useTranslation()
  const { message, modal } = App.useApp()

  const [departments, setDepartments] = useState<DepartmentItem[]>([])
  const [groups, setGroups] = useState<GroupItem[]>([])
  const [deptLoading, setDeptLoading] = useState(true)
  const [groupLoading, setGroupLoading] = useState(true)

  const {
    activeTab,
    setActiveTabAndSync,
    selectedDeptId,
    selectDepartment,
    persistedExpandedIds,
    updatePersistedExpanded,
    afterDepartmentDeleted,
    scrollToDeptId,
    clearScrollTarget,
  } = useAdminOrgUiState(departments, !deptLoading)

  const [deptModalOpen, setDeptModalOpen] = useState(false)
  const [deptEditing, setDeptEditing] = useState<DepartmentItem | null>(null)
  const [deptParentId, setDeptParentId] = useState<number | null>(null)
  const [deptForm] = Form.useForm<{ name: string; sort_order: number }>()
  const [deptSaving, setDeptSaving] = useState(false)

  const [groupModalOpen, setGroupModalOpen] = useState(false)
  const [groupEditing, setGroupEditing] = useState<GroupItem | null>(null)
  const [groupForm] = Form.useForm<{ name: string; description: string }>()
  const [groupSaving, setGroupSaving] = useState(false)

  const loadDepartments = useCallback(async () => {
    setDeptLoading(true)
    try {
      const res = await listAdminDepartments()
      setDepartments(res.data)
    } catch (e) {
      message.error(formatApiError(e))
    } finally {
      setDeptLoading(false)
    }
  }, [message])

  const loadGroups = useCallback(async () => {
    setGroupLoading(true)
    try {
      const res = await listAdminGroups()
      setGroups(res.data)
    } catch (e) {
      message.error(formatApiError(e))
    } finally {
      setGroupLoading(false)
    }
  }, [message])

  useEffect(() => {
    void loadDepartments()
    void loadGroups()
  }, [loadDepartments, loadGroups])

  const selectedDept = useMemo(
    () => departments.find((d) => d.id === selectedDeptId) ?? null,
    [departments, selectedDeptId],
  )

  function openCreateDept(parentId: number | null) {
    setDeptEditing(null)
    setDeptParentId(parentId)
    deptForm.setFieldsValue({ name: '', sort_order: 0 })
    setDeptModalOpen(true)
  }

  function openEditDept(dept: DepartmentItem) {
    setDeptEditing(dept)
    setDeptParentId(dept.parent_id)
    deptForm.setFieldsValue({ name: dept.name, sort_order: dept.sort_order })
    setDeptModalOpen(true)
  }

  async function submitDept() {
    try {
      const v = await deptForm.validateFields()
      setDeptSaving(true)
      if (deptEditing) {
        await updateAdminDepartment(deptEditing.id, {
          name: v.name.trim(),
          sort_order: v.sort_order,
        })
        message.success(t('adminRbac.departmentUpdated'))
      } else {
        const parentId = deptParentId ?? departments.find((d) => d.parent_id === null)?.id
        if (!parentId) {
          message.error(t('adminRbac.departmentParentRequired'))
          return
        }
        await createAdminDepartment({
          name: v.name.trim(),
          parent_id: parentId,
          sort_order: v.sort_order,
        })
        message.success(t('adminRbac.departmentCreated'))
      }
      setDeptModalOpen(false)
      deptForm.resetFields()
      await loadDepartments()
    } catch (e) {
      if (isFormValidationError(e)) return
      message.error(formatApiError(e))
    } finally {
      setDeptSaving(false)
    }
  }

  function confirmDeleteDept(dept: DepartmentItem) {
    modal.confirm({
      title: t('adminRbac.departmentDeleteTitle', { name: dept.name }),
      content: t('adminRbac.departmentDeleteConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okType: 'danger',
      centered: true,
      onOk: async () => {
        try {
          await deleteAdminDepartment(dept.id)
          message.success(t('adminRbac.departmentDeleted'))
          afterDepartmentDeleted(dept.id)
          await loadDepartments()
        } catch (e) {
          message.error(formatApiError(e))
          return Promise.reject(e)
        }
      },
    })
  }

  function openCreateGroup() {
    setGroupEditing(null)
    groupForm.setFieldsValue({ name: '', description: '' })
    setGroupModalOpen(true)
  }

  function openEditGroup(group: GroupItem) {
    setGroupEditing(group)
    groupForm.setFieldsValue({ name: group.name, description: group.description ?? '' })
    setGroupModalOpen(true)
  }

  async function submitGroup() {
    try {
      const v = await groupForm.validateFields()
      setGroupSaving(true)
      if (groupEditing) {
        await updateAdminGroup(groupEditing.id, {
          name: v.name.trim(),
          description: v.description?.trim() || null,
        })
        message.success(t('adminRbac.groupUpdated'))
      } else {
        await createAdminGroup({
          name: v.name.trim(),
          description: v.description?.trim() || null,
        })
        message.success(t('adminRbac.groupCreated'))
      }
      setGroupModalOpen(false)
      groupForm.resetFields()
      await loadGroups()
    } catch (e) {
      if (isFormValidationError(e)) return
      message.error(formatApiError(e))
    } finally {
      setGroupSaving(false)
    }
  }

  function confirmDeleteGroup(group: GroupItem) {
    modal.confirm({
      title: t('adminRbac.groupDeleteTitle', { name: group.name }),
      content: t('adminRbac.groupDeleteConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okType: 'danger',
      centered: true,
      onOk: async () => {
        try {
          await deleteAdminGroup(group.id)
          message.success(t('adminRbac.groupDeleted'))
          await loadGroups()
        } catch (e) {
          message.error(formatApiError(e))
          return Promise.reject(e)
        }
      },
    })
  }

  const groupColumns: ColumnsType<GroupItem> = [
    { title: t('adminRbac.colGroupName'), dataIndex: 'name', key: 'name' },
    {
      title: t('adminRbac.colGroupDescription'),
      dataIndex: 'description',
      key: 'description',
      render: (v: string | null) => v || '—',
    },
    {
      title: t('adminRbac.colCreated'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => formatDate(v),
    },
    {
      title: t('adminRbac.colActions'),
      key: 'actions',
      width: 140,
      render: (_, row) => (
        <Space>
          <Button type="link" size="small" onClick={() => openEditGroup(row)}>
            {t('adminRbac.edit')}
          </Button>
          <Tooltip title={t('adminRbac.delete')}>
            <Button
              type="link"
              danger
              size="small"
              icon={<DeleteActionIcon />}
              aria-label={t('adminRbac.delete')}
              onClick={() => confirmDeleteGroup(row)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  const tabItems = [
    {
      key: 'departments',
      label: t('adminRbac.tabDepartments'),
      children: (
        <div className="admin-org-split">
          <DepartmentTreePanel
            departments={departments}
            loading={deptLoading}
            selectedDeptId={selectedDeptId}
            persistedExpandedIds={persistedExpandedIds}
            scrollToDeptId={scrollToDeptId}
            onSelectDept={selectDepartment}
            onPersistedExpandedChange={updatePersistedExpanded}
            onScrollComplete={clearScrollTarget}
          />
          <DepartmentDetailPane
            departments={departments}
            selectedDept={selectedDept}
            onCreateChild={openCreateDept}
            onEdit={openEditDept}
            onDelete={confirmDeleteDept}
          />
        </div>
      ),
    },
    {
      key: 'groups',
      label: t('adminRbac.tabGroups'),
      children: (
        <div className="admin-org-groups-tab">
          <Button type="primary" className="admin-org-groups-add" onClick={openCreateGroup}>
            {t('adminRbac.addGroup')}
          </Button>
          <div className="admin-table-wrap admin-table-wrap--flex fl-table-shell">
            <Table
              rowKey="id"
              loading={groupLoading}
              columns={groupColumns}
              dataSource={groups}
              pagination={false}
            />
          </div>
        </div>
      ),
    },
  ]

  return (
    <div className="admin-root">
      <div className="admin-panel admin-panel--organization">
        <div className="admin-header">
          <div className="ah-title-group">
            <h2 className="ah-title">{t('adminRbac.organizationTitle')}</h2>
            <span className="ah-sub">{t('adminRbac.organizationSubtitle')}</span>
          </div>
        </div>
        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTabAndSync(key as AdminOrgTab)}
          items={tabItems}
        />
      </div>

      <Modal
        title={
          deptEditing
            ? t('adminRbac.editDepartmentTitle', { name: deptEditing.name })
            : t('adminRbac.createDepartmentTitle')
        }
        open={deptModalOpen}
        onCancel={() => {
          setDeptModalOpen(false)
          deptForm.resetFields()
        }}
        onOk={() => void submitDept()}
        confirmLoading={deptSaving}
        destroyOnClose
      >
        <Form form={deptForm} layout="vertical" initialValues={{ sort_order: 0 }}>
          <Form.Item
            name="name"
            label={t('adminRbac.fieldDepartmentName')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input disabled={deptEditing?.is_builtin} />
          </Form.Item>
          <Form.Item name="sort_order" label={t('adminRbac.fieldSortOrder')}>
            <InputNumber style={{ width: '100%' }} min={0} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={
          groupEditing
            ? t('adminRbac.editGroupTitle', { name: groupEditing.name })
            : t('adminRbac.createGroupTitle')
        }
        open={groupModalOpen}
        onCancel={() => {
          setGroupModalOpen(false)
          groupForm.resetFields()
        }}
        onOk={() => void submitGroup()}
        confirmLoading={groupSaving}
        destroyOnClose
      >
        <Form form={groupForm} layout="vertical">
          <Form.Item
            name="name"
            label={t('adminRbac.fieldGroupName')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="description" label={t('adminRbac.fieldGroupDescription')}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
