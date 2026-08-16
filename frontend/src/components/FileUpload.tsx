import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { App, Upload } from 'antd'
import type { UploadProps } from 'antd'
import { uploadFile, updateFile } from '@/api/files'
import { formatApiError } from '@/api/index'
import { getActiveWorkspaceId } from '@/stores/workspaceStore'
import { emitLibraryStatsRefresh } from '@/lib/libraryEvents'
import { useFilesStore } from '@/stores/filesStore'
import { useFoldersStore } from '@/stores/foldersStore'
import { uploadTargetFolderId } from '@/lib/folderTree'
import { useSystemSettingsStore } from '@/stores/systemSettingsStore'
import './FileUpload.css'

const allowed = [
  'pdf',
  'doc',
  'docx',
  'ppt',
  'pptx',
  'xls',
  'xlsx',
  'jpg',
  'jpeg',
  'png',
  'gif',
  'bmp',
  'webp',
  'txt',
  'md',
  'html',
  'htm',
  'eml',
]

export default function FileUpload() {
  const { t } = useTranslation()
  const { message: msg, modal } = App.useApp()
  const setPage = useFilesStore((s) => s.setPage)
  const folderSelection = useFoldersStore((s) => s.selected)
  const uploadAllowed = useFoldersStore((s) => s.uploadAllowed)
  const zeroAclMember = useFoldersStore((s) => s.zeroAclMember)
  const canUpload = uploadAllowed && !zeroAclMember
  const maxUploadMb = useSystemSettingsStore((s) => s.max_upload_size_mb)

  useEffect(() => {
    void useSystemSettingsStore.getState().load()
  }, [])

  const props: UploadProps = {
    name: 'file',
    accept: '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.jpg,.jpeg,.png,.gif,.bmp,.webp,.txt,.md,.markdown,.html,.htm,.eml',
    multiple: true,
    showUploadList: false,
    customRequest: async (options) => {
      const { file, onError, onSuccess, onProgress } = options
      const raw = file as File
      const ext = raw.name.split('.').pop()?.toLowerCase()
      if (ext && !allowed.includes(ext)) {
        msg.error(t('fileUpload.rejectedType', { ext }))
        onError?.(new Error('type'))
        return
      }
      const maxBytes = maxUploadMb * 1024 * 1024
      if (raw.size > maxBytes) {
        msg.error(t('fileUpload.rejectedSize', { mb: maxUploadMb }))
        onError?.(new Error('size'))
        return
      }
      const fd = new FormData()
      fd.append('file', raw)
      const wsId = getActiveWorkspaceId()
      if (wsId != null) {
        fd.append('workspace_id', String(wsId))
      }
      const targetFolderId = uploadTargetFolderId(folderSelection)
      if (targetFolderId != null) {
        fd.append('folder_id', String(targetFolderId))
      }
      try {
        const res = await uploadFile(fd, (e) => {
          const total = e.total ?? 0
          const pct = total ? Math.round((100 * (e.loaded ?? 0)) / total) : 0
          onProgress?.({ percent: pct })
        })
        const isDup = res.data.deduplicated === true
        if (isDup) {
          const dedupFolderId = uploadTargetFolderId(folderSelection)
          if (dedupFolderId != null) {
            modal.confirm({
              title: t('folders.dedupRelocateTitle'),
              content: t('folders.dedupRelocateContent', { name: res.data.original_name }),
              okText: t('common.confirm'),
              cancelText: t('common.cancel'),
              onOk: async () => {
                await updateFile(res.data.id, { folder_id: dedupFolderId })
                msg.success(t('messages.uploadDeduplicatedRelocated'))
                setPage(1)
                emitLibraryStatsRefresh()
                void useFoldersStore.getState().refreshFolderFileCounts()
              },
              onCancel: () => {
                msg.info(t('messages.uploadDeduplicated', { name: res.data.original_name }), 5)
              },
            })
          } else {
            msg.info(t('messages.uploadDeduplicated', { name: res.data.original_name }), 5)
          }
        } else {
          msg.success(t('messages.fileIngested'))
        }
        setPage(1)
        emitLibraryStatsRefresh()
        void useFoldersStore.getState().refreshFolderFileCounts()
        onSuccess?.({}, raw as unknown as Blob)
      } catch (err) {
        msg.error(formatApiError(err))
        onError?.(err as Error)
      }
    },
  }

  return (
    <div className="upload-zone">
      <Upload.Dragger {...props} className="upload-dropper" disabled={!canUpload}>
        <div className="drop-content">
          <span className="drop-icon-shell" aria-hidden>
            <span className="drop-icon-ring" />
            <svg width="22" height="22" viewBox="0 0 32 32" fill="none" className="drop-icon">
              <g className="drop-icon-arrow">
                <path
                  d="M16 6v14M10 14l6-8 6 8"
                  stroke="var(--accent)"
                  strokeWidth="1.75"
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </g>
              <line
                className="drop-icon-base"
                x1="7"
                y1="25"
                x2="25"
                y2="25"
                stroke="var(--accent)"
                strokeWidth="1.75"
                strokeLinecap="round"
              />
            </svg>
          </span>
          <div className="drop-body">
            <div className="drop-text">
              <span className="drop-main">{t('fileUpload.dropHere')}</span>
              <span className="drop-or">{t('fileUpload.orBrowse')}</span>
            </div>
            <p className="drop-meta">
              {canUpload
                ? `PDF · IMG · DOCX · MD · EML · PPTX · XLSX · ${t('fileUpload.maxSize', { mb: maxUploadMb })}`
                : t('fileUpload.noPermission')}
            </p>
          </div>
        </div>
      </Upload.Dragger>
    </div>
  )
}
