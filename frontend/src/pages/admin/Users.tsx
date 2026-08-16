import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  App,
  Button,
  Dropdown,
  Form,
  Input,
  Modal,
  Pagination,
  Space,
  Select,
  Spin,
  Switch,
  Table,
  Tag,
  Tooltip,
} from 'antd'
import type { MenuProps } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckCircleOutlined,
  CrownOutlined,
  EllipsisOutlined,
  KeyOutlined,
  StopOutlined,
  TeamOutlined,
  UserDeleteOutlined,
} from '@ant-design/icons'
import api, { formatApiError, isFormValidationError } from '@/api/index'
import { createAdminUser, listAdminUsers, resetAdminUserPassword, type AdminUserListSummary, type AdminUserRow } from '@/api/admin'
import {
  getAdminUserOrg,
  listAdminDepartments,
  listAdminGroups,
  putAdminUserOrg,
  type DepartmentItem,
  type GroupItem,
} from '@/api/adminRbac'
import { departmentSelectOptions } from '@/lib/departmentTree'
import { formatDate } from '@/utils'
import { useFlexTableBodyScrollY } from '@/hooks/useFlexTableBodyScrollY'
import '@/components/FileList.css'
import './AdminPage.css'

type UserItem = AdminUserRow

function WechatText({ value, className }: { value: string; className?: string }) {
  if (!value) return <span className="at-muted">—</span>
  return (
    <Tooltip title={value}>
      <span className={className}>{value}</span>
    </Tooltip>
  )
}

export default function AdminUsersPage() {
  const { message: msg, modal } = App.useApp()
  const { t } = useTranslation()
  const [users, setUsers] = useState<UserItem[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [summary, setSummary] = useState<AdminUserListSummary>({ admin_count: 0, active_today_count: 0 })
  const bodyRef = useRef<HTMLDivElement>(null)
  const [currentUserId, setCurrentUserId] = useState(0)
  const [createOpen, setCreateOpen] = useState(false)
  const [createForm] = Form.useForm<{ username: string; password: string; confirm: string; is_admin: boolean }>()
  const [creating, setCreating] = useState(false)
  const [resetTarget, setResetTarget] = useState<UserItem | null>(null)
  const [resetForm] = Form.useForm<{ password: string; confirm: string }>()
  const [resetting, setResetting] = useState(false)
  const [orgTarget, setOrgTarget] = useState<UserItem | null>(null)
  const [orgForm] = Form.useForm<{ primary_department_id: number; group_ids: number[] }>()
  const [orgSaving, setOrgSaving] = useState(false)
  const [departments, setDepartments] = useState<DepartmentItem[]>([])
  const [groups, setGroups] = useState<GroupItem[]>([])

  const loadUsers = useCallback(async (p: number, ps: number) => {
    setLoading(true)
    try {
      const res = await listAdminUsers({ page: p, page_size: ps })
      setUsers(res.data.items)
      setTotal(res.data.total)
      setSummary(res.data.summary ?? { admin_count: 0, active_today_count: 0 })
      const userStr = localStorage.getItem('filex_user')
      if (userStr) setCurrentUserId(JSON.parse(userStr).id as number)
    } catch {
      /* interceptor */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadUsers(page, pageSize)
  }, [loadUsers, page, pageSize])

  const scrollY = useFlexTableBodyScrollY([loading, users.length, page, pageSize], {
    bodyRef,
  })

  const tableScroll = users.length > 0 && scrollY > 0 ? { y: scrollY, x: 'max-content' as const } : { x: 'max-content' as const }

  async function submitCreate() {
    try {
      const v = await createForm.validateFields()
      setCreating(true)
      await createAdminUser({
        username: v.username.trim(),
        password: v.password,
        is_admin: v.is_admin,
      })
      msg.success(t('messages.userCreated'))
      setCreateOpen(false)
      createForm.resetFields()
      setPage(1)
      await loadUsers(1, pageSize)
    } catch (e) {
      if (e && typeof e === 'object' && 'errorFields' in e) return
      msg.error(formatApiError(e))
    } finally {
      setCreating(false)
    }
  }

  async function toggleAdmin(user: UserItem) {
    modal.confirm({
      title: user.is_admin ? t('admin.users.confirmRevokeTitle', { name: user.username }) : t('admin.users.confirmPromoteTitle', { name: user.username }),
      content: user.is_admin ? t('admin.users.confirmRevokeContent') : t('admin.users.confirmPromoteContent'),
      okText: user.is_admin ? t('admin.users.revoke') : t('admin.users.promote'),
      okType: user.is_admin ? 'danger' : 'primary',
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          await api.put(`/admin/users/${user.id}`, { is_admin: !user.is_admin })
          msg.success(t('messages.clearanceUpdated'))
          await loadUsers(page, pageSize)
        } catch {
          /* interceptor */
        }
      },
    })
  }

  async function toggleActive(user: UserItem) {
    modal.confirm({
      title: user.is_active ? t('admin.users.confirmDeactivateTitle', { name: user.username }) : t('admin.users.confirmActivateTitle', { name: user.username }),
      content: user.is_active ? t('admin.users.confirmDeactivateContent') : t('admin.users.confirmActivateContent'),
      okText: user.is_active ? t('admin.users.deactivate') : t('admin.users.activate'),
      okType: user.is_active ? 'danger' : 'primary',
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          await api.put(`/admin/users/${user.id}`, { is_active: !user.is_active })
          msg.success(t('messages.accountStatusUpdated'))
          await loadUsers(page, pageSize)
        } catch {
          /* interceptor */
        }
      },
    })
  }

  async function openOrgModal(user: UserItem) {
    setOrgTarget(user)
    try {
      const [deptRes, groupRes, orgRes] = await Promise.all([
        listAdminDepartments(),
        listAdminGroups(),
        getAdminUserOrg(user.id),
      ])
      setDepartments(deptRes.data)
      setGroups(groupRes.data)
      orgForm.setFieldsValue({
        primary_department_id: orgRes.data.primary_department_id,
        group_ids: orgRes.data.groups.map((g) => g.id),
      })
    } catch (e) {
      msg.error(formatApiError(e))
      setOrgTarget(null)
    }
  }

  async function submitOrg() {
    if (!orgTarget) return
    try {
      const v = await orgForm.validateFields()
      setOrgSaving(true)
      await putAdminUserOrg(orgTarget.id, {
        primary_department_id: v.primary_department_id,
        group_ids: v.group_ids ?? [],
      })
      msg.success(t('adminRbac.userOrgSaved'))
      setOrgTarget(null)
      orgForm.resetFields()
    } catch (e) {
      if (isFormValidationError(e)) return
      msg.error(formatApiError(e))
    } finally {
      setOrgSaving(false)
    }
  }

  async function submitResetPassword() {
    if (!resetTarget) return
    try {
      const v = await resetForm.validateFields()
      setResetting(true)
      await resetAdminUserPassword(resetTarget.id, v.password)
      msg.success(t('messages.passwordResetByAdmin'))
      setResetTarget(null)
      resetForm.resetFields()
    } catch (e) {
      if (e && typeof e === 'object' && 'errorFields' in e) {
        msg.warning(t('changePassword.modalValidationTitle'))
        return
      }
      msg.error(formatApiError(e))
    } finally {
      setResetting(false)
    }
  }

  function renderOps(row: UserItem) {
    const items: MenuProps['items'] = [
      {
        key: 'admin',
        label: row.is_admin ? t('admin.users.revoke') : t('admin.users.promote'),
        icon: row.is_admin ? <UserDeleteOutlined /> : <CrownOutlined />,
        disabled: row.id === currentUserId || !row.is_active,
        danger: row.is_admin,
        onClick: () => void toggleAdmin(row),
      },
      {
        key: 'active',
        label: row.is_active ? t('admin.users.deactivate') : t('admin.users.activate'),
        icon: row.is_active ? <StopOutlined /> : <CheckCircleOutlined />,
        disabled: row.id === currentUserId,
        danger: row.is_active,
        onClick: () => void toggleActive(row),
      },
      {
        key: 'reset',
        label: t('admin.users.resetPassword'),
        icon: <KeyOutlined />,
        disabled: row.id === currentUserId,
        onClick: () => setResetTarget(row),
      },
      {
        key: 'org',
        label: t('adminRbac.userOrgAction'),
        icon: <TeamOutlined />,
        onClick: () => void openOrgModal(row),
      },
    ]

    return (
      <Dropdown menu={{ items }} trigger={['click']}>
        <Button size="small" className="admin-user-ops-trigger" icon={<EllipsisOutlined />}>
          {t('admin.users.opsExpand')}
        </Button>
      </Dropdown>
    )
  }

  const columns: ColumnsType<UserItem> = [
    {
      title: t('admin.users.ident'),
      key: 'ident',
      width: 128,
      ellipsis: true,
      render: (_, row) => (
        <div className="at-ident">
          <span className="at-avatar">{row.username.charAt(0).toUpperCase()}</span>
          <span className="at-name">{row.username}</span>
          {row.id === currentUserId ? <span className="at-you">{t('admin.users.you')}</span> : null}
        </div>
      ),
    },
    {
      title: t('admin.users.clearance'),
      key: 'role',
      width: 70,
      className: 'admin-users-clearance-col',
      render: (_, row) => (
        <div className="admin-users-clearance">
          <Tag color={row.is_admin ? 'gold' : 'default'}>{row.is_admin ? t('admin.users.admin') : t('admin.users.user')}</Tag>
          {!row.is_active ? <Tag color="red">{t('admin.users.inactive')}</Tag> : null}
        </div>
      ),
    },
    {
      title: t('admin.users.wechatName'),
      key: 'wechat_nickname',
      width: 86,
      render: (_, row) => <WechatText value={row.wechat_nickname} className="at-wechat-name" />,
    },
    {
      title: t('admin.users.wechatId'),
      key: 'wechat_openid',
      width: 104,
      render: (_, row) => <WechatText value={row.wechat_openid} className="at-wechat-id" />,
    },
    {
      title: t('admin.users.createdAt'),
      dataIndex: 'created_at',
      width: 124,
      render: (d: string) => <span className="at-date">{d ? formatDate(d) : '—'}</span>,
    },
    {
      title: t('admin.users.lastLoginAt'),
      dataIndex: 'last_login_at',
      width: 124,
      render: (d: string) => (
        <span className="at-date">{d ? formatDate(d) : t('admin.users.neverLoggedIn')}</span>
      ),
    },
    {
      title: t('admin.users.ops'),
      key: 'ops',
      width: 62,
      align: 'center',
      className: 'admin-users-ops-col',
      render: (_, row) => renderOps(row),
    },
  ]

  return (
    <div className="admin-root">
      <div className="admin-panel admin-panel--users">
        <div className="admin-header admin-header--users">
          <div className="ah-title-group ah-title-group--row">
            <h2 className="ah-title">{t('admin.users.title')}</h2>
            <span className="ah-sub">{t('admin.users.subtitle')}</span>
            <div className="admin-users-header-stats" aria-label={t('admin.users.statsAria')}>
              <span className="admin-users-header-stat">
                <span className="admin-users-header-stat__value">{total}</span>
                <span className="admin-users-header-stat__label">{t('admin.users.statTotal')}</span>
              </span>
              <span className="admin-users-header-stat">
                <span className="admin-users-header-stat__value">{summary.admin_count}</span>
                <span className="admin-users-header-stat__label">{t('admin.users.statAdmins')}</span>
              </span>
              <span className="admin-users-header-stat">
                <span className="admin-users-header-stat__value">{summary.active_today_count}</span>
                <span className="admin-users-header-stat__label">{t('admin.users.statActiveToday')}</span>
              </span>
            </div>
          </div>
          <div className="ah-toolbar">
            <Button type="primary" onClick={() => setCreateOpen(true)}>
              {t('admin.users.createUser')}
            </Button>
          </div>
        </div>
        <div className="admin-table-wrap admin-table-wrap--flex fl-table-shell">
          <div className="fl-body" ref={bodyRef}>
            <Spin spinning={loading} className="fl-spin">
              <div className="fl-table-host">
                <Table
                  rowKey="id"
                  columns={columns}
                  dataSource={users}
                  size="small"
                  tableLayout="fixed"
                  pagination={false}
                  scroll={tableScroll}
                />
              </div>
            </Spin>
          </div>
          <div className="fl-pager">
            <Pagination
              current={page}
              pageSize={pageSize}
              total={total}
              showSizeChanger
              pageSizeOptions={['10', '20', '50', '100']}
              showTotal={(n) => t('admin.users.pageTotal', { total: n })}
              onChange={(p, ps) => {
                setPage(p)
                setPageSize(ps)
              }}
            />
          </div>
        </div>
      </div>

      <Modal
        title={t('admin.users.createTitle')}
        open={createOpen}
        onCancel={() => {
          setCreateOpen(false)
          createForm.resetFields()
        }}
        footer={
          <Space>
            <Button
              onClick={() => {
                setCreateOpen(false)
                createForm.resetFields()
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button type="primary" loading={creating} onClick={() => void submitCreate()}>
              {t('common.confirm')}
            </Button>
          </Space>
        }
        destroyOnClose
      >
        <Form form={createForm} layout="vertical" initialValues={{ is_admin: false }}>
          <Form.Item name="username" label={t('admin.users.newUsername')} rules={[{ required: true, message: t('validation.requiredIdent') }]}>
            <Input placeholder={t('login.identPlaceholder')} autoComplete="off" />
          </Form.Item>
          <Form.Item
            name="password"
            label={t('admin.users.initialPassword')}
            rules={[
              { required: true, message: t('validation.requiredPassword') },
              { min: 6, message: t('validation.passwordMinLength') },
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            name="confirm"
            label={t('admin.users.confirmPassword')}
            dependencies={['password']}
            rules={[
              { required: true, message: t('validation.requiredConfirm') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) return Promise.resolve()
                  return Promise.reject(new Error(t('validation.passwordMismatch')))
                },
              }),
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="is_admin" label={t('admin.users.grantAdmin')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={resetTarget ? t('admin.users.resetTitle', { name: resetTarget.username }) : ''}
        open={resetTarget !== null}
        onCancel={() => {
          setResetTarget(null)
          resetForm.resetFields()
        }}
        footer={
          <Space>
            <Button
              onClick={() => {
                setResetTarget(null)
                resetForm.resetFields()
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button type="primary" loading={resetting} onClick={() => void submitResetPassword()}>
              {t('common.confirm')}
            </Button>
          </Space>
        }
        destroyOnClose
      >
        <p className="at-reset-hint">{t('admin.users.resetHint')}</p>
        <Form form={resetForm} layout="vertical">
          <Form.Item
            name="password"
            label={t('admin.users.newPassword')}
            rules={[
              { required: true, message: t('validation.requiredPassword') },
              { min: 6, message: t('validation.passwordMinLength') },
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            name="confirm"
            label={t('admin.users.confirmPassword')}
            dependencies={['password']}
            rules={[
              { required: true, message: t('validation.requiredConfirm') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) return Promise.resolve()
                  return Promise.reject(new Error(t('validation.passwordMismatch')))
                },
              }),
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={orgTarget ? t('adminRbac.userOrgTitle', { name: orgTarget.username }) : ''}
        open={orgTarget !== null}
        onCancel={() => {
          setOrgTarget(null)
          orgForm.resetFields()
        }}
        footer={
          <Space>
            <Button
              onClick={() => {
                setOrgTarget(null)
                orgForm.resetFields()
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button type="primary" loading={orgSaving} onClick={() => void submitOrg()}>
              {t('common.confirm')}
            </Button>
          </Space>
        }
        destroyOnClose
      >
        <Form form={orgForm} layout="vertical">
          <Form.Item
            name="primary_department_id"
            label={t('adminRbac.fieldPrimaryDepartment')}
            rules={[{ required: true, message: t('validation.required') }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={departmentSelectOptions(departments, { excludeUnassigned: false })}
            />
          </Form.Item>
          <Form.Item name="group_ids" label={t('adminRbac.fieldGroups')}>
            <Select
              mode="multiple"
              showSearch
              optionFilterProp="label"
              options={groups.map((g) => ({ value: g.id, label: g.name }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
