import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Button, Empty, Pagination, Table, Tooltip, type TableColumnsType } from 'antd'
import { ClusterOutlined, FileTextOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import type { KbIndexRow } from '@/utils/parseKbIndexTable'
import { MarqueeTooltip } from '@/components/FileListComponents'
import { setupKbIndexTagsMarquee } from '@/utils/kbIndexPreviewHtml'
import { useFlexTableBodyScrollY } from '@/hooks/useFlexTableBodyScrollY'
import { useKbChunkReindex } from '@/hooks/useKbChunkReindex'

type CreatedSortOrder = 'ascend' | 'descend'

type Props = {
  rows: KbIndexRow[]
  onOpenFile: (fileId: number) => void
  onOpenMdPreview?: (fileId: number, fileName: string) => void
  emptyDescription?: string
  active?: boolean
}

export function KbIndexTagsCell({ tags }: { tags: string[] }) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const stripRef = useRef<HTMLDivElement>(null)
  const [marquee, setMarquee] = useState(false)

  useLayoutEffect(() => {
    const vp = viewportRef.current
    const strip = stripRef.current
    if (!vp || !strip || tags.length === 0) return
    const measure = () => {
      const oneLine = parseFloat(getComputedStyle(strip).lineHeight) || 20
      const overflowX = strip.scrollWidth > vp.clientWidth + 1
      const overflowY = strip.scrollHeight > oneLine + 2
      const overflow = overflowX || overflowY
      setMarquee(overflow)
      if (overflow) {
        const w = strip.scrollWidth
        vp.style.setProperty('--kb-tags-marquee-sec', `${Math.min(48, Math.max(8, w / 26))}s`)
      } else {
        vp.style.removeProperty('--kb-tags-marquee-sec')
      }
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(vp)
    ro.observe(strip)
    return () => ro.disconnect()
  }, [tags])

  if (tags.length === 0) return <>—</>

  const title = tags.join('、')
  return (
    <MarqueeTooltip active={marquee} title={title}>
      <div ref={viewportRef} className="kb-index-tags" data-marquee-managed="react">
        <div className={marquee ? 'kb-index-tags-track kb-index-tags-track--marquee' : 'kb-index-tags-track'}>
          <div ref={stripRef} className="kb-index-tags-strip">
            {tags.map((tg) => (
              <span key={tg} className="kb-index-tags-chip">
                {tg}
              </span>
            ))}
          </div>
          {marquee ? (
            <div className="kb-index-tags-strip" aria-hidden>
              {tags.map((tg) => (
                <span key={`dup-${tg}`} className="kb-index-tags-chip">
                  {tg}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </MarqueeTooltip>
  )
}

function KbIndexMdIcon({
  hasMd,
  fileId,
  fileName,
  onPreview,
}: {
  hasMd: boolean
  fileId: number
  fileName: string
  onPreview?: (fileId: number, fileName: string) => void
}) {
  const { t } = useTranslation()
  if (!hasMd) {
    return (
      <span
        className="kb-index-md-icon kb-index-md-icon--no"
        role="img"
        aria-label={t('knowledgeIndex.mdNoNote')}
      >
        <FileTextOutlined className="kb-index-md-icon__svg" />
      </span>
    )
  }
  return (
    <button
      type="button"
      className="kb-index-md-icon kb-index-md-icon--yes kb-index-md-icon--btn"
      aria-label={t('knowledgeIndex.mdPreviewOpen')}
      title={t('knowledgeIndex.mdPreviewOpen')}
      onClick={(e) => {
        e.stopPropagation()
        onPreview?.(fileId, fileName)
      }}
    >
      <FileTextOutlined className="kb-index-md-icon__svg" />
    </button>
  )
}

function ReindexAction({ hasMd, fileId }: { hasMd: boolean; fileId: number }) {
  const { t } = useTranslation()
  const { confirmForceReindex, forceReindexLoading } = useKbChunkReindex(fileId)

  const label = t('knowledgeIndex.reindexRowAction')

  if (!hasMd) {
    return (
      <Tooltip title={t('knowledgeIndex.reindexRowDisabledTip')}>
        <span>
          <Button
            type="default"
            size="small"
            icon={<ClusterOutlined aria-hidden />}
            disabled
          >
            {label}
          </Button>
        </span>
      </Tooltip>
    )
  }

  return (
    <Button
      type="default"
      size="small"
      icon={<ClusterOutlined aria-hidden />}
      loading={forceReindexLoading}
      onClick={(e) => {
        e.stopPropagation()
        confirmForceReindex()
      }}
    >
      {label}
    </Button>
  )
}

export default function KbIndexPreviewTable({
  rows,
  onOpenFile,
  onOpenMdPreview,
  emptyDescription,
  active = true,
}: Props) {
  const { t } = useTranslation()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [createdSort, setCreatedSort] = useState<CreatedSortOrder>('descend')
  const bodyRef = useRef<HTMLDivElement>(null)
  const tableHostRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setPage(1)
  }, [rows])

  const sortedRows = useMemo(() => {
    const copy = [...rows]
    copy.sort((a, b) => {
      const cmp = a.createdAtMs - b.createdAtMs
      return createdSort === 'ascend' ? cmp : -cmp
    })
    return copy
  }, [rows, createdSort])

  const pagedRows = useMemo(() => {
    const start = (page - 1) * pageSize
    return sortedRows.slice(start, start + pageSize)
  }, [sortedRows, page, pageSize])

  const scrollY = useFlexTableBodyScrollY([rows.length, page, pageSize, createdSort], {
    bodyRef,
    enabled: active && rows.length > 0,
  })

  const tableScroll =
    rows.length > 0 && scrollY > 0 ? { x: 'max-content' as const, y: scrollY } : { x: 'max-content' as const }

  useLayoutEffect(() => {
    const el = tableHostRef.current
    if (!el) return
    return setupKbIndexTagsMarquee(el)
  }, [sortedRows, page, pageSize])

  const columns: TableColumnsType<KbIndexRow> = [
    {
      title: t('knowledgeIndex.columns.file_id'),
      dataIndex: 'fileId',
      key: 'file_id',
      width: 72,
    },
    {
      title: t('knowledgeIndex.columns.original_name'),
      dataIndex: 'originalName',
      key: 'original_name',
      className: 'kb-index-col-filename',
      ellipsis: true,
      render: (name: string, row) => (
        <Button
          type="link"
          className="kb-index-filename-link"
          title={name}
          onClick={() => onOpenFile(row.fileId)}
        >
          {name}
        </Button>
      ),
    },
    {
      title: t('knowledgeIndex.columns.mime_type'),
      dataIndex: 'mimeType',
      key: 'mime_type',
      width: 72,
    },
    {
      title: t('knowledgeIndex.columns.has_md'),
      dataIndex: 'hasMd',
      key: 'has_md',
      className: 'kb-index-col-md',
      width: 56,
      align: 'center',
      render: (hasMd: boolean, row) => (
        <KbIndexMdIcon
          hasMd={hasMd}
          fileId={row.fileId}
          fileName={row.originalName}
          onPreview={onOpenMdPreview}
        />
      ),
    },
    {
      title: t('knowledgeIndex.columns.tags'),
      dataIndex: 'tags',
      key: 'tags',
      className: 'kb-index-col-tags',
      render: (tags: string[]) => <KbIndexTagsCell tags={tags} />,
    },
    {
      title: t('knowledgeIndex.columns.created_at'),
      dataIndex: 'createdAt',
      key: 'created_at',
      width: 168,
      sorter: true,
      sortOrder: createdSort,
      showSorterTooltip: false,
      render: (value: string) => value || '—',
    },
    {
      title: '',
      key: 'reindex',
      width: 190,
      render: (_: unknown, row: KbIndexRow) => (
        <>
          <ReindexAction hasMd={row.hasMd} fileId={row.fileId} />
          <Button
            type="link"
            size="small"
            href={`/admin/knowledge-base/quality-workbench?file_id=${row.fileId}`}
            onClick={(event) => event.stopPropagation()}
          >
            {t('knowledgeIndex.qualityWorkbench')}
          </Button>
        </>
      ),
    },
  ]

  if (rows.length === 0) {
    return (
      <div className="kb-index-table-shell fl-table-shell">
        <div className="fl-body fl-body--empty">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={emptyDescription ?? t('knowledgeIndex.noFilesYet')}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="kb-index-table-shell fl-table-shell">
      <div className="fl-body" ref={bodyRef}>
        <div ref={tableHostRef} className="kb-index-preview-table-host fl-table-host">
          <Table<KbIndexRow>
            className="kb-index-preview-table"
            rowKey="fileId"
            size="small"
            columns={columns}
            dataSource={pagedRows}
            tableLayout="fixed"
            pagination={false}
            scroll={tableScroll}
            onChange={(_pagination, _filters, sorter, extra) => {
              if (extra?.action !== 'sort') return
              if (Array.isArray(sorter)) return
              if (sorter.columnKey !== 'created_at') return
              const order = sorter.order === 'ascend' ? 'ascend' : 'descend'
              setCreatedSort(order)
              setPage(1)
            }}
          />
        </div>
      </div>
      <div className="fl-pager">
        <Pagination
          current={page}
          pageSize={pageSize}
          total={sortedRows.length}
          showSizeChanger
          pageSizeOptions={['10', '20', '50', '100']}
          onChange={(nextPage, nextSize) => {
            setPage(nextPage)
            setPageSize(nextSize)
          }}
        />
      </div>
    </div>
  )
}
