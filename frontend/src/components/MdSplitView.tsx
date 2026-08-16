import { useCallback, useLayoutEffect, useRef, type ReactNode, type RefObject } from 'react'
import { useTranslation } from 'react-i18next'
import { Spin } from 'antd'
import hljs from 'highlight.js'
import { syncTextareaFillHeight } from '@/lib/mdSplitViewTextareaHeight'
import './MdSplitView.css'

export type MdSplitViewProps = {
  source: string
  previewHtml: string
  loading?: boolean
  emptyMessage?: ReactNode
  showHeaders?: boolean
  className?: string
  style?: React.CSSProperties
  previewRef?: RefObject<HTMLDivElement | null>
  syncScroll?: boolean
  fillHeight?: boolean
  editable?: boolean
  onSourceChange?: (value: string) => void
}

export default function MdSplitView({
  source,
  previewHtml,
  loading = false,
  emptyMessage,
  showHeaders = true,
  className,
  style,
  previewRef,
  syncScroll = true,
  fillHeight = false,
  editable = false,
  onSourceChange,
}: MdSplitViewProps) {
  const { t } = useTranslation()
  const sourceRef = useRef<HTMLTextAreaElement>(null)
  const sourceScrollRef = useRef<HTMLDivElement>(null)
  const previewScrollRef = useRef<HTMLDivElement>(null)
  const innerPreviewRef = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    if (!fillHeight || loading) return
    const ta = sourceRef.current
    const pane = sourceScrollRef.current
    if (!ta || !pane) return

    const syncTextareaHeight = () => {
      syncTextareaFillHeight(ta, pane, pane.clientHeight)
    }

    syncTextareaHeight()
    const ro = new ResizeObserver(() => {
      syncTextareaHeight()
    })
    ro.observe(pane)
    return () => ro.disconnect()
  }, [source, fillHeight, loading])

  const syncPreviewScrollFromSource = useCallback(() => {
    if (!syncScroll) return
    const srcPane = sourceScrollRef.current
    const pane = previewScrollRef.current
    if (!srcPane || !pane) return
    const maxSrc = srcPane.scrollHeight - srcPane.clientHeight
    const ratio = maxSrc > 0 ? srcPane.scrollTop / maxSrc : 0
    const maxPv = pane.scrollHeight - pane.clientHeight
    pane.scrollTop = ratio * maxPv
  }, [syncScroll])

  useLayoutEffect(() => {
    if (!previewHtml || loading) return
    const root = innerPreviewRef.current
    if (!root) return
    root.querySelectorAll('pre code').forEach((block) => {
      hljs.highlightElement(block as HTMLElement)
    })
    syncPreviewScrollFromSource()

    if (!syncScroll) return

    let raf = 0
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        syncPreviewScrollFromSource()
      })
    })
    ro.observe(root)
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
    }
  }, [previewHtml, loading, syncScroll, syncPreviewScrollFromSource])

  function handleSourceScroll() {
    syncPreviewScrollFromSource()
  }

  function rootClass(extra?: string) {
    return ['mdsv-root', fillHeight ? 'mdsv-fill' : '', className, extra].filter(Boolean).join(' ')
  }

  function setPreviewNode(node: HTMLDivElement | null) {
    innerPreviewRef.current = node
    if (previewRef) {
      ;(previewRef as { current: HTMLDivElement | null }).current = node
    }
  }

  if (loading) {
    return (
      <div className={rootClass()} style={style}>
        <div className="mdsv-loading">
          <Spin />
        </div>
      </div>
    )
  }

  if (!source.trim() && !previewHtml.trim() && !editable) {
    return (
      <div className={rootClass()} style={style}>
        <div className="mdsv-empty">{emptyMessage ?? t('filePreview.mdEmpty')}</div>
      </div>
    )
  }

  return (
    <div className={rootClass()} style={style}>
      <div className="mdsv-panes">
        <div className="mdsv-pane">
          {showHeaders ? <div className="mdsv-pane-head">{t('mdSplitView.source')}</div> : null}
          <div className="mdsv-source-scroll" ref={sourceScrollRef} onScroll={handleSourceScroll}>
            <textarea
              ref={sourceRef}
              className="mdsv-source"
              value={source}
              readOnly={!editable}
              spellCheck={false}
              aria-label={t('mdSplitView.source')}
              onChange={editable && onSourceChange ? (e) => onSourceChange(e.target.value) : undefined}
            />
          </div>
        </div>
        <div className="mdsv-pane">
          {showHeaders ? <div className="mdsv-pane-head">{t('mdSplitView.preview')}</div> : null}
          <div className="mdsv-preview-scroll" ref={previewScrollRef}>
            <div
              ref={setPreviewNode}
              className="mdsv-preview markdown-body fb-markdown-host"
              dangerouslySetInnerHTML={{ __html: previewHtml }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
