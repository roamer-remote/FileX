import type { KbChunkPatchParams } from '@/api/knowledgeBase'

export type KbChunkPatchPayloadInput = {
  originalText: string
  editText: string
  originalBoost: string | null | undefined
  editBoost: string
}

export type BuildKbChunkPatchPayloadResult =
  | { changed: false }
  | { changed: true; patch: KbChunkPatchParams }
  | { changed: true; error: 'empty_text' }

function normalizeBoost(value: string | null | undefined): string {
  return (value ?? '').trim()
}

/** 仅发送实际变更字段，避免 keywords-only 误触正文 PATCH 与 manual_override。 */
export function buildKbChunkPatchPayload(input: KbChunkPatchPayloadInput): BuildKbChunkPatchPayloadResult {
  const originalText = input.originalText.trim()
  const editText = input.editText.trim()
  const textChanged = editText !== originalText
  const boostChanged = normalizeBoost(input.editBoost) !== normalizeBoost(input.originalBoost)

  if (!textChanged && !boostChanged) {
    return { changed: false }
  }

  if (textChanged && !editText) {
    return { changed: true, error: 'empty_text' }
  }

  const patch: KbChunkPatchParams = {}

  if (textChanged) {
    patch.text = editText
    patch.reembed = true
  }

  if (boostChanged) {
    patch.boost_keywords = input.editBoost
    if (!textChanged) {
      patch.reembed = false
    }
  }

  return { changed: true, patch }
}
