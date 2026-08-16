import { useMemo, useState } from 'react'
import { Alert, App, Button, Checkbox, Divider, Upload } from 'antd'
import { DownloadOutlined, InboxOutlined, UploadOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import { useTranslation } from 'react-i18next'
import { formatApiError } from '@/api/index'
import {
  exportOkfBundle,
  importOkfBundle,
  type OkfImportResponse,
  type OkfValidateResponse,
  validateOkfBundle,
} from '@/api/okf'
import { canManageFolders } from '@/lib/folderDragDrop'
import { folderPathLabel, uploadTargetFolderId } from '@/lib/folderTree'
import { useAuthStore } from '@/stores/authStore'
import { useFoldersStore } from '@/stores/foldersStore'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import './OkfImportExport.css'

type Props = {
  onImportComplete?: () => void
}

function canValidateOkf(isAdmin: boolean | undefined, myRole: string | undefined): boolean {
  if (isAdmin) return true
  const role = myRole ?? ''
  return role === 'contributor' || role === 'curator' || role === 'admin' || role === 'auditor'
}

function pickZipFile(fileList: UploadFile[]): File | null {
  const item = fileList.find((f) => f.originFileObj)
  return item?.originFileObj ?? null
}

export default function OkfImportExport({ onImportComplete }: Props) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const isAdmin = useAuthStore((s) => s.user?.is_admin)
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId)
  const workspaces = useWorkspaceStore((s) => s.workspaces)
  const folderSelection = useFoldersStore((s) => s.selected)
  const folders = useFoldersStore((s) => s.folders)

  const [validateFiles, setValidateFiles] = useState<UploadFile[]>([])
  const [importFiles, setImportFiles] = useState<UploadFile[]>([])
  const [dryRun, setDryRun] = useState(false)
  const [includeSources, setIncludeSources] = useState(false)
  const [validating, setValidating] = useState(false)
  const [importing, setImporting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [validateResult, setValidateResult] = useState<OkfValidateResponse | null>(null)
  const [importResult, setImportResult] = useState<OkfImportResponse | null>(null)

  const activeWs = workspaces.find((w) => w.id === activeWorkspaceId)
  const canValidate = canValidateOkf(isAdmin, activeWs?.my_role)
  const canImportExport = canManageFolders(isAdmin, activeWs?.my_role)
  const folderId = uploadTargetFolderId(folderSelection)
  const folderLabel = useMemo(() => {
    if (folderSelection === 'all') {
      return t('okf.scopeAllFolders')
    }
    if (folderSelection === 'uncategorized') {
      return t('okf.scopeUncategorized')
    }
    return folderPathLabel(folders, folderSelection) || t('okf.scopeFolder', { id: folderSelection })
  }, [folderSelection, folders, t])

  const workspaceLabel = activeWs?.name ?? t('okf.noWorkspace')

  const handleValidate = async () => {
    const file = pickZipFile(validateFiles)
    if (!file) {
      message.warning(t('okf.pickZip'))
      return
    }
    if (activeWorkspaceId == null) {
      message.error(t('okf.noWorkspace'))
      return
    }
    setValidating(true)
    setValidateResult(null)
    try {
      const result = await validateOkfBundle(file, activeWorkspaceId)
      setValidateResult(result)
      if (result.conformant) {
        message.success(t('okf.validateSuccess', { count: result.concept_count }))
      } else {
        message.warning(t('okf.validateFailed'))
      }
    } catch (e: unknown) {
      const detail = formatApiError(e)
      message.error(detail ? `${t('okf.validateError')}: ${detail}` : t('okf.validateError'))
    } finally {
      setValidating(false)
    }
  }

  const handleImport = async () => {
    const file = pickZipFile(importFiles)
    if (!file) {
      message.warning(t('okf.pickZip'))
      return
    }
    if (activeWorkspaceId == null) {
      message.error(t('okf.noWorkspace'))
      return
    }
    setImporting(true)
    setImportResult(null)
    try {
      const result = await importOkfBundle(file, {
        workspaceId: activeWorkspaceId,
        folderId,
        dryRun,
      })
      setImportResult(result)
      if (result.dry_run) {
        message.info(t('okf.importDryRunDone', { count: result.concepts_created }))
      } else {
        message.success(
          t('okf.importSuccess', {
            created: result.concepts_created,
            updated: result.concepts_updated,
          }),
        )
        onImportComplete?.()
      }
    } catch (e: unknown) {
      const detail = formatApiError(e)
      message.error(detail ? `${t('okf.importError')}: ${detail}` : t('okf.importError'))
    } finally {
      setImporting(false)
    }
  }

  const handleExport = async () => {
    if (activeWorkspaceId == null) {
      message.error(t('okf.noWorkspace'))
      return
    }
    setExporting(true)
    try {
      await exportOkfBundle({
        workspaceId: activeWorkspaceId,
        folderId,
        includeSources,
      })
      message.success(t('okf.exportSuccess'))
    } catch (e: unknown) {
      const detail = formatApiError(e)
      message.error(detail ? `${t('okf.exportError')}: ${detail}` : t('okf.exportError'))
    } finally {
      setExporting(false)
    }
  }

  if (activeWorkspaceId == null) {
    return (
      <div className="okf-ie-panel">
        <Alert type="warning" showIcon message={t('okf.noWorkspace')} />
      </div>
    )
  }

  return (
    <div className="okf-ie-panel">
      <p className="okf-ie-intro">{t('okf.intro')}</p>
      <p className="okf-ie-meta">
        {t('okf.activeWorkspace')}: <strong>{workspaceLabel}</strong>
        {' · '}
        {t('okf.importTarget')}: <strong>{folderLabel}</strong>
      </p>

      <section className="okf-ie-section" aria-labelledby="okf-validate-title">
        <h3 id="okf-validate-title" className="okf-ie-section-title">
          {t('okf.validateTitle')}
        </h3>
        <p className="okf-ie-section-desc">{t('okf.validateDesc')}</p>
        {!canValidate ? (
          <Alert type="info" showIcon message={t('okf.validateForbidden')} />
        ) : (
          <>
            <Upload.Dragger
              className="okf-ie-upload"
              accept=".zip,application/zip"
              maxCount={1}
              fileList={validateFiles}
              beforeUpload={() => false}
              onChange={({ fileList }) => {
                setValidateFiles(fileList.slice(-1))
                setValidateResult(null)
              }}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined aria-hidden />
              </p>
              <p className="ant-upload-text">{t('okf.dropZip')}</p>
            </Upload.Dragger>
            <div className="okf-ie-actions">
              <Button type="primary" loading={validating} onClick={() => void handleValidate()}>
                {t('okf.validateAction')}
              </Button>
            </div>
            {validateResult ? (
              <Alert
                type={validateResult.conformant ? 'success' : 'error'}
                showIcon
                message={
                  validateResult.conformant
                    ? t('okf.validateConformant', { count: validateResult.concept_count })
                    : t('okf.validateNotConformant')
                }
                description={
                  <>
                    {validateResult.errors.length > 0 ? (
                      <ul className="okf-ie-result">
                        {validateResult.errors.map((err) => (
                          <li key={err}>{err}</li>
                        ))}
                      </ul>
                    ) : null}
                    {validateResult.warnings.length > 0 ? (
                      <ul className="okf-ie-warnings">
                        {validateResult.warnings.map((w) => (
                          <li key={w}>{w}</li>
                        ))}
                      </ul>
                    ) : null}
                  </>
                }
              />
            ) : null}
          </>
        )}
      </section>

      <Divider />

      <section className="okf-ie-section" aria-labelledby="okf-import-title">
        <h3 id="okf-import-title" className="okf-ie-section-title">
          {t('okf.importTitle')}
        </h3>
        <p className="okf-ie-section-desc">{t('okf.importDesc')}</p>
        {!canImportExport ? (
          <Alert type="info" showIcon message={t('okf.importExportForbidden')} />
        ) : (
          <>
            <Upload.Dragger
              className="okf-ie-upload"
              accept=".zip,application/zip"
              maxCount={1}
              fileList={importFiles}
              beforeUpload={() => false}
              onChange={({ fileList }) => {
                setImportFiles(fileList.slice(-1))
                setImportResult(null)
              }}
            >
              <p className="ant-upload-drag-icon">
                <UploadOutlined aria-hidden />
              </p>
              <p className="ant-upload-text">{t('okf.dropZip')}</p>
            </Upload.Dragger>
            <Checkbox checked={dryRun} onChange={(e) => setDryRun(e.target.checked)}>
              {t('okf.dryRun')}
            </Checkbox>
            <div className="okf-ie-actions">
              <Button type="primary" loading={importing} onClick={() => void handleImport()}>
                {dryRun ? t('okf.importDryRunAction') : t('okf.importAction')}
              </Button>
            </div>
            {importResult ? (
              <ul className="okf-ie-result">
                <li>{t('okf.importReportCreated', { count: importResult.concepts_created })}</li>
                <li>{t('okf.importReportUpdated', { count: importResult.concepts_updated })}</li>
                <li>{t('okf.importReportLog', { count: importResult.log_entries_imported })}</li>
                {importResult.warnings.length > 0 ? (
                  <li>
                    {t('okf.importReportWarnings', { count: importResult.warnings.length })}
                    <ul className="okf-ie-warnings">
                      {importResult.warnings.map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  </li>
                ) : null}
              </ul>
            ) : null}
          </>
        )}
      </section>

      <Divider />

      <section className="okf-ie-section" aria-labelledby="okf-export-title">
        <h3 id="okf-export-title" className="okf-ie-section-title">
          {t('okf.exportTitle')}
        </h3>
        <p className="okf-ie-section-desc">{t('okf.exportDesc')}</p>
        {!canImportExport ? (
          <Alert type="info" showIcon message={t('okf.importExportForbidden')} />
        ) : (
          <>
            <Checkbox checked={includeSources} onChange={(e) => setIncludeSources(e.target.checked)}>
              {t('okf.includeSources')}
            </Checkbox>
            <div className="okf-ie-actions">
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                loading={exporting}
                onClick={() => void handleExport()}
              >
                {t('okf.exportAction')}
              </Button>
            </div>
          </>
        )}
      </section>
    </div>
  )
}
