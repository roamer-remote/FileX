import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { App, Button, Form, Input, Modal, Space, Switch, Table, Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  createEnterpriseRole,
  deleteEnterpriseRole,
  listEnterpriseRoles,
  updateEnterpriseRole,
  type EnterpriseRoleItem,
} from '@/api/adminRbac'
import { formatApiError, isFormValidationError } from '@/api/index'
import RoleNotPermissionPackNotice from '@/components/admin/RoleNotPermissionPackNotice'
import { DeleteActionIcon } from '@/components/DeleteActionIcon'
import { formatDate } from '@/utils'
import './AdminPage.css'

export default function AdminEnterpriseRolesPage() {
  const { t } = useTranslation()
  const { message, modal } = App.useApp()

  const [roles, setRoles] = useState<EnterpriseRoleItem[]>([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<EnterpriseRoleItem | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<{
    slug: string
    name: string
    description: string
    is_active: boolean
  }>()

  const loadRoles = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listEnterpriseRoles()
      setRoles(res.data)
    } catch (e) {
      message.error(formatApiError(e))
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    void loadRoles()
  }, [loadRoles])

  function openCreate() {
    setEditing(null)
    form.setFieldsValue({ slug: '', name: '', description: '', is_active: true })
    setModalOpen(true)
  }

  function openEdit(role: EnterpriseRoleItem) {
    setEditing(role)
    form.setFieldsValue({
      slug: role.slug,
      name: role.name,
      description: role.description ?? '',
      is_active: role.is_active,
    })
    setModalOpen(true)
  }

  async function submit() {
    try {
      const v = await form.validateFields()
      setSaving(true)
      if (editing) {
        await updateEnterpriseRole(editing.id, {
          name: v.name.trim(),
          description: v.description?.trim() || null,
          is_active: v.is_active,
        })
        message.success(t('adminRbac.roleUpdated'))
      } else {
        await createEnterpriseRole({
          slug: v.slug.trim(),
          name: v.name.trim(),
          description: v.description?.trim() || null,
        })
        message.success(t('adminRbac.roleCreated'))
      }
      setModalOpen(false)
      form.resetFields()
      await loadRoles()
    } catch (e) {
      if (isFormValidationError(e)) return
      message.error(formatApiError(e))
    } finally {
      setSaving(false)
    }
  }

  function confirmDelete(role: EnterpriseRoleItem) {
    modal.confirm({
      title: t('adminRbac.roleDeleteTitle', { name: role.name }),
      content: t('adminRbac.roleDeleteConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okType: 'danger',
      centered: true,
      onOk: async () => {
        try {
          const res = await deleteEnterpriseRole(role.id)
          message.success(res.data.message || t('adminRbac.roleDeleted'))
          await loadRoles()
        } catch (e) {
          message.error(formatApiError(e))
          return Promise.reject(e)
        }
      },
    })
  }

  const columns: ColumnsType<EnterpriseRoleItem> = [
    { title: t('adminRbac.colSlug'), dataIndex: 'slug', key: 'slug', width: 140 },
    { title: t('adminRbac.colRoleName'), dataIndex: 'name', key: 'name' },
    {
      title: t('adminRbac.colDescription'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (v: string | null) => v || '—',
    },
    {
      title: t('adminRbac.colBuiltin'),
      key: 'is_builtin',
      width: 80,
      render: (_, row) =>
        row.is_builtin ? <Tag>{t('adminRbac.builtin')}</Tag> : <Tag>{t('adminRbac.custom')}</Tag>,
    },
    {
      title: t('adminRbac.colActive'),
      key: 'is_active',
      width: 80,
      render: (_, row) => (
        <Tag color={row.is_active ? 'green' : 'default'}>
          {row.is_active ? t('adminRbac.active') : t('adminRbac.inactive')}
        </Tag>
      ),
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
      width: 160,
      render: (_, row) => (
        <Space>
          <Button type="link" size="small" onClick={() => openEdit(row)}>
            {t('adminRbac.edit')}
          </Button>
          {row.is_builtin ? null : (
            <Tooltip title={t('adminRbac.delete')}>
              <Button
                type="link"
                danger
                size="small"
                icon={<DeleteActionIcon />}
                aria-label={t('adminRbac.delete')}
                onClick={() => confirmDelete(row)}
              />
            </Tooltip>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div className="admin-root">
      <div className="admin-panel admin-panel--enterprise-roles">
        <div className="admin-header">
          <div className="ah-title-group">
            <h2 className="ah-title">{t('adminRbac.enterpriseRolesTitle')}</h2>
            <span className="ah-sub">{t('adminRbac.enterpriseRolesSubtitle')}</span>
          </div>
          <div className="ah-toolbar">
            <Button type="primary" onClick={openCreate}>
              {t('adminRbac.addRole')}
            </Button>
          </div>
        </div>
        <div className="admin-enterprise-roles-body">
          <RoleNotPermissionPackNotice showDisabledHint className="admin-rbac-notice" />
          <div className="admin-table-wrap admin-enterprise-roles-table-wrap">
            <Table
              className="admin-enterprise-roles-table"
              rowKey="id"
              loading={loading}
              columns={columns}
              dataSource={roles}
              size="small"
              pagination={false}
            />
          </div>
        </div>
      </div>

      <Modal
        title={
          editing
            ? t('adminRbac.editRoleTitle', { name: editing.name })
            : t('adminRbac.createRoleTitle')
        }
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false)
          form.resetFields()
        }}
        onOk={() => void submit()}
        confirmLoading={saving}
        destroyOnClose
      >
        <Form form={form} layout="vertical" initialValues={{ is_active: true }}>
          <Form.Item
            name="slug"
            label={t('adminRbac.fieldSlug')}
            rules={[
              { required: true, message: t('validation.required') },
              {
                pattern: /^[a-z][a-z0-9_]*$/,
                message: t('adminRbac.slugPatternHint'),
              },
            ]}
          >
            <Input disabled={!!editing} placeholder="editor" />
          </Form.Item>
          <Form.Item
            name="name"
            label={t('adminRbac.fieldRoleName')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="description" label={t('adminRbac.fieldDescription')}>
            <Input.TextArea rows={3} />
          </Form.Item>
          {editing ? (
            <Form.Item name="is_active" label={t('adminRbac.fieldActive')} valuePropName="checked">
              <Switch />
            </Form.Item>
          ) : null}
        </Form>
      </Modal>
    </div>
  )
}
