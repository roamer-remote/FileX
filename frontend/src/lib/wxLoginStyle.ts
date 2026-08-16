/**
 * 微信 WxLogin iframe 内样式（href 须为 https 或 data:text/css;base64）。
 * 外层容器使用 `.wechat-embed-surface` + `--canvas`，与 bgcolor / href 保持同一底色。
 */
export const WECHAT_EMBED_SURFACE_CLASS = 'wechat-embed-surface'

const WX_EMBED_BG_FALLBACK = {
  dark: '1c1c1e',
  light: 'f5f5f7',
} as const

function cssToDataUrl(css: string): string {
  const bytes = new TextEncoder().encode(css)
  let binary = ''
  for (const b of bytes) binary += String.fromCharCode(b)
  return `data:text/css;base64,${btoa(binary)}`
}

/** 与 cyber.css 中 --canvas 对齐（WxLogin bgcolor 仅接受无 # 的 hex） */
export function getWxLoginBgcolor(theme: 'light' | 'dark'): string {
  if (typeof document !== 'undefined') {
    const raw = getComputedStyle(document.documentElement).getPropertyValue('--canvas').trim()
    if (raw.startsWith('#') && /^#[0-9a-fA-F]{6}$/.test(raw)) {
      return raw.slice(1).toLowerCase()
    }
  }
  return WX_EMBED_BG_FALLBACK[theme]
}

function embedBgRules(hex: string): string {
  const bg = `#${hex}`
  return `
html,
body,
.impowerBox,
.web_qrcode_panel,
.web_qrcode_panel_wrp,
.confirm_login_panel,
.login_confirm_panel,
.auth_confirm,
.wrp_code,
.quick_login_box,
.loginPanel,
.loginPanel.normalPanel,
.wrp_page_login,
.page_login,
#wx_after_scan {
  background-color: ${bg} !important;
}
`
}

/** 扫码成功等状态文案（如「微信登录成功」）与容器 */
function darkStatusRules(hex: string): string {
  const bg = `#${hex}`
  const text = '#f5f5f7'
  const muted = '#a1a1a6'
  return `
.impowerBox .status,
.impowerBox .status_succ,
.impowerBox .status_fail,
.status_succ,
.status_fail,
.login_succ,
.wrp_login_succ {
  background-color: ${bg} !important;
  color: ${text} !important;
  border: none !important;
  text-align: center !important;
}
.impowerBox .status p,
.impowerBox .status_succ p,
.impowerBox .status_fail p {
  color: ${text} !important;
}
.impowerBox .info,
.impowerBox .info p {
  color: ${muted} !important;
}
`
}

function darkWxCss(hex: string): string {
  return `${embedBgRules(hex)}
${darkStatusRules(hex)}
.impowerBox {
  color: #f5f5f7 !important;
}
.impowerBox .title {
  display: none !important;
}
.impowerBox .qrcode {
  width: 200px;
  margin: 0 auto;
  border: none !important;
}
.status_icon {
  display: none !important;
}
`.trim()
}

function lightWxCss(hex: string): string {
  return `${embedBgRules(hex)}
.impowerBox .title {
  display: none !important;
}
.impowerBox .qrcode {
  width: 200px;
  margin: 0 auto;
  border: none !important;
}
.status_icon {
  display: none !important;
}
`.trim()
}

export function getWxLoginColorScheme(theme: 'light' | 'dark'): 'light' | 'dark' {
  return theme
}

export function getWxLoginHref(theme: 'light' | 'dark'): string {
  const hex = getWxLoginBgcolor(theme)
  return cssToDataUrl(theme === 'dark' ? darkWxCss(hex) : lightWxCss(hex))
}

/** 深色页面背景用 white（浅色字），浅色背景用 black（深色字），见微信开放平台 FAQ */
export function getWxLoginStyle(theme: 'light' | 'dark'): 'black' | 'white' {
  return theme === 'dark' ? 'white' : 'black'
}
