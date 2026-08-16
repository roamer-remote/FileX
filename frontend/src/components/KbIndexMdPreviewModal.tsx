import { useEffect, useState } from 'react'
import { getFileById, type FileItem } from '@/api/files'
import MdNoteViewModal from '@/components/MdNoteViewModal'

type Props = {
  open: boolean
  fileId: number
  fileName: string
  onClose: () => void
}

export default function KbIndexMdPreviewModal({ open, fileId, fileName, onClose }: Props) {
  const [file, setFile] = useState<FileItem | null>(null)

  useEffect(() => {
    if (!open || !fileId) {
      setFile(null)
      return
    }
    let cancelled = false
    void getFileById(fileId)
      .then((res) => {
        if (!cancelled) setFile({ ...res.data, original_name: fileName })
      })
      .catch(() => {
        if (!cancelled) setFile(null)
      })
    return () => {
      cancelled = true
    }
  }, [open, fileId, fileName])

  return <MdNoteViewModal open={open} file={file} onClose={onClose} readOnly />
}
