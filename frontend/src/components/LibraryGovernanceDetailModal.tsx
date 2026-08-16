import { useEffect, useMemo, useState } from 'react'
import { Empty, Modal, Spin, Table } from 'antd'
import { useTranslation } from 'react-i18next'
import { getFileById } from '@/api/files'
import {
  getWikiCandidates,
  postWikiLint,
  type WikiCandidateItem,
  type WikiLintResponse,
} from '@/api/knowledgeBase'
import { FlTableMarqueeText } from '@/components/FileListComponents'
import './LibraryGovernanceDetailModal.css'

export type LibraryGovernanceDetailKind = 'broken' | 'pending'

export type LibraryGovernanceDetailModalProps = {
  open: boolean
  kind: LibraryGovernanceDetailKind
  onClose: () => void
  onOpenFile: (fileId: number, options?: { mdNote?: boolean }) => void
  /** 报告内已知的 file_id → 名称，减少重复请求 */
  knownFileNames?: Map<number, string>
}

type BrokenLinkRow = {
  key: string
  source_file_id: number
  source_name: string
  link_kind: string
  target: string
  broken_reason: string
}

function normalizeBrokenRows(lint: WikiLintResponse): Array<Omit<BrokenLinkRow, 'source_name' | 'key'>> {
  const rows: Array<Omit<BrokenLinkRow, 'source_name' | 'key'>> = []
  for (const item of lint.broken_links) {
    const sourceId = Number(item.source_file_id)
    if (!sourceId) continue
    rows.push({
      source_file_id: sourceId,
      link_kind: String(item.link_kind ?? '—'),
      target: String(item.target ?? '—'),
      broken_reason: String(item.broken_reason ?? 'deleted'),
    })
  }
  for (const item of lint.acl_broken_links) {
    const sourceId = Number(item.source_file_id)
    if (!sourceId) continue
    const targetId = item.target_file_id != null ? Number(item.target_file_id) : null
    rows.push({
      source_file_id: sourceId,
      link_kind: 'file',
      target: targetId != null ? `#${targetId}` : '—',
      broken_reason: String(item.broken_reason ?? 'acl'),
    })
  }
  return rows
}

async function resolveFileNames(
  fileIds: number[],
  known: Map<number, string>,
): Promise<Map<number, string>> {
  const names = new Map(known)
  const missing = fileIds.filter((id) => id > 0 && !names.has(id))
  await Promise.all(
    missing.map(async (id) => {
      try {
        const res = await getFileById(id)
        names.set(id, res.data.original_name || res.data.filename || `#${id}`)
      } catch {
        names.set(id, `#${id}`)
      }
    }),
  )
  return names
}

export default function LibraryGovernanceDetailModal({
  open,
  kind,
  onClose,
  onOpenFile,
  knownFileNames,
}: LibraryGovernanceDetailModalProps) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [brokenRows, setBrokenRows] = useState<BrokenLinkRow[]>([])
  const [pendingRows, setPendingRows] = useState<WikiCandidateItem[]>([])
  const [fileNames, setFileNames] = useState<Map<number, string>>(() => new Map())

  useEffect(() => {
    if (!open) return

    let cancelled = false
    setLoading(true)
    setError(false)
    setBrokenRows([])
    setPendingRows([])

    const load = async () => {
      try {
        if (kind === 'broken') {
          const lint = await postWikiLint()
          if (cancelled) return
          const baseRows = normalizeBrokenRows(lint)
          const ids = baseRows.map((row) => row.source_file_id)
          const names = await resolveFileNames(ids, knownFileNames ?? new Map())
          if (cancelled) return
          setFileNames(names)
          setBrokenRows(
            baseRows.map((row, index) => ({
              ...row,
              key: `${row.source_file_id}-${row.target}-${index}`,
              source_name: names.get(row.source_file_id) ?? `#${row.source_file_id}`,
            })),
          )
          return
        }

        const pending = await getWikiCandidates()
        if (cancelled) return
        const ids = pending.flatMap((row) => row.sample_file_ids ?? [])
        const names = await resolveFileNames(ids, knownFileNames ?? new Map())
        if (cancelled) return
        setFileNames(names)
        setPendingRows(pending)
      } catch {
        if (!cancelled) setError(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [open, kind, knownFileNames])

  const title =
    kind === 'broken'
      ? t('libraryMap.brokenLinksDetailTitle')
      : t('libraryMap.pendingConceptsDetailTitle')

  const pendingTableData = useMemo(
    () =>
      pendingRows.map((row) => ({
        key: row.wiki_slug,
        ...row,
      })),
    [pendingRows],
  )

  return (
    <Modal open={open} title={title} footer={null} width={640} onCancel={onClose} destroyOnClose>
      <Spin spinning={loading}>
        {error ? (
          <Empty description={t('libraryMap.detailLoadFailed')} />
        ) : kind === 'broken' ? (
          brokenRows.length === 0 && !loading ? (
            <Empty description={t('libraryMap.brokenLinksDetailEmpty')} />
          ) : (
            <Table<BrokenLinkRow>
              size="small"
              pagination={{ pageSize: 10, hideOnSinglePage: true }}
              rowKey="key"
              dataSource={brokenRows}
              columns={[
                {
                  title: t('libraryMap.detailSourceFile'),
                  dataIndex: 'source_name',
                  ellipsis: true,
                  render: (name: string, row) => (
                    <button
                      type="button"
                      className="library-governance-detail__file-link"
                      title={name}
                      onClick={() => onOpenFile(row.source_file_id, { mdNote: true })}
                    >
                      <FlTableMarqueeText text={name} />
                    </button>
                  ),
                },
                {
                  title: t('libraryMap.detailLinkKind'),
                  dataIndex: 'link_kind',
                  width: 96,
                },
                {
                  title: t('libraryMap.detailTarget'),
                  dataIndex: 'target',
                  ellipsis: true,
                },
                {
                  title: t('libraryMap.detailBrokenReason'),
                  dataIndex: 'broken_reason',
                  width: 96,
                  render: (reason: string) => t(`libraryMap.brokenReason.${reason}`, { defaultValue: reason }),
                },
              ]}
            />
          )
        ) : pendingTableData.length === 0 && !loading ? (
          <Empty description={t('libraryMap.pendingConceptsDetailEmpty')} />
        ) : (
          <Table
            size="small"
            pagination={{ pageSize: 10, hideOnSinglePage: true }}
            rowKey="key"
            dataSource={pendingTableData}
            columns={[
              {
                title: t('libraryMap.slug'),
                dataIndex: 'wiki_slug',
                ellipsis: true,
              },
              {
                title: t('libraryMap.detailSourceCount'),
                dataIndex: 'source_count',
                width: 88,
              },
              {
                title: t('libraryMap.detailSampleSources'),
                key: 'samples',
                render: (_, row: WikiCandidateItem) => (
                  <div className="library-governance-detail__samples">
                    {(row.sample_file_ids ?? []).map((fileId) => {
                      const label = fileNames.get(fileId) ?? `#${fileId}`
                      return (
                        <button
                          key={fileId}
                          type="button"
                          className="library-governance-detail__file-link"
                          title={label}
                          onClick={() => onOpenFile(fileId)}
                        >
                          {label}
                        </button>
                      )
                    })}
                  </div>
                ),
              },
            ]}
          />
        )}
      </Spin>
    </Modal>
  )
}
