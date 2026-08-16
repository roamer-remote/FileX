/**
 * @vitest-environment jsdom
 */

import { act } from 'react-dom/test-utils'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { useMqMonitorTab, type MqMonitorTab } from './useMqMonitorTab'

const STORAGE_KEY = 'filex_mq_monitor_tab'

let tabRef: MqMonitorTab = 'factory'
let setTabRef: (next: MqMonitorTab) => void = () => {}

function TabProbe() {
  const [tab, setTab] = useMqMonitorTab()
  tabRef = tab
  setTabRef = setTab
  return null
}

describe('useMqMonitorTab', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    localStorage.clear()
    tabRef = 'factory'
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
  })

  it('defaults to factory when localStorage is empty', () => {
    act(() => {
      root.render(<TabProbe />)
    })
    expect(tabRef).toBe('factory')
  })

  it('reads classic from localStorage', () => {
    localStorage.setItem(STORAGE_KEY, 'classic')
    act(() => {
      root.render(<TabProbe />)
    })
    expect(tabRef).toBe('classic')
  })

  it('falls back to factory for invalid stored values', () => {
    localStorage.setItem(STORAGE_KEY, 'invalid')
    act(() => {
      root.render(<TabProbe />)
    })
    expect(tabRef).toBe('factory')
  })

  it('persists tab changes to localStorage', () => {
    act(() => {
      root.render(<TabProbe />)
    })
    act(() => {
      setTabRef('classic')
    })
    expect(tabRef).toBe('classic')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('classic')

    act(() => {
      setTabRef('factory')
    })
    expect(tabRef).toBe('factory')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('factory')
  })
})
