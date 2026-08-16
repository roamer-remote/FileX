import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { Alert, Empty, Modal, Spin, Tag } from 'antd'
import { ExportOutlined, FileOutlined, ImportOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import {
  getFileWikiLinks,
  type WikiLinkBackItem,
  type WikiLinkOutItem,
  type WikiLinksResponse,
} from '@/api/files'
import {
  backlinkOpenable,
  backlinkRowLabel,
  brokenOutlinkRowLabel,
  outlinkListOpenable,
  outlinkOpenable,
  outlinkRowLabel,
  outlinkSlugOpenable,
} from '@/utils/wikiLinkDisplay'
import './WikiLinksListModal.css'

export type WikiLinkListKind = 'outlinks' | 'backlinks'

export type WikiLinkOpenMeta = {
  anchorId?: string
}

export type WikiLinksListModalProps = {
  open: boolean
  onClose: () => void
  fileId: number
  fileName: string
  linkKind: WikiLinkListKind
  onOpenFile: (fileId: number, meta?: WikiLinkOpenMeta) => void
  /** 预览宿主：处理含 [[wiki:slug]] 的出链（083 slug fallback） */
  onOpenOutlink?: (ol: WikiLinkOutItem) => void
  /** 预览宿主已加载的 wiki links；提供则跳过 getFileWikiLinks */
  initialData?: WikiLinksResponse | null
  /** 叠在宿主 Modal 之上（如 MdNoteViewModal zIndex + 100） */
  zIndex?: number
  /** 仅展示 [[file:id]] 且对端为普通资料（page_kind=source）的直连 */
  sourceFileDirectOnly?: boolean
}

function rowKeyHandler(onActivate: () => void) {
  return (event: KeyboardEvent<HTMLDivElement | HTMLButtonElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onActivate()
    }
  }
}

export default function WikiLinksListModal({
  open,
  onClose,
  fileId,
  fileName,
  linkKind,
  onOpenFile,
  onOpenOutlink,
  initialData = null,
  zIndex,
  sourceFileDirectOnly = false,
}: WikiLinksListModalProps) {
  const { t } = useTranslation()
  const cacheRef = useRef(new Map<string, WikiLinksResponse>())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [data, setData] = useState<WikiLinksResponse | null>(null)

  useEffect(() => {
    if (!open || fileId <= 0) return

    if (initialData != null) {
      setData(initialData)
      setError(false)
      setLoading(false)
      return
    }

    const cacheKey = `${fileId}:${sourceFileDirectOnly ? "source-direct" : "all"}`
    const cached = cacheRef.current.get(cacheKey)
    if (cached) {
      setData(cached)
      setError(false)
      setLoading(false)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(false)
    setData(null)

    void getFileWikiLinks(fileId, {
      dedupe: false,
      sourceFileDirectOnly,
    })
      .then((res) => {
        if (cancelled) return
        cacheRef.current.set(cacheKey, res.data)
        setData(res.data)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [open, fileId, sourceFileDirectOnly, initialData])

  const outlinks = data?.outlinks ?? []
  const backlinks = data?.backlinks ?? []
  const items = linkKind === 'outlinks' ? outlinks : backlinks
  const recordCount = items.length
  const isEmpty = recordCount === 0

  const handleOpenOutlink = (ol: WikiLinkOutItem) => {
    if (outlinkOpenable(ol)) {
      onClose()
      onOpenFile(ol.target_file_id, { anchorId: ol.anchor_id || undefined })
      return
    }
    if (outlinkSlugOpenable(ol) && onOpenOutlink) {
      onClose()
      onOpenOutlink(ol)
    }
  }

  const handleOpenBacklink = (bl: WikiLinkBackItem) => {
    if (!backlinkOpenable(bl)) return
    onClose()
    onOpenFile(bl.source_file_id, { anchorId: bl.anchor_id })
  }

  const renderOutlinkRow = (ol: WikiLinkOutItem) => {
    if (outlinkListOpenable(ol, { resolveSlug: Boolean(onOpenOutlink) })) {
      return (
        <div
          key={ol.anchor_id}
          role="button"
          tabIndex={0}
          className="kb-wiki-link-modal__row kb-wiki-link-modal__row--clickable"
          onClick={() => handleOpenOutlink(ol)}
          onKeyDown={rowKeyHandler(() => handleOpenOutlink(ol))}
        >
          <FileOutlined className="kb-wiki-link-modal__row-icon" aria-hidden />
          <span className="kb-wiki-link-modal__row-label">{outlinkRowLabel(ol)}</span>
        </div>
      )
    }

    const brokenLabel = brokenOutlinkRowLabel(ol)
    return (
      <div key={ol.anchor_id} className="kb-wiki-link-modal__row kb-wiki-link-modal__row--broken">
        <FileOutlined className="kb-wiki-link-modal__row-icon kb-wiki-link-modal__row-icon--muted" aria-hidden />
        <span className="kb-wiki-link-modal__row-label">{brokenLabel ?? '—'}</span>
        <Tag className="kb-wiki-link-modal__row-badge">{t('filePreview.wikiLinkBrokenBadge')}</Tag>
      </div>
    )
  }

  const renderBacklinkRow = (bl: WikiLinkBackItem) => (
    <div
      key={bl.anchor_id}
      role="button"
      tabIndex={0}
      className="kb-wiki-link-modal__row kb-wiki-link-modal__row--clickable"
      onClick={() => handleOpenBacklink(bl)}
      onKeyDown={rowKeyHandler(() => handleOpenBacklink(bl))}
    >
      <FileOutlined className="kb-wiki-link-modal__row-icon" aria-hidden />
      <span className="kb-wiki-link-modal__row-label">{backlinkRowLabel(bl)}</span>
    </div>
  )

  let body: ReactNode
  if (loading) {
    body = (
      <div className="kb-wiki-link-modal-center">
        <Spin tip={t('knowledgeIndex.wikiLinkModal.loading')} />
      </div>
    )
  } else if (error) {
    body = <Alert type="error" showIcon message={t('knowledgeIndex.wikiLinkModal.loadFailed')} />
  } else if (isEmpty) {
    body = <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('knowledgeIndex.wikiLinkModal.empty')} />
  } else {
    body = (
      <div className="kb-wiki-link-modal__layout">
        <p className="kb-wiki-link-modal__meta">
          {t('knowledgeIndex.wikiLinkModal.previewHint')}
          {' · '}
          <strong>{t('knowledgeIndex.wikiLinkModal.recordCount', { count: recordCount })}</strong>
        </p>
        <div className="kb-wiki-link-modal__scroll">
          <div className="kb-wiki-link-modal__list" role="list">
            {linkKind === 'outlinks'
              ? outlinks.map(renderOutlinkRow)
              : backlinks.map(renderBacklinkRow)}
          </div>
        </div>
      </div>
    )
  }

  const kindLabel =
    linkKind === 'outlinks'
      ? t('knowledgeIndex.wikiColumns.outlinks')
      : t('knowledgeIndex.wikiColumns.backlinks')
  const KindIcon = linkKind === 'outlinks' ? ExportOutlined : ImportOutlined

  return (
    <Modal
      open={open}
      title={
        <div className="kb-wiki-link-modal__title">
          <span className="kb-wiki-link-modal__title-icon" aria-hidden>
            <KindIcon />
          </span>
          <div className="kb-wiki-link-modal__title-text">
            <span className="kb-wiki-link-modal__title-kind">{kindLabel}</span>
            <span className="kb-wiki-link-modal__title-name" title={fileName}>
              {fileName}
            </span>
          </div>
        </div>
      }
      onCancel={onClose}
      footer={null}
      width={600}
      zIndex={zIndex}
      destroyOnClose
      maskClosable={false}
      rootClassName="kb-wiki-link-modal"
    >
      {body}
    </Modal>
  )
}
