import { describe, expect, it } from 'vitest'
import { FIGMA_FACTORY_ORIGIN } from './mqFigmaTheme'
import { FIGMA_TASK_BUBBLE, figmaTaskBubbleForeignObject } from './mqFigmaArmLayout'

describe('mq figma task bubble layout', () => {
  it('keeps the running task bubble inside the workshop row top edge', () => {
    const box = figmaTaskBubbleForeignObject()
    const absoluteTop = FIGMA_FACTORY_ORIGIN.y + FIGMA_TASK_BUBBLE.anchorY + box.y

    expect(absoluteTop).toBeGreaterThanOrEqual(8)
  })
})
