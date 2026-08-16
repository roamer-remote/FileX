import { useTranslation } from 'react-i18next'
import { switchLanguage } from '@/i18n'
import './LanguageSwitcher.css'

export default function LanguageSwitcher() {
  const { i18n, t } = useTranslation()
  const code = i18n.language === 'zh-CN' ? 'ZH' : 'EN'

  function toggle() {
    switchLanguage(i18n.language === 'zh-CN' ? 'en' : 'zh-CN')
  }

  return (
    <button type="button" className="fx-btn lang-switcher" onClick={toggle} title={t('common.switchLang')}>
      <span className="lang-code">{code}</span>
    </button>
  )
}
