import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Dropdown, Empty, Input, Spin } from 'antd'
import NavMenuLabel from './NavMenuLabel'
import { getFiles, type FileItem } from '@/api/files'
import { getActiveWorkspaceId } from '@/stores/workspaceStore'
import { useFoldersStore } from '@/stores/foldersStore'
import { fileTypeIcon } from '@/utils/fileIcons'
import './KnowledgeFilesMenu.css'

const MENU_PAGE_SIZE = 50

export default function KnowledgeFilesMenu() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const loc = useLocation()
  const routeActive = loc.pathname === '/' || loc.pathname === '/files' || loc.pathname.startsWith('/files/')
  const [open, setOpen] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [debouncedKeyword, setDebouncedKeyword] = useState('')
  const [items, setItems] = useState<FileItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setDebouncedKeyword(keyword.trim())
    }, 280)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [keyword])

  const loadMenu = useCallback(async () => {
    setLoading(true)
    try {
      const wsId = getActiveWorkspaceId()
      const res = await getFiles({
        workspace_id: wsId ?? undefined,
        search: debouncedKeyword || undefined,
        page: 1,
        page_size: MENU_PAGE_SIZE,
        sort_time: 'desc',
      })
      setItems(res.data.items)
      setTotal(res.data.total)
    } catch {
      setItems([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [debouncedKeyword])

  useEffect(() => {
    if (!open) return
    void loadMenu()
  }, [open, loadMenu])

  const openAllFilesScope = () => {
    useFoldersStore.getState().setSelected('all')
  }

  const openFile = (file: FileItem) => {
    setOpen(false)
    openAllFilesScope()
    navigate(`/?preview=${file.id}`)
  }

  const panel = (
    <div className="kfm-panel" role="dialog" aria-label={t('knowledgeFilesMenu.panelAria')}>
      <div className="kfm-panel-head">
        <span className="kfm-panel-title">{t('knowledgeFilesMenu.title')}</span>
        {total > 0 ? (
          <span className="kfm-panel-count">{t('knowledgeFilesMenu.count', { count: total })}</span>
        ) : null}
      </div>
      <Input.Search
        allowClear
        size="small"
        className="kfm-search"
        placeholder={t('knowledgeFilesMenu.searchPlaceholder')}
        value={keyword}
        onChange={(e) => setKeyword(e.target.value)}
        onSearch={(v) => setKeyword(v)}
      />
      <div className="kfm-list" role="listbox">
        {loading ? (
          <div className="kfm-loading">
            <Spin size="small" />
          </div>
        ) : items.length === 0 ? (
          <Empty className="kfm-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('knowledgeFilesMenu.empty')} />
        ) : (
          items.map((file) => (
            <button
              key={file.id}
              type="button"
              className="kfm-item"
              role="option"
              onClick={() => openFile(file)}
            >
              <span className="kfm-item-icon" aria-hidden>
                {fileTypeIcon(file.mime_type, file.original_name)}
              </span>
              <span className="kfm-item-name" title={file.original_name}>
                {file.original_name}
              </span>
            </button>
          ))
        )}
      </div>
      <div className="kfm-footer">
        <Link to="/" className="kfm-view-all" onClick={() => { setOpen(false); openAllFilesScope() }}>
          {total > items.length
            ? t('knowledgeFilesMenu.viewAllMore', { count: total })
            : t('knowledgeFilesMenu.viewAll')}
        </Link>
      </div>
    </div>
  )

  return (
    <Dropdown
      open={open}
      onOpenChange={setOpen}
      trigger={['click']}
      placement="bottomLeft"
      dropdownRender={() => panel}
    >
      <button
        type="button"
        className={'nav-link nav-link--with-icon kfm-trigger' + (open || routeActive ? ' active' : '')}
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <NavMenuLabel icon="myFiles">{t('appLayout.myFiles')}</NavMenuLabel>
      </button>
    </Dropdown>
  )
}
