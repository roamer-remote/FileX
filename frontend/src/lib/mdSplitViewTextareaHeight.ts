/** fillHeight 模式下同步 textarea 高度，并保留光标与滚动位置。 */
export function syncTextareaFillHeight(
  textarea: HTMLTextAreaElement,
  scrollContainer: HTMLElement,
  paneClientHeight: number,
): void {
  const selectionStart = textarea.selectionStart
  const selectionEnd = textarea.selectionEnd
  const containerScrollTop = scrollContainer.scrollTop
  const textareaScrollTop = textarea.scrollTop

  textarea.style.height = '0'
  const nextHeight = Math.max(textarea.scrollHeight, paneClientHeight)
  textarea.style.height = `${nextHeight}px`

  textarea.setSelectionRange(selectionStart, selectionEnd)
  scrollContainer.scrollTop = containerScrollTop
  textarea.scrollTop = textareaScrollTop
}
