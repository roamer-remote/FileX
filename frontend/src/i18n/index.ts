import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { patchLocaleUiState } from '@/lib/uiStateSync'
import en from './locales/en'
import zhCN from './locales/zh-CN'

function readSavedLocale(): 'zh-CN' | 'en' {
  try {
    const stored = globalThis.localStorage?.getItem('filex_locale')
    if (stored === 'en' || stored === 'zh-CN') {
      return stored
    }
  } catch {
    // Node/vitest 或无 localStorage 环境
  }
  return 'zh-CN'
}

const savedLocale = readSavedLocale()

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    'zh-CN': { translation: zhCN },
  },
  lng: savedLocale,
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

export function switchLanguage(lang: 'zh-CN' | 'en') {
  void i18n.changeLanguage(lang)
  try {
    globalThis.localStorage?.setItem('filex_locale', lang)
  } catch {
    // ignore
  }
  patchLocaleUiState(lang)
}

export default i18n
