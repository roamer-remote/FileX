import { describe, expect, it } from 'vitest'
import {
  isKbIndexRoute,
  isKnowledgeFileListRoute,
  isKnowledgeLobbyRoute,
  knowledgeFileListPathForFolderSelection,
  showsFolderFloatingPanel,
} from './wikiLinkEvents'

describe('showsFolderFloatingPanel', () => {
  it('shows on all authenticated AppLayout routes', () => {
    expect(showsFolderFloatingPanel('/')).toBe(true)
    expect(showsFolderFloatingPanel('/files')).toBe(true)
    expect(showsFolderFloatingPanel('/knowledge-base')).toBe(true)
    expect(showsFolderFloatingPanel('/admin/users')).toBe(true)
    expect(showsFolderFloatingPanel('/api-keys')).toBe(true)
  })
})

describe('isKbIndexRoute', () => {
  it('matches knowledge base index page only', () => {
    expect(isKbIndexRoute('/knowledge-base')).toBe(true)
    expect(isKbIndexRoute('/')).toBe(false)
    expect(isKbIndexRoute('/admin/users')).toBe(false)
  })
})

describe('isKnowledgeFileListRoute', () => {
  it('matches file list pages only', () => {
    expect(isKnowledgeFileListRoute('/')).toBe(true)
    expect(isKnowledgeFileListRoute('/files')).toBe(true)
    expect(isKnowledgeFileListRoute('/files/abc')).toBe(true)
    expect(isKnowledgeFileListRoute('/knowledge-base')).toBe(false)
    expect(isKnowledgeFileListRoute('/admin/users')).toBe(false)
  })
})

describe('isKnowledgeLobbyRoute', () => {
  it('matches library lobby root only', () => {
    expect(isKnowledgeLobbyRoute('/')).toBe(true)
    expect(isKnowledgeLobbyRoute('')).toBe(true)
    expect(isKnowledgeLobbyRoute('/files')).toBe(false)
    expect(isKnowledgeLobbyRoute('/knowledge-base')).toBe(false)
    expect(isKnowledgeLobbyRoute('/admin/skill')).toBe(false)
  })
})

describe('knowledgeFileListPathForFolderSelection', () => {
  it('opens the files panel in one navigation from non-file-list routes', () => {
    expect(knowledgeFileListPathForFolderSelection('/knowledge-base')).toBe('/?panel=files')
    expect(knowledgeFileListPathForFolderSelection('/admin/users')).toBe('/?panel=files')
  })

  it('keeps same-page folder selection on the current route', () => {
    expect(knowledgeFileListPathForFolderSelection('/')).toBeNull()
    expect(knowledgeFileListPathForFolderSelection('/files')).toBeNull()
  })
})
