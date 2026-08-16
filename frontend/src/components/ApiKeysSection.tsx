import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { App, Button, Input, Modal, Space, Spin, Switch, Table, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteActionIcon } from '@/components/DeleteActionIcon'
import { CopyOutlined, LoadingOutlined } from '@ant-design/icons'
import {
  createApiKey,
  deleteApiKey,
  getApiKeys,
  patchApiKey,
  revealApiKey,
  type ApiKeyCreateResponse,
  type ApiKeyItem,
} from '@/api/apiKeys'
import { copyToClipboard, formatDate } from '@/utils'
import '@/pages/ApiKeys.css'

const MODAL_WIDTH = 'min(560px, calc(100vw - 32px))'

type Props = {
  embedded?: boolean
}

export default function ApiKeysSection({ embedded = false }: Props) {
  const { message: msg, modal } = App.useApp()
  const { t } = useTranslation()
  const [keys, setKeys] = useState<ApiKeyItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newKeyName, setNewKeyName] = useState('')
  const [newKeyData, setNewKeyData] = useState<ApiKeyCreateResponse | null>(null)
  const [patchingId, setPatchingId] = useState<number | null>(null)
  const [copyingId, setCopyingId] = useState<number | null>(null)
  const [previewPlainById, setPreviewPlainById] = useState<Record<number, string>>({})
  const [previewErrorById, setPreviewErrorById] = useState<Record<number, true>>({})
  const [previewLoadingId, setPreviewLoadingId] = useState<number | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)

  async function loadKeys() {
    setLoading(true)
    try {
      const res = await getApiKeys()
      setKeys(res.data)
    } catch {
      /* interceptor */
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadKeys()
  }, [])

  async function doCreate() {
    const name = newKeyName.trim()
    if (!name) {
      msg.warning(t('apiKeys.nameRequired'))
      return
    }
    if (creating) return
    setCreating(true)
    try {
      const res = await createApiKey(name)
      setNewKeyData(res.data)
      setPreviewPlainById((m) => ({ ...m, [res.data.id]: res.data.plain_text_key }))
      await loadKeys()
    } catch {
      /* interceptor */
    } finally {
      setCreating(false)
    }
  }

  function closeCreate() {
    setShowCreate(false)
    setNewKeyName('')
    setNewKeyData(null)
  }

  async function copyNewKey() {
    if (!newKeyData) return
    try {
      await copyToClipboard(newKeyData.plain_text_key)
      msg.success(t('apiKeys.copyComplete'))
    } catch {
      msg.error(t('apiKeys.copyFailed'))
    }
  }

  async function copyExistingKey(row: ApiKeyItem) {
    if (!row.can_reveal) {
      Modal.info({
        title: t('apiKeys.cannotReveal'),
        width: MODAL_WIDTH,
        content: <p style={{ whiteSpace: 'pre-line', margin: 0 }}>{t('apiKeys.cannotRevealDetail')}</p>,
      })
      return
    }
    setCopyingId(row.id)
    try {
      const res = await revealApiKey(row.id)
      await copyToClipboard(res.data.plain_text_key)
      setPreviewPlainById((m) => ({ ...m, [row.id]: res.data.plain_text_key }))
      msg.success(t('apiKeys.copyComplete'))
    } catch {
      msg.error(t('apiKeys.copyFailed'))
    } finally {
      setCopyingId(null)
    }
  }

  function openDeleteConfirm(row: ApiKeyItem) {
    modal.confirm({
      title: t('apiKeys.deleteConfirm', { name: row.name }),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okType: 'danger',
      centered: true,
      onOk: async () => {
        setDeletingId(row.id)
        try {
          await deleteApiKey(row.id)
          setPreviewPlainById((m) => {
            const next = { ...m }
            delete next[row.id]
            return next
          })
          setPreviewErrorById((m) => {
            const next = { ...m }
            delete next[row.id]
            return next
          })
          msg.success(t('apiKeys.deleted'))
          await loadKeys()
        } finally {
          setDeletingId(null)
        }
      },
    })
  }

  async function onToggleActive(row: ApiKeyItem, checked: boolean) {
    setPatchingId(row.id)
    try {
      await patchApiKey(row.id, { is_active: checked })
      msg.success(checked ? t('apiKeys.statusOn') : t('apiKeys.statusOff'))
      await loadKeys()
    } catch {
      /* interceptor */
    } finally {
      setPatchingId(null)
    }
  }

  async function onPreviewTooltipOpen(row: ApiKeyItem, open: boolean) {
    if (!open || !row.can_reveal) return
    if (previewPlainById[row.id]) return
    setPreviewLoadingId(row.id)
    try {
      const res = await revealApiKey(row.id, { preview: true })
      setPreviewPlainById((m) => ({ ...m, [row.id]: res.data.plain_text_key }))
      setPreviewErrorById((m) => {
        const next = { ...m }
        delete next[row.id]
        return next
      })
    } catch {
      setPreviewErrorById((m) => ({ ...m, [row.id]: true }))
    } finally {
      setPreviewLoadingId(null)
    }
  }

  function previewTooltipTitle(row: ApiKeyItem) {
    if (!row.can_reveal) return t('apiKeys.tooltipNoDecrypt')
    if (previewErrorById[row.id]) return t('apiKeys.previewFailed')
    const plain = previewPlainById[row.id]
    if (plain) {
      return <span className="ak-tooltip-plain">{plain}</span>
    }
    if (previewLoadingId === row.id) {
      return (
        <span className="ak-create-loading">
          <Spin size="small" /> {t('apiKeys.previewLoading')}
        </span>
      )
    }
    return t('apiKeys.previewLoading')
  }

  const columns: ColumnsType<ApiKeyItem> = useMemo(
    () => [
    { title: t('apiKeys.name'), dataIndex: 'name', key: 'name', ellipsis: true },
    {
      title: t('apiKeys.keyPreview'),
      key: 'prefix',
      width: 112,
      ellipsis: true,
      render: (_, row) => {
        const trigger = (
          <span
            className={
              'ak-prefix-trigger' + (row.can_reveal ? '' : ' ak-prefix-trigger--disabled')
            }
          >
            {row.prefix}…
          </span>
        )
        return (
          <Tooltip
            title={previewTooltipTitle(row)}
            mouseEnterDelay={0.12}
            overlayStyle={{ maxWidth: 480 }}
            onOpenChange={(open) => void onPreviewTooltipOpen(row, open)}
          >
            {trigger}
          </Tooltip>
        )
      },
    },
    {
      title: t('apiKeys.active'),
      key: 'active',
      width: 72,
      align: 'center',
      render: (_, row) => (
        <Switch
          size="small"
          checked={row.is_active}
          loading={patchingId === row.id}
          onChange={(checked) => void onToggleActive(row, checked)}
        />
      ),
    },
    {
      title: t('apiKeys.created'),
      dataIndex: 'created_at',
      key: 'c',
      width: 148,
      ellipsis: true,
      render: (d: string) => (
        <span className="ak-date-cell" title={formatDate(d)}>
          {formatDate(d)}
        </span>
      ),
    },
    {
      title: t('apiKeys.lastUsed'),
      dataIndex: 'last_used_at',
      key: 'lu',
      width: 148,
      ellipsis: true,
      render: (d: string | null) => {
        const text = d ? formatDate(d) : '—'
        return (
          <span className="ak-date-cell" title={d ? text : undefined}>
            {text}
          </span>
        )
      },
    },
    {
      title: t('apiKeys.ops'),
      key: 'ops',
      width: 72,
      align: 'center',
      render: (_, row) => (
        <Space size={0} className="ak-ops-actions">
          <Tooltip title={t('apiKeys.copyKey')}>
            <Button
              type="text"
              size="small"
              className="ak-ops-btn"
              disabled={!row.is_active}
              loading={copyingId === row.id}
              icon={copyingId === row.id ? <LoadingOutlined /> : <CopyOutlined />}
              aria-label={t('apiKeys.copyKey')}
              onClick={() => void copyExistingKey(row)}
            />
          </Tooltip>
          <Tooltip title={t('apiKeys.delete')}>
            <Button
              type="text"
              size="small"
              danger
              className="ak-ops-btn ak-ops-btn--danger"
              loading={deletingId === row.id}
              icon={<DeleteActionIcon />}
              aria-label={t('apiKeys.delete')}
              onClick={() => openDeleteConfirm(row)}
            />
          </Tooltip>
        </Space>
      ),
    },
    ],
    [
      t,
      patchingId,
      copyingId,
      previewPlainById,
      previewErrorById,
      previewLoadingId,
      deletingId,
    ],
  )

  const rootClass = embedded ? "apikeys-root apikeys-root--embedded" : "apikeys-root"

  return (
    <div className={rootClass}>
      <div className="apikeys-header">
        <div className="ah-title-group">
          <h2 className="ah-title">{t('apiKeys.title')}</h2>
          {!embedded ? <span className="ah-sub">{t('apiKeys.subtitle')}</span> : null}
        </div>
        <Button type="primary" size="small" onClick={() => setShowCreate(true)}>
          + {t('apiKeys.create')}
        </Button>
      </div>
      {!embedded ? (
        <div className="apikeys-info">
          <span className="api-info-text">{t('apiKeys.info')}</span>
        </div>
      ) : null}
      <div className="apikeys-panel">
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={keys}
          pagination={false}
          tableLayout="fixed"
          className="apikeys-table"
        />
      </div>

      <Modal
        open={showCreate}
        title={t('apiKeys.createTitle')}
        width={MODAL_WIDTH}
        rootClassName="apikeys-modal"
        styles={{ body: { maxWidth: '100%' } }}
        onCancel={closeCreate}
        footer={
          newKeyData ? (
            <Space>
              <Button type="primary" icon={<CopyOutlined />} onClick={() => void copyNewKey()}>
                {t('apiKeys.copyKey')}
              </Button>
              <Button onClick={closeCreate}>{t('apiKeys.confirmSaved')}</Button>
            </Space>
          ) : (
            <Space>
              <Button onClick={closeCreate}>{t('common.cancel')}</Button>
              <Button type="primary" loading={creating} onClick={() => void doCreate()}>
                {t('apiKeys.generate')}
              </Button>
            </Space>
          )
        }
      >
        {!newKeyData ? (
          <Input
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            placeholder={t('apiKeys.namePlaceholder')}
            size="large"
            disabled={creating}
            onPressEnter={() => void doCreate()}
            autoFocus
          />
        ) : (
          <div className="ak-result">
            <p className="ak-result-msg">{t('apiKeys.saveKey')}</p>
            <p className="ak-result-key">
              <code>{newKeyData.prefix}…</code>
            </p>
            <p className="ak-result-sub">{t('apiKeys.saveKeySub')}</p>
          </div>
        )}
      </Modal>
    </div>
  )
}
