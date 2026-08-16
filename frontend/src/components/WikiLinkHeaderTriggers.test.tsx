/**
 * @vitest-environment jsdom
 */

import { act } from 'react-dom/test-utils'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BacklinkHeaderTrigger, OutlinkHeaderTrigger } from './WikiLinkHeaderTriggers'

async function renderTrigger(node: React.ReactNode) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root: Root = createRoot(container)

  await act(async () => {
    root.render(node)
  })

  return { container, root }
}

describe('WikiLinkHeaderTriggers', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('renders static text when count is zero', async () => {
    await renderTrigger(
      <OutlinkHeaderTrigger label="本资料提及了其他 0 篇资料" count={0} onOpenList={vi.fn()} />,
    )

    expect(document.body.querySelector('button')).toBeNull()
    expect(document.body.textContent).toContain('本资料提及了其他 0 篇资料')
  })

  it('opens list modal via button when count is positive', async () => {
    const onOpenList = vi.fn()
    await renderTrigger(
      <BacklinkHeaderTrigger
        label="3 篇资料提及了本资料"
        count={3}
        onOpenList={onOpenList}
      />,
    )

    const button = document.body.querySelector('button')
    expect(button).toBeTruthy()

    await act(async () => {
      button!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(onOpenList).toHaveBeenCalledTimes(1)
    expect(document.body.querySelector('.pv-mention-chip')).toBeNull()
  })
})
