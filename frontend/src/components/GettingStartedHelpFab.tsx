import { useState } from 'react'
import { QuestionCircleOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import './GettingStartedHelpFab.css'

const FAB_SIZE = 52
const LOGO_SRC = '/filex-logo.png'

export type GettingStartedHelpFabProps = {
  onClick: () => void
}

export default function GettingStartedHelpFab({ onClick }: GettingStartedHelpFabProps) {
  const { t } = useTranslation()
  const [logoFailed, setLogoFailed] = useState(false)

  return (
    <button
      type="button"
      className="getting-started-help-fab"
      style={{ width: FAB_SIZE, height: FAB_SIZE }}
      aria-label={t('gettingStarted.fabLabel')}
      onClick={onClick}
    >
      {logoFailed ? (
        <span className="getting-started-help-fab__fallback" aria-hidden="true">
          <QuestionCircleOutlined />
        </span>
      ) : (
        <span className="getting-started-help-fab__inner" aria-hidden="true">
          <img
            className="getting-started-help-fab__logo"
            src={LOGO_SRC}
            alt=""
            width={36}
            height={36}
            onError={() => setLogoFailed(true)}
          />
          <span className="getting-started-help-fab__badge">?</span>
        </span>
      )}
    </button>
  )
}
