import { WIKI_LINKS_HELP_HTML as en } from './wikiLinksHelpEn'
import { WIKI_LINKS_HELP_HTML as zh } from './wikiLinksHelpZh'

export function getWikiLinksHelpHtml(language: string | undefined): string {
  const lang = (language ?? '').toLowerCase()
  if (lang.startsWith('zh')) return zh
  return en
}
