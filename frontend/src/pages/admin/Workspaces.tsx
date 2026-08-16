import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { App, Button, Form, Input, Modal, Select, Space, Table, Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  createAdminWorkspace,
  deleteAdminWorkspace,
  getAdminUsers,
  listAdminWorkspaces,
  type AdminUserOption,
  type AdminWorkspaceItem,
} from '@/api/adminWorkspaces'
import { formatApiError, isFormValidationError } from '@/api/index'
import { useSystemSettingsStore } from '@/stores/systemSettingsStore'
import { DeleteActionIcon } from '@/components/DeleteActionIcon'
import { formatDate } from '@/utils'
import './AdminPage.css'

export default function AdminWorkspacesPage() {
  const { t } = useTranslation()
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const [items, setItems] = useState<AdminWorkspaceItem[]>([])
  const [loading, setLoading] = useState(true)
  const [users, setUsers] = useState<AdminUserOption[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm<{ name: string; owner_user_id: number }>()
  const sharedWorkspacesEnabled = useSystemSettingsStore((s) => s.shared_workspaces_enabled ?? true)

  useEffect(() => {
    void useSystemSettingsStore.getState().load()
  }, [])

  async function load() {
    setLoading(true)
    try {
      const [wsRes, usersRes] = await Promise.all([listAdminWorkspaces(), getAdminUsers()])
      setItems(wsRes.data)
      setUsers(usersRes.data.items)
    } catch (e) {
      message.error(formatApiError(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  async function submitCreate() {
    try {
      const v = await form.validateFields()
      setCreating(true)
      const res = await createAdminWorkspace(v.name.trim(), v.owner_user_id)
      message.success(t('adminWorkspaces.created'))
      setCreateOpen(false)
      form.resetFields()
      await load()
      navigate(`/admin/workspaces/${res.data.id}`)
    } catch (e) {
      if (isFormValidationError(e)) return
      message.error(formatApiError(e))
    } finally {
      setCreating(false)
    }
  }

  function confirmDelete(row: AdminWorkspaceItem) {
    modal.confirm({
      title: t('adminWorkspaces.deleteTitle'),
      content: t('adminWorkspaces.deleteConfirm', { name: row.name }),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okType: 'danger',
      centered: true,
      onOk: async () => {
        try {
          await deleteAdminWorkspace(row.id)
          message.success(t('adminWorkspaces.deleted'))
          await load()
        } catch (e) {
          message.error(formatApiError(e))
          return Promise.reject(e)
        }
      },
    })
  }

  const columns: ColumnsType<AdminWorkspaceItem> = [
    { title: t('adminWorkspaces.colName'), dataIndex: 'name', key: 'name' },
    {
      title: t('adminWorkspaces.colKind'),
      dataIndex: 'kind',
      key: 'kind',
      render: (k: string) => (
        <Tag color={k === 'shared' ? 'blue' : 'default'}>
          {k === 'shared' ? t('adminWorkspaces.kindShared') : t('adminWorkspaces.kindPersonal')}
        </Tag>
      ),
    },
    {
      title: t('adminWorkspaces.colOwner'),
      key: 'owner',
      render: (_, r) => r.owner_username ?? '—',
    },
    { title: t('adminWorkspaces.colSlug'), dataIndex: 'slug', key: 'slug' },
    { title: t('adminWorkspaces.colMembers'), dataIndex: 'member_count', key: 'member_count' },
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
          <Link to={`/admin/workspaces/${row.id}`}>{t('adminWorkspaces.manage')}</Link>
          {row.kind === 'shared' ? (
            <Tooltip title={t('adminWorkspaces.delete')}>
              <Button
                type="link"
                danger
                size="small"
                icon={<DeleteActionIcon />}
                aria-label={t('adminWorkspaces.delete')}
                onClick={() => confirmDelete(row)}
              />
            </Tooltip>
          ) : null}
        </Space>
      ),
    },
  ]

  return (
    <div className="admin-page">
      <div className="admin-card">
        <div className="admin-header">
          <div className="ah-title-group">
            <h1 className="admin-title ah-title">{t('adminWorkspaces.title')}</h1>
            <span className="admin-subtitle ah-sub">{t('adminWorkspaces.subtitle')}</span>
          </div>
          {sharedWorkspacesEnabled ? (
            <Button type="primary" onClick={() => setCreateOpen(true)}>
              {t('adminWorkspaces.createShared')}
            </Button>
          ) : null}
        </div>
        <div className="admin-table-wrap">
          <Table rowKey="id" loading={loading} columns={columns} dataSource={items} pagination={false} scroll={{ x: 'max-content' }} />
        </div>
      </div>

      <Modal
        title={t('adminWorkspaces.createTitle')}
        open={createOpen}
        onCancel={() => {
          setCreateOpen(false)
          form.resetFields()
        }}
        footer={
          <Space>
            <Button onClick={() => setCreateOpen(false)}>{t('common.cancel')}</Button>
            <Button type="primary" loading={creating} onClick={() => void submitCreate()}>
              {t('common.confirm')}
            </Button>
          </Space>
        }
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label={t('adminWorkspaces.fieldName')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="owner_user_id" label={t('adminWorkspaces.fieldOwner')} rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={users.map((u) => ({ value: u.id, label: u.username }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
