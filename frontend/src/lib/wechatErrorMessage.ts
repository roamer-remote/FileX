import type { TFunction } from 'i18next'

const DETAIL_TO_KEY: Record<string, string> = {
  '该微信账号已绑定到其他用户': 'wechat.errorAlreadyBound',
  '登录会话已过期或无效，请重新扫码': 'wechat.errorSessionExpired',
  '微信验证已使用或已过期': 'wechat.errorSessionUsed',
  '绑定失败，用户不存在': 'wechat.errorBindUserMissing',
  '未配置微信登录，请使用开发 mock 接口': 'wechat.errorNotConfigured',
  '无效的请求状态': 'wechat.errorInvalidState',
}

/** 将后端 OAuth 业务错误转为 i18n 文案 */
export function resolveWechatErrorMessage(detail: string, t: TFunction): string {
  const trimmed = detail.trim()
  if (!trimmed) return t('wechat.errorGeneric')
  const key = DETAIL_TO_KEY[trimmed]
  return key ? t(key) : trimmed
}
