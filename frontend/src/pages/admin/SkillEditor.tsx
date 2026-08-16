import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Menu,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd'
import type { MenuProps } from 'antd'
import { useTranslation } from 'react-i18next'
import '@/utils/markedPreview'
import {
  getAdminSkillFile,
  listAdminSkillFiles,
  syncSkillFromDisk,
  type AdminSkillFileItem,
} from '@/api/adminSkill'
import { renderMarkdownWithSyncBlocks } from '@/utils/mdSyncRender'
import '@/components/FileList.css'
import '@/components/MdEditor.css'
import './AdminPage.css'

const GROUP_ORDER = ['bootstrap', 'modules', 'references', 'api-ref', 'meta', 'other'] as const

function groupLabel(t: (k: string) => string, group: string) {
  switch (group) {
    case 'bootstrap':
      return t('admin.skillEditor.groupBootstrap')
    case 'modules':
      return t('admin.skillEditor.groupModules')
    case 'meta':
      return t('admin.skillEditor.groupMeta')
    case 'api-ref':
      return t('admin.skillEditor.groupApiRef')
    case 'references':
      return t('admin.skillEditor.groupReferences')
    case 'other':
      return t('admin.skillEditor.groupOther')
    default:
      return group
  }
}

export default function AdminSkillEditorPage() {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [notReady, setNotReady] = useState(false)
  const [cacheEnabled, setCacheEnabled] = useState(false)
  const [skillVersion, setSkillVersion] = useState<string | null>(null)
  const [diskSkillVersion, setDiskSkillVersion] = useState<string | null>(null)
  const [files, setFiles] = useState<AdminSkillFileItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [content, setContent] = useState('')
  const [kind, setKind] = useState('markdown')
  const [fileLoading, setFileLoading] = useState(false)

  const previewHtml = useMemo(() => {
    if (kind !== 'markdown') return ''
    try {
      return renderMarkdownWithSyncBlocks(content || '')
    } catch {
      return ''
    }
  }, [content, kind])

  const loadList = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listAdminSkillFiles()
      const ready = res.data.data_ready !== false
      setNotReady(!ready)
      setCacheEnabled(Boolean(res.data.cache_enabled))
      setSkillVersion(res.data.skill_version ?? null)
      setDiskSkillVersion(res.data.disk_skill_version ?? null)
      setFiles(res.data.files)
      if (!selectedId && res.data.files.length > 0) {
        setSelectedId(res.data.files[0].file_id)
      } else if (selectedId && !res.data.files.some((f) => f.file_id === selectedId)) {
        setSelectedId(res.data.files[0]?.file_id ?? null)
      }
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 503) {
        setNotReady(true)
        setFiles([])
        setSkillVersion(null)
        setDiskSkillVersion(null)
      }
    } finally {
      setLoading(false)
    }
  }, [selectedId])

  const loadFile = useCallback(async (fileId: string) => {
    setFileLoading(true)
    try {
      const res = await getAdminSkillFile(fileId)
      setContent(res.data.content)
      setKind(res.data.kind)
    } catch {
      setContent('')
    } finally {
      setFileLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadList()
  }, [loadList])

  useEffect(() => {
    if (selectedId && !notReady) void loadFile(selectedId)
  }, [selectedId, notReady, loadFile])

  async function handleSyncFromDisk() {
    setSyncing(true)
    try {
      const res = await syncSkillFromDisk()
      const { added, updated, removed, reason, skill_dir: skillDir } = res.data
      if (
        reason === 'scan_empty' ||
        reason === 'scan_missing_bootstrap' ||
        reason === 'scan_no_modules'
      ) {
        message.warning(
          `${t('admin.skillEditor.syncFailedScan')}${skillDir ? ` (${skillDir})` : ''}`,
        )
        await loadList()
        return
      }
      const parts: string[] = []
      if (skillDir) parts.push(skillDir)
      if (added.length) parts.push(t('admin.skillEditor.syncAdded', { count: added.length }))
      if (updated.length) parts.push(t('admin.skillEditor.syncUpdated', { count: updated.length }))
      if (removed.length) parts.push(t('admin.skillEditor.syncRemoved', { count: removed.length }))
      message.success(parts.length ? parts.join(' · ') : t('admin.skillEditor.syncDone'))
      setNotReady(false)
      await loadList()
    } catch {
      /* interceptor */
    } finally {
      setSyncing(false)
    }
  }

  const menuItems: MenuProps['items'] = useMemo(() => {
    const byGroup = new Map<string, AdminSkillFileItem[]>()
    for (const f of files) {
      const list = byGroup.get(f.group) || []
      list.push(f)
      byGroup.set(f.group, list)
    }
    return GROUP_ORDER.filter((g) => byGroup.has(g)).map((group) => ({
      type: 'group' as const,
      label: groupLabel(t, group),
      children: (byGroup.get(group) || []).map((f) => ({
        key: f.file_id,
        label: f.label,
      })),
    }))
  }, [files, t])

  function renderPreview() {
    if (kind === 'markdown') {
      return (
        <div
          className="me-preview fb-markdown-host markdown-body"
          dangerouslySetInnerHTML={{ __html: previewHtml }}
        />
      )
    }
    if (kind === 'json') {
      let formatted = content
      try {
        formatted = JSON.stringify(JSON.parse(content), null, 2)
      } catch {
        /* raw */
      }
      return <pre className="admin-skill-editor-raw admin-skill-editor-raw--in-pane">{formatted}</pre>
    }
    return <pre className="admin-skill-editor-raw admin-skill-editor-raw--in-pane">{content}</pre>
  }

  return (
    <div className="admin-root">
      <div className="admin-panel admin-skill-editor">
        <header className="admin-header">
          <div className="ah-title-group">
            <Typography.Title level={3} className="admin-title ah-title">
              {t('admin.skillEditor.title')}
            </Typography.Title>
          </div>
          <Space wrap>
            <div className="admin-skill-version-block" aria-label={t('admin.skillEditor.skillVersionAria')}>
              <Typography.Text type="secondary" className="admin-skill-version-line">
                <span className="admin-skill-version-label">{t('admin.skillEditor.skillVersionDb')}</span>
                <span className="admin-skill-version-value">{skillVersion ?? '—'}</span>
              </Typography.Text>
              <Typography.Text type="secondary" className="admin-skill-version-line">
                <span className="admin-skill-version-label">{t('admin.skillEditor.skillVersionDisk')}</span>
                <span className="admin-skill-version-value">{diskSkillVersion ?? '—'}</span>
              </Typography.Text>
            </div>
            {!cacheEnabled ? (
              <Tag color="orange">{t('admin.skillEditor.cacheOff')}</Tag>
            ) : null}
            <Button type="primary" loading={syncing} onClick={() => void handleSyncFromDisk()}>
              {t('admin.skillEditor.syncFromDisk')}
            </Button>
            <Button onClick={() => void loadList()} disabled={loading}>
              {t('admin.skillEditor.refresh')}
            </Button>
          </Space>
        </header>

        {notReady ? (
          <Alert
            type="warning"
            showIcon
            message={t('admin.skillEditor.notReadyTitle')}
            description={t('admin.skillEditor.notReadyHint')}
            style={{ marginBottom: 16 }}
          />
        ) : null}

        {loading ? (
          <div className="admin-skill-editor-loading">
            <Spin />
          </div>
        ) : notReady ? (
          <div className="admin-skill-editor-loading">
            <Typography.Text type="secondary">{t('admin.skillEditor.notReadyHint')}</Typography.Text>
          </div>
        ) : (
          <div className="admin-skill-editor-body">
            <aside className="admin-skill-editor-sidebar">
              <Menu
                mode="inline"
                selectedKeys={selectedId ? [selectedId] : []}
                items={menuItems}
                onClick={({ key }) => setSelectedId(String(key))}
              />
            </aside>
            <section className="admin-skill-editor-main admin-skill-editor-main--preview fl-table-shell">
              <div className="fl-body">
                {fileLoading ? (
                  <Spin />
                ) : selectedId ? (
                  <div className="admin-skill-editor-preview-pane admin-skill-editor-preview-pane--full me-preview-pane">
                    {renderPreview()}
                  </div>
                ) : (
                  <Typography.Text type="secondary">{t('admin.skillEditor.selectFile')}</Typography.Text>
                )}
              </div>
            </section>
          </div>
        )}

      </div>
    </div>
  )
}
