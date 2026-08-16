import { Modal } from 'antd'
import { useTranslation } from 'react-i18next'
import AccountOverview from '@/pages/account/AccountOverview'
import './AccountOverviewModal.css'

type AccountOverviewModalProps = {
  open: boolean
  onClose: () => void
}

export default function AccountOverviewModal({ open, onClose }: AccountOverviewModalProps) {
  const { t } = useTranslation()

  return (
    <Modal
      title={t('account.title')}
      open={open}
      onCancel={onClose}
      footer={null}
      destroyOnClose
      width="min(960px, calc(100vw - 32px))"
      className="account-overview-modal"
      styles={{ body: { paddingTop: 8 } }}
    >
      <AccountOverview embedded onNavigateAway={onClose} />
    </Modal>
  )
}
