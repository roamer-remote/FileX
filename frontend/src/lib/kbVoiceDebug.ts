export type KbVoiceDebugEntry = {
  ts: number
  stage: string
  detail?: Record<string, unknown>
}

const MAX_ENTRIES = 50

let buffer: KbVoiceDebugEntry[] = []

export function isKbVoiceDebugEnabled(): boolean {
  if (typeof localStorage === 'undefined') return false
  return localStorage.getItem('filex_kb_voice_debug') === '1'
}

export function kbVoiceDebugPush(stage: string, detail?: Record<string, unknown>): void {
  if (!isKbVoiceDebugEnabled()) return
  buffer.push({ ts: Date.now(), stage, detail })
  if (buffer.length > MAX_ENTRIES) {
    buffer = buffer.slice(-MAX_ENTRIES)
  }
}

export function kbVoiceDebugDump(): KbVoiceDebugEntry[] {
  return [...buffer]
}

export function resetKbVoiceDebugForTest(): void {
  buffer = []
}

function installDebugGlobal(): void {
  if (typeof window === 'undefined') return
  if (!isKbVoiceDebugEnabled() && !import.meta.env.DEV) return
  ;(
    window as unknown as { __filexKbVoiceDebug?: () => KbVoiceDebugEntry[] }
  ).__filexKbVoiceDebug = kbVoiceDebugDump
}

installDebugGlobal()
