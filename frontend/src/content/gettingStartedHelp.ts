import { GETTING_STARTED_DING_HELP_HTML as dingEn } from './gettingStartedDingHelpEn'
import { GETTING_STARTED_DING_HELP_HTML as dingZh } from './gettingStartedDingHelpZh'
import { GETTING_STARTED_HELP_HTML as en } from './gettingStartedHelpEn'
import { GETTING_STARTED_HELP_HTML as zh } from './gettingStartedHelpZh'

function isZh(language: string | undefined): boolean {
  return (language ?? '').toLowerCase().startsWith('zh')
}

export function getGettingStartedHelpHtml(language: string | undefined): string {
  return isZh(language) ? zh : en
}

export function getGettingStartedDingHelpHtml(language: string | undefined): string {
  return isZh(language) ? dingZh : dingEn
}
