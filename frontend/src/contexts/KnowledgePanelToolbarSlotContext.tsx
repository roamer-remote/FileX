import { createContext, useContext } from 'react'

/** Drawer 顶栏工具栏挂载点（Portal 目标），避免提升 ReactNode 导致输入框重挂载 */
export const KnowledgePanelToolbarSlotContext = createContext<HTMLElement | null>(null)

export function useKnowledgePanelToolbarSlot(): HTMLElement | null {
  return useContext(KnowledgePanelToolbarSlotContext)
}
