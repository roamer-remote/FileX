import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Button, Empty, Pagination, Spin, Table, Tag, Tooltip, type TableColumnsType } from 'antd'
import { useTranslation } from 'react-i18next'
import { getFileWikiLinks } from '@/api/files'
import type { KbWikiIndexRow } from '@/utils/parseKbIndexTable'
import { setupKbIndexTagsMarquee } from '@/utils/kbIndexPreviewHtml'
import { KbIndexTagsCell } from '@/components/KbIndexPreviewTable'
import { uniqueOutlinkWikiSlugs } from '@/utils/wikiLinkDisplay'
import WikiLinksListModal, { type WikiLinkListKind } from '@/components/WikiLinksListModal'
import { useFlexTableBodyScrollY } from '@/hooks/useFlexTableBodyScrollY'

type SlugLoadState = 'loading' | 'error' | string[]

type LinkModalState = {
  fileId: number
  fileName: string
  kind: WikiLinkListKind
} | null

type Props = {
  rows: KbWikiIndexRow[]
  onOpenFile: (fileId: number) => void
  active?: boolean
}

export default function KbWikiIndexPreviewTable({ rows, onOpenFile, active = true }: Props) {
  const { t } = useTranslation()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [linkModal, setLinkModal] = useState<LinkModalState>(null)
  const [outlinkSlugs, setOutlinkSlugs] = useState<Record<number, SlugLoadState>>({})
  const bodyRef = useRef<HTMLDivElement>(null)
  const tableHostRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setPage(1)
  }, [rows])

  useEffect(() => {
    const ids = rows.filter((r) => r.outlinks > 0).map((r) => r.fileId)
    if (ids.length === 0) {
      setOutlinkSlugs({})
      return
    }

    setOutlinkSlugs(Object.fromEntries(ids.map((id) => [id, 'loading'])))
    let cancelled = false

    void Promise.all(
      ids.map(async (id) => {
        try {
          const res = await getFileWikiLinks(id)
          return { id, slugs: uniqueOutlinkWikiSlugs(res.data.outlinks) }
        } catch {
          return { id, slugs: null as null }
        }
      }),
    ).then((results) => {
      if (cancelled) return
      const next: Record<number, SlugLoadState> = {}
      for (const { id, slugs } of results) {
        next[id] = slugs ?? 'error'
      }
      setOutlinkSlugs(next)
    })

    return () => {
      cancelled = true
    }
  }, [rows])

  const sortedRows = useMemo(() => {
    return [...rows].sort((a, b) => a.fileId - b.fileId || a.originalName.localeCompare(b.originalName))
  }, [rows])

  const pagedRows = useMemo(() => {
    const start = (page - 1) * pageSize
    return sortedRows.slice(start, start + pageSize)
  }, [sortedRows, page, pageSize])

  const scrollY = useFlexTableBodyScrollY([rows.length, page, pageSize], {
    bodyRef,
    enabled: active && rows.length > 0,
  })

  const tableScroll =
    rows.length > 0 && scrollY > 0 ? { x: 872, y: scrollY } : { x: 872 }

  useLayoutEffect(() => {
    const el = tableHostRef.current
    if (!el) return
    return setupKbIndexTagsMarquee(el)
  }, [sortedRows, page, pageSize, outlinkSlugs])

  const openLinkModal = useCallback((row: KbWikiIndexRow, kind: WikiLinkListKind) => {
    setLinkModal({ fileId: row.fileId, fileName: row.originalName, kind })
  }, [])

  const renderLinkCount = useCallback(
    (count: number, row: KbWikiIndexRow, kind: WikiLinkListKind) => {
      if (count <= 0) return <span>{count}</span>
      return (
        <Button type="link" className="kb-wiki-link-count" onClick={() => openLinkModal(row, kind)}>
          {count}
        </Button>
      )
    },
    [openLinkModal],
  )

  const renderOutlinkWikiSlugs = useCallback(
    (row: KbWikiIndexRow) => {
      if (row.outlinks <= 0) return <span className="kb-wiki-outlink-slugs-empty">—</span>
      const state = outlinkSlugs[row.fileId]
      if (state === 'loading' || state === undefined) {
        return <Spin size="small" aria-label={t('knowledgeIndex.wikiLinkModal.loading')} />
      }
      if (state === 'error') return <span className="kb-wiki-outlink-slugs-empty">—</span>
      if (state.length === 0) return <span className="kb-wiki-outlink-slugs-empty">—</span>
      return (
        <div className="kb-wiki-outlink-slugs">
          {state.map((slug) => (
            <Tooltip key={slug} title={slug}>
              <Tag className="kb-wiki-outlink-slug-tag">{slug}</Tag>
            </Tooltip>
          ))}
        </div>
      )
    },
    [outlinkSlugs, t],
  )

  const columns: TableColumnsType<KbWikiIndexRow> = [
    {
      title: t('knowledgeIndex.wikiColumns.file_id'),
      dataIndex: 'fileId',
      key: 'file_id',
      width: 72,
    },
    {
      title: t('knowledgeIndex.wikiColumns.original_name'),
      dataIndex: 'originalName',
      key: 'original_name',
      className: 'kb-index-col-filename',
      width: 220,
      ellipsis: true,
      render: (name: string, row) => (
        <Button type="link" className="kb-index-filename-link" title={name} onClick={() => onOpenFile(row.fileId)}>
          {name}
        </Button>
      ),
    },
    {
      title: t('knowledgeIndex.wikiColumns.outlink_wiki_slugs'),
      key: 'outlink_wiki_slugs',
      width: 180,
      className: 'kb-wiki-col-outlink-slugs',
      render: (_: unknown, row) => renderOutlinkWikiSlugs(row),
    },
    {
      title: t('knowledgeIndex.wikiColumns.outlinks'),
      dataIndex: 'outlinks',
      key: 'outlinks',
      width: 72,
      align: 'center',
      render: (count: number, row) => renderLinkCount(count, row, 'outlinks'),
    },
    {
      title: t('knowledgeIndex.wikiColumns.backlinks'),
      dataIndex: 'backlinks',
      key: 'backlinks',
      width: 72,
      align: 'center',
      render: (count: number, row) => renderLinkCount(count, row, 'backlinks'),
    },
    {
      title: t('knowledgeIndex.wikiColumns.tags'),
      dataIndex: 'tags',
      key: 'tags',
      className: 'kb-index-col-tags',
      render: (tags: string[]) => <KbIndexTagsCell tags={tags} />,
    },
  ]

  if (rows.length === 0) {
    return (
      <div className="kb-index-table-shell fl-table-shell">
        <div className="fl-body fl-body--empty">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('knowledgeIndex.wikiNoTopicsYet')} />
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="kb-index-table-shell fl-table-shell">
        <div className="fl-body" ref={bodyRef}>
          <div ref={tableHostRef} className="kb-index-preview-table-host kb-wiki-index-preview-table-host fl-table-host">
            <Table<KbWikiIndexRow>
              className="kb-index-preview-table kb-wiki-index-preview-table"
              rowKey="fileId"
              size="small"
              columns={columns}
              dataSource={pagedRows}
              tableLayout="fixed"
              pagination={false}
              scroll={tableScroll}
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
      <WikiLinksListModal
        open={linkModal != null}
        onClose={() => setLinkModal(null)}
        fileId={linkModal?.fileId ?? 0}
        fileName={linkModal?.fileName ?? ''}
        linkKind={linkModal?.kind ?? 'outlinks'}
        onOpenFile={onOpenFile}
      />
    </>
  )
}
