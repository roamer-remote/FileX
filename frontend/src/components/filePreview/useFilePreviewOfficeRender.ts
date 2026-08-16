import { useLayoutEffect, type RefObject } from 'react'
import { renderAsync } from 'docx-preview'
import { getPreviewUrl, type FileItem } from '@/api/files'
import { sanitizeSpreadsheetHtml } from '@/utils/sanitizeHtml'
import { waitPaintFrames } from '@/utils/mdNotePreview'
import type { ExcelPreviewTab } from './filePreviewMime'
import {
  isDocxLike,
  isExcelLike,
  isLegacyDocForPreview,
  isLegacyPptForPreview,
  isPptxLike,
} from './filePreviewMime'

export const OFFICE_RENDER_TIMEOUT_MS = 90_000

type PptxPreviewer = {
  destroy: () => void
  preview: (file: ArrayBuffer) => Promise<unknown>
}

type OfficeRenderArgs = {
  open: boolean
  file: FileItem | null
  docxBodyRef: RefObject<HTMLDivElement | null>
  pptxWrapperRef: RefObject<HTMLDivElement | null>
  pptxPreviewerRef: RefObject<PptxPreviewer | null>
  setOfficeLoading: (v: boolean) => void
  setOfficeError: (v: boolean) => void
  setExcelTabs: (tabs: ExcelPreviewTab[]) => void
}

export function useFilePreviewOfficeRender({
  open,
  file,
  docxBodyRef,
  pptxWrapperRef,
  pptxPreviewerRef,
  setOfficeLoading,
  setOfficeError,
  setExcelTabs,
}: OfficeRenderArgs) {
  useLayoutEffect(() => {
    if (!open || !file || !(isDocxLike(file) || isLegacyDocForPreview(file))) {
      docxBodyRef.current?.replaceChildren()
      return
    }
    let cancelled = false
    setOfficeLoading(true)
    setOfficeError(false)
    docxBodyRef.current?.replaceChildren()

    void (async () => {
      await waitPaintFrames(2)
      if (cancelled) return
      const bodyEl = docxBodyRef.current
      if (!bodyEl) {
        setOfficeError(true)
        setOfficeLoading(false)
        return
      }
      bodyEl.replaceChildren()
      try {
        const res = await fetch(getPreviewUrl(file.id))
        if (!res.ok) throw new Error(String(res.status))
        const buf = await res.arrayBuffer()
        if (cancelled) return
        await Promise.race([
          renderAsync(buf, bodyEl, undefined, { inWrapper: true }),
          new Promise<never>((_, rej) => {
            setTimeout(() => rej(new Error('docx render timeout')), OFFICE_RENDER_TIMEOUT_MS)
          }),
        ])
        if (!cancelled) setOfficeLoading(false)
      } catch {
        if (!cancelled) {
          setOfficeError(true)
          setOfficeLoading(false)
        }
      }
    })()

    return () => {
      cancelled = true
      docxBodyRef.current?.replaceChildren()
    }
  }, [open, file?.id, file?.mime_type, file?.original_name, file?.preview_mime_type, docxBodyRef, pptxWrapperRef, pptxPreviewerRef, setOfficeLoading, setOfficeError, setExcelTabs])

  useLayoutEffect(() => {
    if (!open || !file || !(isPptxLike(file) || isLegacyPptForPreview(file))) {
      pptxPreviewerRef.current?.destroy()
      pptxPreviewerRef.current = null
      pptxWrapperRef.current?.replaceChildren()
      return
    }
    let cancelled = false
    setOfficeLoading(true)
    setOfficeError(false)
    pptxPreviewerRef.current?.destroy()
    pptxPreviewerRef.current = null
    pptxWrapperRef.current?.replaceChildren()

    void (async () => {
      await waitPaintFrames(2)
      if (cancelled) return
      const el = pptxWrapperRef.current
      if (!el) {
        setOfficeError(true)
        setOfficeLoading(false)
        return
      }
      try {
        const { init } = await import('pptx-preview')
        if (cancelled) return
        const previewer = init(el, { width: 960, height: 540 }) as PptxPreviewer
        pptxPreviewerRef.current = previewer
        const res = await fetch(getPreviewUrl(file.id))
        if (!res.ok) throw new Error(String(res.status))
        const buf = await res.arrayBuffer()
        if (cancelled) return
        await Promise.race([
          previewer.preview(buf),
          new Promise<never>((_, rej) => {
            setTimeout(() => rej(new Error('pptx render timeout')), OFFICE_RENDER_TIMEOUT_MS)
          }),
        ])
        if (!cancelled) setOfficeLoading(false)
      } catch {
        if (!cancelled) {
          setOfficeError(true)
          setOfficeLoading(false)
        }
      }
    })()

    return () => {
      cancelled = true
      pptxPreviewerRef.current?.destroy()
      pptxPreviewerRef.current = null
      pptxWrapperRef.current?.replaceChildren()
    }
  }, [open, file?.id, file?.mime_type, file?.original_name, file?.preview_mime_type, docxBodyRef, pptxWrapperRef, pptxPreviewerRef, setOfficeLoading, setOfficeError, setExcelTabs])

  useLayoutEffect(() => {
    if (!open || !file || !isExcelLike(file)) {
      setExcelTabs([])
      return
    }
    let cancelled = false
    setOfficeLoading(true)
    setOfficeError(false)
    setExcelTabs([])

    void (async () => {
      await waitPaintFrames(2)
      if (cancelled) return
      try {
        const res = await fetch(getPreviewUrl(file.id))
        if (!res.ok) throw new Error(String(res.status))
        const buf = await res.arrayBuffer()
        if (cancelled) return
        const XLSX = await import('xlsx')
        const wb = XLSX.read(buf, { type: 'array' })
        if (cancelled) return
        if (!wb.SheetNames.length) {
          setOfficeError(true)
          setOfficeLoading(false)
          return
        }
        const tabs = wb.SheetNames.map((sheetName, i) => ({
          key: `sheet-${i}`,
          label: sheetName || `Sheet${i + 1}`,
          html: sanitizeSpreadsheetHtml(
            XLSX.utils.sheet_to_html(wb.Sheets[sheetName], { editable: false }),
          ),
        }))
        if (!cancelled) {
          setExcelTabs(tabs)
          setOfficeLoading(false)
        }
      } catch {
        if (!cancelled) {
          setOfficeError(true)
          setOfficeLoading(false)
        }
      }
    })()

    return () => {
      cancelled = true
      setExcelTabs([])
    }
  }, [open, file?.id, file?.mime_type, file?.original_name, file?.preview_mime_type, setOfficeLoading, setOfficeError, setExcelTabs])
}
