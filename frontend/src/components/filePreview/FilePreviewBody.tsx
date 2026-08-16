import type { RefObject, ReactNode } from 'react'
import { Button, Spin, Tabs } from 'antd'
import { PhotoProvider, PhotoView } from 'react-photo-view'
import type { FileItem } from '@/api/files'
import { isWikiThemePage } from '@/utils/mdNotePreview'
import type { ExcelPreviewTab } from './filePreviewMime'
import {
  isDocxLike,
  isExcelLike,
  isEmlLike,
  isHtmlLike,
  isLegacyBinaryOffice,
  isLegacyDocForPreview,
  isLegacyPptForPreview,
  isPdfLike,
  isPptxLike,
  isExtractBusy,
} from './filePreviewMime'

export type FilePreviewBodyProps = {
  file: FileItem
  previewUrl: string
  scrollToAnchorId?: string | null
  pdfBlobUrl: string | null
  pdfLoadError: boolean
  htmlBlobUrl: string | null
  htmlLoadError: boolean
  officeLoading: boolean
  officeError: boolean
  excelTabs: ExcelPreviewTab[]
  docxBodyRef: RefObject<HTMLDivElement | null>
  pptxWrapperRef: RefObject<HTMLDivElement | null>
  mdFileSource: string
  mdHtml: string
  mdFileLoading: boolean
  mdContainerRef: RefObject<HTMLDivElement | null>
  txtContent: string
  onDownload: () => void
  t: (key: string, opts?: Record<string, unknown>) => string
}

export function FilePreviewBody({
  file: activeFile,
  previewUrl,
  scrollToAnchorId,
  pdfBlobUrl,
  pdfLoadError,
  htmlBlobUrl,
  htmlLoadError,
  officeLoading,
  officeError,
  excelTabs,
  docxBodyRef,
  pptxWrapperRef,
  mdFileSource,
  mdHtml,
  mdFileLoading,
  mdContainerRef,
  txtContent,
  onDownload,
  t,
}: FilePreviewBodyProps): ReactNode {
  const isPdf = isPdfLike(activeFile)
  const isHtml = isHtmlLike(activeFile)
  const legacyOfficeExtracting =
    isLegacyBinaryOffice(activeFile) && isExtractBusy(activeFile.extract_status)
  const isDocx = isDocxLike(activeFile) || isLegacyDocForPreview(activeFile)
  const isPptx = isPptxLike(activeFile) || isLegacyPptForPreview(activeFile)
  const isExcel = isExcelLike(activeFile)
  const isEml = isEmlLike(activeFile)

  if (activeFile.mime_type.startsWith('image/')) {
    return (
      <PhotoProvider maskClosable pullClosable bannerVisible loop={false}>
        <div className="pv-photo-root">
          <PhotoView src={previewUrl}>
            <img
              src={previewUrl}
              alt={activeFile.original_name}
              className="pv-photo-thumb"
              decoding="async"
              loading="eager"
            />
          </PhotoView>
        </div>
      </PhotoProvider>
    )
  }

  if (isPdf) {
    if (pdfLoadError) {
      return (
        <div className="pv-fallback">
          <p className="pv-fb-msg">{t('filePreview.pdfLoadFailed')}</p>
          <Button type="primary" onClick={onDownload}>
            {t('filePreview.download')}
          </Button>
        </div>
      )
    }
    if (!pdfBlobUrl) {
      return (
        <div className="pv-pdf-loading">
          <Spin size="large" />
        </div>
      )
    }
    return <iframe title={activeFile.original_name} src={pdfBlobUrl} className="pv-pdf" />
  }

  if (isDocx || isPptx) {
    if (officeError) {
      return (
        <div className="pv-fallback">
          <p className="pv-fb-msg">{t('filePreview.officeLoadFailed')}</p>
          <Button type="primary" onClick={onDownload}>
            {t('filePreview.download')}
          </Button>
        </div>
      )
    }
    return (
      <div className="pv-office-wrap">
        {officeLoading ? (
          <div className="pv-office-spin-overlay">
            <Spin size="large" />
          </div>
        ) : null}
        {isDocx ? (
          <div className="pv-docx-wrap">
            <div ref={docxBodyRef} className="pv-docx-body" />
          </div>
        ) : (
          <div ref={pptxWrapperRef} className="pv-pptx-host" />
        )}
      </div>
    )
  }

  if (isExcel) {
    if (officeError) {
      return (
        <div className="pv-fallback">
          <p className="pv-fb-msg">{t('filePreview.officeLoadFailed')}</p>
          <Button type="primary" onClick={onDownload}>
            {t('filePreview.download')}
          </Button>
        </div>
      )
    }
    return (
      <div className="pv-office-wrap">
        {officeLoading ? (
          <div className="pv-office-spin-overlay">
            <Spin size="large" />
          </div>
        ) : null}
        {!officeLoading && excelTabs.length > 0 ? (
          <Tabs
            className="pv-xlsx-tabs"
            destroyInactiveTabPane={false}
            items={excelTabs.map((tab) => ({
              key: tab.key,
              label: tab.label,
              children: (
                <div className="pv-xlsx-sheet" dangerouslySetInnerHTML={{ __html: tab.html }} />
              ),
            }))}
          />
        ) : null}
      </div>
    )
  }

  if (legacyOfficeExtracting) {
    return (
      <div className="pv-fallback">
        <Spin size="large" />
        <p className="pv-fb-msg">{t('filePreview.officeNormalizing')}</p>
      </div>
    )
  }

  if (isHtml) {
    if (htmlLoadError) {
      return (
        <div className="pv-fallback">
          <p className="pv-fb-msg">{t('filePreview.htmlLoadFailed')}</p>
          <Button type="primary" onClick={onDownload}>
            {t('filePreview.download')}
          </Button>
        </div>
      )
    }
    if (!htmlBlobUrl) {
      return (
        <div className="pv-pdf-loading">
          <Spin size="large" />
        </div>
      )
    }
    return (
      <iframe title={activeFile.original_name} src={htmlBlobUrl} className="pv-html" sandbox="" />
    )
  }

  if (activeFile.mime_type === 'text/markdown' || isEml) {
    if (isWikiThemePage(activeFile) && activeFile.has_md) {
      if (mdFileLoading) {
        return (
          <div className="pv-md-theme-preview pv-md-theme-preview--loading">
            <Spin size="large" />
          </div>
        )
      }
      if (!mdFileSource.trim() && !mdHtml.trim()) {
        return (
          <div className="pv-md-theme-preview">
            <div className="mdsv-empty">{t('filePreview.mdEmpty')}</div>
          </div>
        )
      }
      return (
        <div className="pv-md-theme-preview">
          <div
            ref={mdContainerRef}
            className="pv-md markdown-body fb-markdown-host"
            dangerouslySetInnerHTML={{ __html: mdHtml }}
          />
        </div>
      )
    }
    if (activeFile.has_md && scrollToAnchorId && !isWikiThemePage(activeFile)) {
      return (
        <div className="pv-md-sidecar-hint">
          <p>{t('filePreview.sidecarHintWhenTagJump')}</p>
        </div>
      )
    }
    if (mdFileLoading) {
      return (
        <div className="pv-md-source-readonly pv-md-source-readonly--loading">
          <Spin size="large" />
        </div>
      )
    }
    if (!mdFileSource.trim() && !mdHtml.trim()) {
      return (
        <div className="pv-md-source-readonly">
          <div className="mdsv-empty">{t('filePreview.mdEmpty')}</div>
        </div>
      )
    }
    return (
      <div className="pv-md-source-readonly">
        <div
          ref={mdContainerRef}
          className="pv-md markdown-body fb-markdown-host"
          dangerouslySetInnerHTML={{ __html: mdHtml }}
        />
      </div>
    )
  }

  if (activeFile.mime_type === 'text/plain') {
    return (
      <div className="pv-txt">
        <pre>{txtContent}</pre>
      </div>
    )
  }

  return (
    <div className="pv-fallback">
      <p className="pv-fb-msg">{t('filePreview.unavailable')}</p>
      <p className="pv-fb-sub">{activeFile.mime_type}</p>
      <Button type="primary" onClick={onDownload}>
        {t('filePreview.download')}
      </Button>
    </div>
  )
}
