/**
 * 复制文本到剪贴板。优先 Clipboard API；失败或非安全上下文时降级 execCommand。
 * 须在用户手势（click）回调链内调用，降级路径才能可靠工作。
 */
export async function copyToClipboard(text: string): Promise<void> {
  if (typeof document === 'undefined') {
    throw new Error('clipboard unavailable')
  }

  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      /* 权限拒绝、非焦点文档等：尝试降级 */
    }
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', 'true')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '0'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  textarea.setSelectionRange(0, text.length)

  let ok = false
  try {
    ok = document.execCommand('copy')
  } finally {
    document.body.removeChild(textarea)
  }

  if (!ok) {
    throw new Error('clipboard copy failed')
  }
}
