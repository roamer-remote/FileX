import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Alert, App, Button, Form, Input, Modal, Select, Space, Switch, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  createExternalSyncSource,
  getExternalSyncDeletePolicyHint,
  listExternalSyncSources,
  listExternalSyncWorkspaces,
  rotateExternalSyncSecret,
  syncExternalSyncNow,
  testExternalSyncConnection,
  updateExternalSyncSource,
  type ExternalSyncSource,
  type ExternalSyncWorkspaceOption,
} from '@/api/adminExternalSync'
import { formatApiError, isFormValidationError } from '@/api/index'
import { formatDate } from '@/utils'
import './AdminPage.css'

type CreateForm = {
  workspace_id: number
  secret: string
  database_id: string
  is_active: boolean
}

export default function AdminExternalSyncPage() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [items, setItems] = useState<ExternalSyncSource[]>([])
  const [workspaces, setWorkspaces] = useState<ExternalSyncWorkspaceOption[]>([])
  const [loading, setLoading] = useState(true)
  const [policyHint, setPolicyHint] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm<CreateForm>()

  async function load() {
    setLoading(true)
    try {
      const [srcRes, wsRes, hintRes] = await Promise.all([
        listExternalSyncSources(),
        listExternalSyncWorkspaces(),
        getExternalSyncDeletePolicyHint(),
      ])
      setItems(srcRes.data)
      setWorkspaces(wsRes.data)
      setPolicyHint(hintRes.data.hint)
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
      await createExternalSyncSource({
        workspace_id: v.workspace_id,
        provider: 'notion',
        secret: v.secret.trim(),
        config_public_json: { database_id: v.database_id.trim() },
        delete_policy: 'keep_file',
        is_active: v.is_active,
      })
      message.success(t('adminExternalSync.created'))
      setCreateOpen(false)
      form.resetFields()
      await load()
    } catch (e) {
      if (isFormValidationError(e)) return
      message.error(formatApiError(e))
    } finally {
      setCreating(false)
    }
  }

  async function handleTest(row: ExternalSyncSource) {
    try {
      const res = await testExternalSyncConnection(row.id)
      message.success(t('adminExternalSync.testOk', { id: res.data.database_id }))
    } catch (e) {
      message.error(formatApiError(e))
    }
  }

  async function handleSync(row: ExternalSyncSource) {
    try {
      const res = await syncExternalSyncNow(row.id)
      message.success(t('adminExternalSync.syncAccepted', { runId: res.data.run_id }))
    } catch (e) {
      message.error(formatApiError(e))
    }
  }

  function handleRotate(row: ExternalSyncSource) {
    let secret = ''
    Modal.confirm({
      title: t('adminExternalSync.rotateTitle'),
      content: (
        <Input.Password
          placeholder={t('adminExternalSync.secretPlaceholder')}
          onChange={(e) => {
            secret = e.target.value
          }}
        />
      ),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        if (!secret.trim()) {
          message.warning(t('adminExternalSync.secretRequired'))
          return Promise.reject()
        }
        await rotateExternalSyncSecret(row.id, secret.trim())
        message.success(t('adminExternalSync.rotated'))
        await load()
      },
    })
  }

  async function toggleActive(row: ExternalSyncSource, active: boolean) {
    try {
      await updateExternalSyncSource(row.id, { is_active: active })
      await load()
    } catch (e) {
      message.error(formatApiError(e))
    }
  }

  const columns: ColumnsType<ExternalSyncSource> = [
    { title: 'ID', dataIndex: 'id', width: 72 },
    {
      title: t('adminExternalSync.colWorkspace'),
      dataIndex: 'workspace_id',
      render: (id: number) => workspaces.find((w) => w.id === id)?.name ?? id,
    },
    { title: t('adminExternalSync.colProvider'), dataIndex: 'provider' },
    {
      title: t('adminExternalSync.colSecret'),
      dataIndex: 'secret_preview',
      render: (v: string) => `••••${v}`,
    },
    {
      title: t('adminExternalSync.colActive'),
      dataIndex: 'is_active',
      render: (v: boolean, row) => <Switch checked={v} onChange={(c) => void toggleActive(row, c)} />,
    },
    {
      title: t('adminExternalSync.colLastSync'),
      dataIndex: 'last_sync_at',
      render: (v: string | null) => (v ? formatDate(v) : '—'),
    },
    {
      title: t('adminExternalSync.colActions'),
      key: 'actions',
      render: (_, row) => (
        <Space wrap>
          <Button size="small" onClick={() => void handleTest(row)}>
            {t('adminExternalSync.test')}
          </Button>
          <Button size="small" onClick={() => handleRotate(row)}>
            {t('adminExternalSync.rotate')}
          </Button>
          <Button size="small" type="primary" onClick={() => void handleSync(row)}>
            {t('adminExternalSync.syncNow')}
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div className="admin-page">
      <div className="admin-card">
        <div className="admin-header">
          <div className="ah-title-group">
            <h1 className="admin-title ah-title">{t('adminExternalSync.title')}</h1>
            <span className="admin-subtitle ah-sub">{t('adminExternalSync.subtitle')}</span>
          </div>
          <Button type="primary" onClick={() => setCreateOpen(true)}>
            {t('adminExternalSync.create')}
          </Button>
        </div>
        {policyHint ? (
          <Alert type="info" showIcon message={policyHint} style={{ marginBottom: 16 }} />
        ) : null}
        <div className="admin-table-wrap">
          <Table rowKey="id" loading={loading} columns={columns} dataSource={items} pagination={false} scroll={{ x: 'max-content' }} />
        </div>
      </div>

      <Modal
        title={t('adminExternalSync.createTitle')}
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
        <Alert type="info" showIcon message={policyHint || t('adminExternalSync.deletePolicyHint')} style={{ marginBottom: 16 }} />
        <Form form={form} layout="vertical" initialValues={{ is_active: true }}>
          <Form.Item name="workspace_id" label={t('adminExternalSync.fieldWorkspace')} rules={[{ required: true }]}>
            <Select
              options={workspaces.map((w) => ({
                value: w.id,
                label: `${w.name} (${w.kind === 'shared' ? t('adminExternalSync.kindShared') : t('adminExternalSync.kindPersonal')})`,
              }))}
            />
          </Form.Item>
          <Form.Item name="database_id" label={t('adminExternalSync.fieldDatabaseId')} rules={[{ required: true }]}>
            <Input placeholder="Notion database_id" />
          </Form.Item>
          <Form.Item name="secret" label={t('adminExternalSync.fieldSecret')} rules={[{ required: true, min: 8 }]}>
            <Input.Password placeholder={t('adminExternalSync.secretPlaceholder')} />
          </Form.Item>
          <Form.Item name="is_active" label={t('adminExternalSync.fieldActive')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
