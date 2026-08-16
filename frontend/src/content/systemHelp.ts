import { SYSTEM_HELP_HTML as en } from './systemHelpEn'
import { SYSTEM_HELP_HTML as zh } from './systemHelpZh'

export function getSystemHelpHtml(language: string | undefined): string {
  const lang = (language ?? '').toLowerCase()
  if (lang.startsWith('zh')) return zh
  return en
}
