import {
  cloneElement,
  forwardRef,
  isValidElement,
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type Key,
  type MouseEvent,
  type ReactElement,
} from "react"
import { useTranslation } from "react-i18next"
import { Tag, Tooltip, type TooltipProps } from "antd"
import { useFilesStore } from "@/stores/filesStore"
import type { FileItem } from "@/api/files"

export function indexStatusLabelKey(status: string | undefined): string {
  switch (status) {
    case "pending":
      return "kbIndex.statusPending"
    case "indexing":
      return "kbIndex.statusIndexing"
    case "ready":
      return "kbIndex.statusReady"
    case "failed":
      return "kbIndex.statusFailed"
    default:
      return "kbIndex.statusSkipped"
  }
}

export function extractStatusLabelKey(status: string | undefined): string {
  switch (status) {
    case "pending":
      return "kbIndex.statusExtractPending"
    case "extracting":
      return "kbIndex.statusExtracting"
    case "ready":
      return "kbIndex.statusExtractReady"
    case "failed":
      return "kbIndex.statusExtractFailed"
    case "not_needed":
      return "kbIndex.statusExtractNotNeeded"
    case "waiting_gpu":
      return "kbIndex.statusExtractWaitingGpu"
    default:
      return "kbIndex.statusExtractNotNeeded"
  }
}

export function fileExt(name: string): string {
  const i = name.lastIndexOf(".")
  return i >= 0 ? name.slice(i + 1).toLowerCase() : ""
}

export const EXTRACTABLE_EXT = new Set([
  "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
  "jpg", "jpeg", "png", "gif", "bmp", "webp",
])

export const MARKDOWN_EXT = new Set(["md", "markdown"])

export function isMarkdownFile(row: FileItem): boolean {
  return MARKDOWN_EXT.has(fileExt(row.original_name || row.filename || ""))
}

export function canAutoExtract(row: FileItem): boolean {
  return EXTRACTABLE_EXT.has(fileExt(row.original_name || row.filename || ""))
}

export function canReextract(row: FileItem): boolean {
  return canAutoExtract(row) || isMarkdownFile(row)
}

export function isExtractBusy(status: string | undefined): boolean {
  return status === "pending" || status === "extracting"
}

/** 表头「AI」与后缀分行显示 */
export function TableHeadAiBreak({ line2 }: { line2: string }) {
  return (
    <span className="fl-th-ai-break">
      AI<br />{line2}
    </span>
  )
}

/** 列表/网格：向量索引状态与块数 */
export function FlKbIndexCell({
  row,
  compact,
  onViewVectors,
}: {
  row: FileItem
  compact?: boolean
  onViewVectors?: (row: FileItem) => void
}) {
  const { t } = useTranslation()
  const status = row.index_status ?? "skipped"
  const count = row.chunk_count ?? 0
  const ready = status === "ready"
  const postStatus = row.kb_post_status
  const postBusy = ready && (postStatus === "queued" || postStatus === "running")
  const postFailed = ready && postStatus === "failed"
  const statusLabel = t(indexStatusLabelKey(status))

  const exStatus = row.extract_status ?? "not_needed"
  const showExtract = exStatus !== "not_needed" || canAutoExtract(row)
  const extractLabel = t(extractStatusLabelKey(exStatus))
  const tooltip = (
    <>
      {showExtract ? <div>{t("kbIndex.tooltipExtract", { status: extractLabel })}</div> : null}
      <div>{t("kbIndex.tooltipEngine", { engine: row.extract_engine?.trim() || "—" })}</div>
      {ready ? <div>{t("kbIndex.tooltipChunks", { count })}</div> : null}
      {row.extract_error ? <div>{t("kbIndex.tooltipExtractError", { error: row.extract_error })}</div> : null}
      {row.index_error ? <div>{t("kbIndex.tooltipError", { error: row.index_error })}</div> : null}
      {postBusy ? <div>{t("kbIndex.tooltipPostRunning")}</div> : null}
      {postFailed ? <div>{t("kbIndex.tooltipPostFailed")}</div> : null}
      {row.kb_post_error ? <div>{t("kbIndex.tooltipPostError", { error: row.kb_post_error })}</div> : null}
    </>
  )

  const display = ready ? (
    <span className="fl-index-ready-wrap">
      <span className="fl-index-count fl-index-count--ready">{count}</span>
      {postBusy ? (
        <Tag className="fl-index-post-badge" color="processing">
          {t("kbIndex.postBadge")}
        </Tag>
      ) : null}
      {postFailed ? (
        <Tag className="fl-index-post-badge" color="error">
          {t("kbIndex.postStatusFailed")}
        </Tag>
      ) : null}
    </span>
  ) : (
    <span className={`fl-index-status fl-index-status--${status}`}>
      {compact && status === "skipped" ? "—" : statusLabel}
    </span>
  )

  const canOpen = ready && count > 0 && onViewVectors
  const inner = canOpen ? (
    <button
      type="button"
      className="fl-index-cell fl-index-cell--numeric fl-index-cell--btn"
      onClick={(e) => {
        e.stopPropagation()
        onViewVectors(row)
      }}
    >
      {display}
    </button>
  ) : (
    <span className="fl-index-cell fl-index-cell--numeric">{display}</span>
  )

  return (
    <Tooltip placement="topLeft" overlayClassName="fl-index-tooltip-overlay" title={canOpen ? <>{tooltip}<div>{t("kbVectors.openHint")}</div></> : tooltip}>
      {inner}
    </Tooltip>
  )
}

export function MarqueeTooltip({
  active,
  title,
  children,
  placement = "topLeft",
}: {
  active: boolean
  title: string
  children: ReactElement
  placement?: TooltipProps["placement"]
}) {
  if (!isValidElement(children)) return children
  const child = children as ReactElement<{ className?: string }>
  const trigger = cloneElement(child, {
    className: child.props.className
      ? `${child.props.className} marquee-tooltip-trigger`
      : "marquee-tooltip-trigger",
  })
  return (
    <Tooltip title={active ? title : undefined} placement={placement} mouseEnterDelay={0.35}>
      {trigger}
    </Tooltip>
  )
}

/** 网格卡片：标签单行，溢出时无缝走马灯 */
export function FlGridCardTags({ tags }: { tags: string[] }) {
  const setTagFilter = useFilesStore((s) => s.setTagFilter)
  const viewportRef = useRef<HTMLDivElement>(null)
  const stripRef = useRef<HTMLDivElement>(null)
  const [marquee, setMarquee] = useState(false)
  useLayoutEffect(() => {
    const vp = viewportRef.current
    const strip = stripRef.current
    if (!vp || !strip) return
    const measure = () => {
      const overflow = strip.scrollWidth > vp.clientWidth + 1
      setMarquee(overflow)
      if (overflow) {
        const w = strip.scrollWidth
        const sec = Math.min(48, Math.max(8, w / 26))
        vp.style.setProperty("--fl-tags-marquee-sec", `${sec}s`)
      }
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(vp)
    ro.observe(strip)
    return () => ro.disconnect()
  }, [tags])

  const title = tags.join("、")
  const onTagClick = (e: MouseEvent, tg: string) => {
    e.stopPropagation()
    setTagFilter(tg)
  }

  return (
    <MarqueeTooltip active={marquee} title={title}>
      <div ref={viewportRef} className="fl-card-tags">
        <div className={marquee ? "fl-card-tags-track fl-card-tags-track--marquee" : "fl-card-tags-track"}>
          <div ref={stripRef} className="fl-card-tags-strip">
            {tags.map((tg, i) => (
              <Tag key={`${i}-${tg}`} color="success" className="fl-card-tags-tag" style={{ cursor: "pointer" }} onClick={(e) => onTagClick(e, tg)}>{tg}</Tag>
            ))}
          </div>
          {marquee ? (
            <div className="fl-card-tags-strip" aria-hidden>
              {tags.map((tg, i) => (
                <Tag key={`d-${i}-${tg}`} color="success" className="fl-card-tags-tag" style={{ cursor: "pointer" }} onClick={(e) => onTagClick(e, tg)}>{tg}</Tag>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </MarqueeTooltip>
  )
}

/** 表格单元格：完整文案，溢出时走马灯；溢出时悬停 Tooltip 显示全文 */
export function FlTableMarqueeText({
  text,
  className,
  title,
  tooltip,
}: {
  text: string
  className?: string
  /** @deprecated 请用 tooltip；原生 title，传空字符串可禁用 */
  title?: string
  /** Ant Design Tooltip；false 禁用；默认溢出走马灯时显示 text */
  tooltip?: string | false
}) {
  const viewportRef = useRef<HTMLSpanElement>(null)
  const stripRef = useRef<HTMLSpanElement>(null)
  const [marquee, setMarquee] = useState(false)

  useLayoutEffect(() => {
    const vp = viewportRef.current
    const strip = stripRef.current
    if (!vp || !strip) return
    const measure = () => {
      const overflow = strip.scrollWidth > vp.clientWidth + 1
      setMarquee(overflow)
      if (overflow) {
        const w = strip.scrollWidth
        vp.style.setProperty("--fl-table-marquee-sec", `${Math.min(48, Math.max(8, w / 28))}s`)
      }
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(vp)
    ro.observe(strip)
    return () => ro.disconnect()
  }, [text])

  const tooltipTitle =
    tooltip === false ? null : typeof tooltip === "string" ? tooltip : text
  const showTooltip = marquee && Boolean(tooltipTitle)
  const nativeTitle =
    showTooltip || title === "" ? undefined : title !== undefined ? title : undefined

  const content = (
    <span
      className={className ? `fl-table-marquee ${className}` : "fl-table-marquee"}
      title={nativeTitle}
    >
      <span ref={viewportRef} className="fl-table-marquee-viewport">
        <span className={marquee ? "fl-table-marquee-track fl-table-marquee-track--on" : "fl-table-marquee-track"}>
          <span ref={stripRef} className="fl-table-marquee-strip">{text}</span>
          {marquee ? <span className="fl-table-marquee-strip" aria-hidden>{text}</span> : null}
        </span>
      </span>
    </span>
  )

  return (
    <MarqueeTooltip active={showTooltip} title={tooltipTitle ?? ""}>
      {content}
    </MarqueeTooltip>
  )
}
