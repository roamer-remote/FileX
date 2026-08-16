import { cancelKbVoice } from '@/lib/kbVoiceSpeak'
import type { KbVoiceNotifyState } from '@/lib/kbVoiceNotify'

let activeState: KbVoiceNotifyState | null = null

export function registerKbVoiceNotifyState(state: KbVoiceNotifyState): () => void {
  activeState = state
  return () => {
    if (activeState === state) {
      activeState = null
    }
  }
}

/** 退出登录或 useKbVoiceNotify 卸载时停止 TTS 并清空 debounce 状态 */
export function teardownKbVoiceNotify(): void {
  cancelKbVoice()
  activeState?.reset()
}
