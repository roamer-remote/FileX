import { Button, Modal } from 'antd'
import '@/styles/helpDoc.css'

export type HelpDocModalProps = {
  open: boolean
  onClose: () => void
  title: string
  closeLabel: string
  html: string
  width?: number
  maskClosable?: boolean
  onFooterClick?: () => void
}

export default function HelpDocModal({
  open,
  onClose,
  title,
  closeLabel,
  html,
  width = 600,
  maskClosable = true,
  onFooterClick,
}: HelpDocModalProps) {
  return (
    <Modal
      open={open}
      title={title}
      onCancel={onClose}
      maskClosable={maskClosable}
      footer={
        <Button type="primary" onClick={onFooterClick ?? onClose}>
          {closeLabel}
        </Button>
      }
      width={width}
      destroyOnClose
      centered
      rootClassName="wlg-help-modal"
    >
      <article className="wlg-help-doc" dangerouslySetInnerHTML={{ __html: html }} />
    </Modal>
  )
}
