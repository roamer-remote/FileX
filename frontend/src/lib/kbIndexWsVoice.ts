/** 054 WS 补发事件仅 patch UI，不进入语音状态机 */
export function shouldVoiceNotifyKbWsEvent(event: { _replay?: boolean }): boolean {
  return event._replay !== true
}
