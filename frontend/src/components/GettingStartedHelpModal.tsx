import { useEffect, useMemo, useState } from 'react'
import { Button, Modal } from 'antd'
import { useTranslation } from 'react-i18next'
import { getGettingStartedDingHelpHtml, getGettingStartedHelpHtml } from '@/content/gettingStartedHelp'
import { getSystemHelpHtml } from '@/content/systemHelp'
import '@/styles/helpDoc.css'

const MODAL_MAX_WIDTH = 960
const MODAL_VIEWPORT_GUTTER = 32

export type HelpSection = 'start' | 'ding' | 'system'

function modalWidthForViewport(viewportWidth: number): number {
  return Math.min(MODAL_MAX_WIDTH, Math.max(280, viewportWidth - MODAL_VIEWPORT_GUTTER))
}

export type GettingStartedHelpModalProps = {
  open: boolean
  onDismiss: () => void
  onGotIt: () => void
  initialSection?: HelpSection
}

export default function GettingStartedHelpModal({
  open,
  onDismiss,
  onGotIt,
  initialSection = 'start',
}: GettingStartedHelpModalProps) {
  const { t, i18n } = useTranslation()
  const [section, setSection] = useState<HelpSection>(initialSection)
  const startHtml = useMemo(() => getGettingStartedHelpHtml(i18n.language), [i18n.language])
  const dingHtml = useMemo(() => getGettingStartedDingHelpHtml(i18n.language), [i18n.language])
  const systemHtml = useMemo(() => getSystemHelpHtml(i18n.language), [i18n.language])
  const [width, setWidth] = useState(() =>
    typeof window !== 'undefined' ? modalWidthForViewport(window.innerWidth) : MODAL_MAX_WIDTH,
  )

  useEffect(() => {
    const update = () => setWidth(modalWidthForViewport(window.innerWidth))
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  useEffect(() => {
    if (open) setSection(initialSection)
  }, [open, initialSection])

  const sectionNav = (
    <nav
      className="wlg-help-section-nav wlg-help-section-nav--title"
      role="tablist"
      aria-label={t('gettingStarted.sectionNav')}
    >
      <button
        type="button"
        role="tab"
        className={`wlg-help-section-btn wlg-help-section-btn--start${section === 'start' ? ' is-active' : ''}`}
        aria-selected={section === 'start'}
        onClick={() => setSection('start')}
      >
        {t('gettingStarted.tabStart')}
      </button>
      <button
        type="button"
        role="tab"
        className={`wlg-help-section-btn wlg-help-section-btn--ding${section === 'ding' ? ' is-active' : ''}`}
        aria-selected={section === 'ding'}
        onClick={() => setSection('ding')}
      >
        {t('gettingStarted.tabDing')}
      </button>
      <button
        type="button"
        role="tab"
        className={`wlg-help-section-btn wlg-help-section-btn--system${section === 'system' ? ' is-active' : ''}`}
        aria-selected={section === 'system'}
        onClick={() => setSection('system')}
      >
        {t('gettingStarted.tabSystem')}
      </button>
    </nav>
  )

  return (
    <Modal
      open={open}
      title={
        <div className="wlg-help-modal-titlebar">
          <span className="wlg-help-modal-titlebar__label">{t('gettingStarted.title')}</span>
          {sectionNav}
        </div>
      }
      onCancel={onDismiss}
      maskClosable={false}
      footer={
        <Button type="primary" onClick={onGotIt}>
          {t('gettingStarted.close')}
        </Button>
      }
      width={width}
      destroyOnClose
      centered
      rootClassName="wlg-help-modal wlg-help-modal--sections"
    >
      <div className="wlg-help-section-panels">
        <article
          className={`wlg-help-doc wlg-help-section-panel wlg-help-section-panel--start${section === 'start' ? ' is-active' : ''}`}
          aria-hidden={section !== 'start'}
          dangerouslySetInnerHTML={{ __html: startHtml }}
        />
        <article
          className={`wlg-help-doc wlg-help-doc--ding wlg-help-section-panel wlg-help-section-panel--ding${section === 'ding' ? ' is-active' : ''}`}
          aria-hidden={section !== 'ding'}
          dangerouslySetInnerHTML={{ __html: dingHtml }}
        />
        <article
          className={`wlg-help-doc wlg-help-section-panel wlg-help-section-panel--system${section === 'system' ? ' is-active' : ''}`}
          aria-hidden={section !== 'system'}
          dangerouslySetInnerHTML={{ __html: systemHtml }}
        />
      </div>
    </Modal>
  )
}
