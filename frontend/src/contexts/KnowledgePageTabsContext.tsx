import { createContext, useContext } from 'react'

export type KnowledgePageTabKey = 'files' | 'wikiPages' | 'wikiLinks' | 'tags' | 'libraryMap' | 'eval'

const KnowledgePageTabsContext = createContext<KnowledgePageTabKey | null>(null)

export function KnowledgePageTabsProvider({
  activeTab,
  children,
}: {
  activeTab: KnowledgePageTabKey | null
  children: React.ReactNode
}) {
  return (
    <KnowledgePageTabsContext.Provider value={activeTab}>{children}</KnowledgePageTabsContext.Provider>
  )
}

export function useKnowledgePageTab(): KnowledgePageTabKey | null {
  return useContext(KnowledgePageTabsContext)
}
