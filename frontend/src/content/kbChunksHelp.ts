import { KB_CHUNKS_HELP_HTML as en } from './kbChunksHelpEn'
import { KB_CHUNKS_HELP_HTML as zh } from './kbChunksHelpZh'

export function getKbChunksHelpHtml(language: string | undefined): string {
  const lang = (language ?? '').toLowerCase()
  if (lang.startsWith('zh')) return zh
  return en
}
