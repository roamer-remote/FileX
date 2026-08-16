import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { App, Button, Pagination, Select, Space, Spin, Table, Tooltip } from 'antd'
import {
  CaretDownOutlined,
  CaretUpOutlined,
  DownloadOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import api from '@/api/index'
import { adminRebuildWikiLinks, adminWikiLint, getAdminFiles, postAdminKbReindexAll } from '@/api/admin'
import { getFileById, type FileItem } from '@/api/files'
import { downloadAuthenticatedFile, getDownloadUrl } from '@/api/files'
import { useWikiLinkNavigation } from '@/hooks/useWikiLinkNavigation'
import FilePreview from '@/components/FilePreview'
import MdNoteViewModal, { MD_NOTE_VIEW_MODAL_Z_INDEX } from '@/components/MdNoteViewModal'
import KnowledgeFilenameSearch from '@/components/KnowledgeFilenameSearch'
import { formatDate, formatFileSize } from '@/utils'
import { fileTypeIcon } from '@/utils/fileIcons'
import { useFlexTableBodyScrollY } from '@/hooks/useFlexTableBodyScrollY'
import '@/components/FileList.css'
import '@/components/knowledge/KnowledgeLobbyToolbar.css'
import './AdminPage.css'

interface UserRow {
  id: number
  username: string
}

function renderAdminFileTimeTooltip(row: FileItem, t: (k: string) => string) {
  return (
    <div>
      <div>
        {t('fileList.createdAtLabel')}: {formatDate(row.created_at)}
      </div>
      <div>
        {t('fileList.updatedAtLabel')}: {row.updated_at ? formatDate(row.updated_at) : '—'}
      </div>
    </div>
  )
}

function formatAdminLastUpdatedCell(row: FileItem) {
  return row.updated_at ? formatDate(row.updated_at) : '—'
}

export default function AdminAllFilesPage() {
  const { t } = useTranslation()
  const { message, modal } = App.useApp()
  const [files, setFiles] = useState<FileItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(true)
  const [users, setUsers] = useState<UserRow[]>([])
  const [filterUserId, setFilterUserId] = useState<number | undefined>(undefined)
  const [draftSearch, setDraftSearch] = useState('')
  const [keyword, setKeyword] = useState('')
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewFile, setPreviewFile] = useState<FileItem | null>(null)
  const [mdNoteOpen, setMdNoteOpen] = useState(false)
  const [mdNoteFile, setMdNoteFile] = useState<FileItem | null>(null)
  const [timeSortOrder, setTimeSortOrder] = useState<'desc' | 'asc'>('desc')
  const [reindexAllLoading, setReindexAllLoading] = useState(false)
  const [wikiLintLoading, setWikiLintLoading] = useState(false)
  const [wikiRebuildLoading, setWikiRebuildLoading] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)


  useWikiLinkNavigation((fileId) => {
    void getFileById(fileId)
      .then((res) => {
        setPreviewFile(res.data)
        setPreviewOpen(true)
      })
      .catch(() => undefined)
  })

  const loadFiles = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getAdminFiles({
        page,
        page_size: pageSize,
        search: keyword || undefined,
        user_id: filterUserId,
        sort_time: timeSortOrder,
      })
      setFiles(res.data.items)
      setTotal(res.data.total)
    } catch {
      /* axios interceptor */
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, keyword, filterUserId, timeSortOrder])

  useEffect(() => {
    void loadFiles()
  }, [loadFiles])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const res = await api.get<{ items: UserRow[] }>('/admin/users', { params: { page: 1, page_size: 100 } })
        if (!cancelled) setUsers(res.data.items)
      } catch {
        /* interceptor */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const scrollY = useFlexTableBodyScrollY([loading, files.length, page, pageSize], {
    bodyRef,
  })

  const tableScroll = files.length > 0 && scrollY > 0 ? { y: scrollY } : undefined

  function applySearch() {
    setKeyword(draftSearch.trim())
    setPage(1)
  }

  function onFilterUser(uid: number | undefined) {
    setFilterUserId(uid)
    setPage(1)
  }

  function toggleAdminTimeSort() {
    setPage(1)
    setTimeSortOrder(timeSortOrder === 'desc' ? 'asc' : 'desc')
  }


  function confirmWikiRebuild() {
    modal.confirm({
      title: t('admin.allFiles.wikiRebuildConfirmTitle'),
      content: t('admin.allFiles.wikiRebuildConfirmContent'),
      okText: t('admin.allFiles.wikiRebuildBtn'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        setWikiRebuildLoading(true)
        try {
          const res = await adminRebuildWikiLinks({ user_id: filterUserId })
          const { rebuilt_count: count, file_count: total } = res.data
          message.success(t('admin.allFiles.wikiRebuildOk', { count, total }))
        } catch {
          message.error(t('admin.allFiles.wikiRebuildFailed'))
        } finally {
          setWikiRebuildLoading(false)
        }
      },
    })
  }

  async function runWikiLint() {
    setWikiLintLoading(true)
    try {
      await adminWikiLint(filterUserId != null ? { user_id: filterUserId } : undefined)
      message.success(t('admin.allFiles.wikiLintOk'))
    } catch {
      message.error(t('admin.allFiles.wikiLintFailed'))
    } finally {
      setWikiLintLoading(false)
    }
  }

  function confirmReindexAll() {
    modal.confirm({
      title: t('admin.allFiles.reindexAllConfirmTitle'),
      icon: <ExclamationCircleOutlined style={{ color: 'var(--warning)' }} />,
      content: t('admin.allFiles.reindexAllConfirmContent'),
      okText: t('admin.allFiles.reindexAllBtn'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      centered: true,
      onOk: async () => {
        setReindexAllLoading(true)
        try {
          const res = await postAdminKbReindexAll({
            user_id: filterUserId,
            force: true,
          })
          const { enqueued_count: count, candidate_count: total } = res.data
          if (count <= 0) {
            message.warning(t('admin.allFiles.reindexAllEmpty', { total }))
            return
          }
          message.success(t('admin.allFiles.reindexAllOk', { count, total }))
        } catch {
          message.error(t('admin.allFiles.reindexAllFailed'))
          throw new Error('reindex failed')
        } finally {
          setReindexAllLoading(false)
        }
      },
    })
  }

  const columns: ColumnsType<FileItem> = [
    {
      title: t('admin.allFiles.colId'),
      dataIndex: 'id',
      width: 72,
      align: 'right',
      className: 'fl-id-col',
      render: (id: number) => <span className="fl-id-cell">{id}</span>,
    },
    {
      title: t('fileList.object'),
      key: 'name',
      ellipsis: true,
      className: 'fl-name-col',
      render: (_: unknown, row: FileItem) => (
        <div className="fl-name">
          <span className="fl-name-ico">{fileTypeIcon(row.mime_type, row.original_name)}</span>
          <button
            type="button"
            className="fl-name-text fl-name-open"
            title={row.original_name}
            onClick={() => {
              setPreviewFile(row)
              setPreviewOpen(true)
            }}
          >
            {row.original_name}
          </button>
        </div>
      ),
    },
    {
      title: t('libraryMap.mdNote'),
      key: 'note',
      width: 64,
      align: 'center',
      className: 'fl-md-col',
      render: (_: unknown, row: FileItem) =>
        row.has_md ? (
          row.md_has_content ? (
            <Tooltip title={t('libraryMap.viewNoteContent')}>
              <button
                type="button"
                className="fl-md-badge fl-md-badge--filled fl-md-badge--btn"
                onClick={() => {
                  setMdNoteFile(row)
                  setMdNoteOpen(true)
                }}
              >
                MD
              </button>
            </Tooltip>
          ) : (
            <Tooltip title={t('fileList.mdNoteNotReady')}>
              <span className="fl-md-badge fl-md-badge--idle">MD</span>
            </Tooltip>
          )
        ) : (
          <span className="fl-md-note-empty">—</span>
        ),
    },
    {
      title: t('admin.allFiles.owner'),
      key: 'owner',
      width: 88,
      align: 'left',
      ellipsis: true,
      className: 'admin-af-col-owner',
      render: (_: unknown, row: FileItem) => {
        const text = row.username ?? `#${row.user_id}`
        return (
          <span className="admin-af-owner" title={text}>
            {text}
          </span>
        )
      },
    },
    {
      title: t('fileList.size'),
      width: 88,
      render: (_: unknown, row: FileItem) => (
        <span className="fl-size-cell">{formatFileSize(row.file_size)}</span>
      ),
    },
    {
      key: 'time',
      title: (
        <button
          type="button"
          className="fl-time-sort-th"
          title={t('fileList.sortTimeTooltip')}
          aria-label={t('fileList.sortTimeTooltip')}
          onClick={() => toggleAdminTimeSort()}
        >
          <span className="fl-time-sort-th__label">{t('fileList.lastUpdatedAt')}</span>
          <span className="fl-time-sort-th__icons" aria-hidden>
            <CaretUpOutlined className={timeSortOrder === 'asc' ? 'fl-time-sort-th__ico--on' : 'fl-time-sort-th__ico--off'} />
            <CaretDownOutlined className={timeSortOrder === 'desc' ? 'fl-time-sort-th__ico--on' : 'fl-time-sort-th__ico--off'} />
          </span>
        </button>
      ),
      width: 168,
      align: 'right',
      render: (_: unknown, row: FileItem) => (
        <Tooltip title={renderAdminFileTimeTooltip(row, t)}>
          <span className="fl-time-cell">{formatAdminLastUpdatedCell(row)}</span>
        </Tooltip>
      ),
    },
    {
      title: t('fileList.ops'),
      key: 'ops',
      width: 48,
      align: 'center',
      className: 'fl-ops-col',
      render: (_: unknown, row: FileItem) => (
        <div className="fl-ops-cell">
          <Button
            type="text"
            size="small"
            icon={<DownloadOutlined />}
            title={t('admin.allFiles.download')}
            onClick={() => {
              void downloadAuthenticatedFile(getDownloadUrl(row.id), row.original_name).catch(() => {
                message.error(t('messages.downloadFailed'))
              })
            }}
          />
        </div>
      ),
    },
  ]

  return (
    <div className="admin-root">
      <div className="admin-panel admin-panel--files">
        <div className="admin-header">
          <div className="ah-title-group">
            <div className="ah-title-actions">
              <span className="ah-count-inline">
                <span className="ah-count-num">{total}</span>
                <span className="ah-count-label">{t('admin.allFiles.records')}</span>
              </span>
              <Button
                icon={<ReloadOutlined />}
                loading={reindexAllLoading}
                onClick={() => confirmReindexAll()}
              >
                {t('admin.allFiles.reindexAllBtn')}
              </Button>
              <Button loading={wikiLintLoading} onClick={() => void runWikiLint()}>
                {t('admin.allFiles.wikiLintBtn')}
              </Button>
              <Button loading={wikiRebuildLoading} onClick={() => confirmWikiRebuild()}>
                {t('admin.allFiles.wikiRebuildBtn')}
              </Button>
            </div>
          </div>
          <div className="ah-toolbar">
            <Space wrap>
              <Select
                allowClear
                placeholder={t('admin.allFiles.userFilter')}
                style={{ minWidth: 160 }}
                value={filterUserId}
                onChange={(v) => onFilterUser(v === null || v === undefined ? undefined : Number(v))}
                options={users.map((u) => ({ label: u.username, value: u.id }))}
              />
              <div className="knowledge-lobby-google-bar admin-allfiles-search-bar">
                <KnowledgeFilenameSearch
                  className="knowledge-lobby-google-bar__input knowledge-filename-search"
                  variant="borderless"
                  placeholderKey="admin.allFiles.searchPlaceholder"
                  submitAriaLabelKey="admin.allFiles.searchBtn"
                  value={draftSearch}
                  onChange={setDraftSearch}
                  onSubmit={() => applySearch()}
                  onClear={() => {
                    setDraftSearch('')
                    setKeyword('')
                    setPage(1)
                  }}
                />
              </div>
            </Space>
          </div>
        </div>

        <div className="admin-table-wrap admin-table-wrap--allfiles admin-table-wrap--flex fl-table-shell">
          <div className="fl-body" ref={bodyRef}>
            <Spin spinning={loading} className="fl-spin">
              <div className="fl-table-host">
                <Table<FileItem>
                  className="fl-file-table admin-allfiles-table"
                  rowKey="id"
                  columns={columns}
                  dataSource={files}
                  size="small"
                  pagination={false}
                  scroll={tableScroll}
                  tableLayout="fixed"
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
              onChange={(p, ps) => {
                setPage(p)
                setPageSize(ps)
              }}
            />
          </div>
        </div>

      </div>

      <FilePreview open={previewOpen} file={previewFile} onClose={() => setPreviewOpen(false)} adminMdApi />
      <MdNoteViewModal
        open={mdNoteOpen}
        file={mdNoteFile}
        onClose={() => setMdNoteOpen(false)}
        adminMdApi
        zIndex={MD_NOTE_VIEW_MODAL_Z_INDEX}
      />
    </div>
  )
}
