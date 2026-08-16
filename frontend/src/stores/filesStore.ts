import { create } from 'zustand'
import { getFiles, FOLDER_ID_UNCATEGORIZED, type FileItem } from '@/api/files'
import { getStorageToken } from '@/api/index'
import type { FolderSelection } from '@/lib/folderTree'
import { getActiveWorkspaceId } from '@/stores/workspaceStore'

let filesLoadGeneration = 0

export type LoadFilesOptions = {
  /** 后台轮询刷新时不展示全表 loading（WebSocket 兜底轮询）。 */
  silent?: boolean
}

type FilesState = {
  files: FileItem[]
  total: number
  page: number
  pageSize: number
  loading: boolean
  searchKeyword: string
  tagFilter: string
  tagFilter2: string
  timeSortOrder: 'desc' | 'asc'
  nameSortOrder: 'desc' | 'asc'
  listSortBy: 'time' | 'name'
  folderFilter: FolderSelection
  setFolderFilter: (filter: FolderSelection) => void
  loadFiles: (options?: LoadFilesOptions) => Promise<void>
  search: (keyword: string) => void
  setTagFilter: (tag: string) => void
  setTagFilters: (tag: string, tag2?: string) => void
  clearTagFilters: () => void
  setTimeSortOrder: (order: 'desc' | 'asc') => void
  toggleTimeSort: () => void
  toggleNameSort: () => void
  setPage: (p: number) => void
  setPageSize: (s: number) => void
  setPagination: (p: number, ps: number) => void
  patchFileIndex: (
    fileId: number,
    patch: Partial<
      Pick<
        FileItem,
        | 'index_status'
        | 'chunk_count'
        | 'index_error'
        | 'kb_post_status'
        | 'kb_post_error'
        | 'extract_status'
        | 'extract_error'
        | 'extracted_at'
        | 'extract_engine'
        | 'has_md'
        | 'md_has_content'
        | 'preview_mime_type'
        | 'okf_concept_path'
        | 'okf_type'
        | 'okf_metadata'
        | 'tags'
      >
    >,
  ) => void
}

export const useFilesStore = create<FilesState>((set, get) => ({
  files: [],
  total: 0,
  page: 1,
  pageSize: 20,
  loading: false,
  searchKeyword: '',
  tagFilter: '',
  tagFilter2: '',
  timeSortOrder: 'desc',
  nameSortOrder: 'asc',
  listSortBy: 'time',
  folderFilter: 'all',

  loadFiles: async (options) => {
    if (!getStorageToken()) return
    const gen = ++filesLoadGeneration
    if (!options?.silent) {
      set({ loading: true })
    }
    try {
      const { page, pageSize, searchKeyword, tagFilter, tagFilter2, timeSortOrder, nameSortOrder, listSortBy, folderFilter } = get()
      const wsId = getActiveWorkspaceId()
      const listParams: Parameters<typeof getFiles>[0] = {
        workspace_id: wsId ?? undefined,
        search: searchKeyword || undefined,
        tag: tagFilter || undefined,
        tag2: tagFilter && tagFilter2 ? tagFilter2 : undefined,
        ...(listSortBy === 'name'
          ? { sort_name: nameSortOrder }
          : { sort_time: timeSortOrder }),
        page,
        page_size: pageSize,
      }
      if (folderFilter === 'uncategorized') {
        listParams.folder_id = FOLDER_ID_UNCATEGORIZED
      } else if (typeof folderFilter === 'number') {
        listParams.folder_id = folderFilter
      }
      const res = await getFiles(listParams)
      if (gen !== filesLoadGeneration) return
      set({ files: res.data.items, total: res.data.total })
    } finally {
      if (gen === filesLoadGeneration && !options?.silent) {
        set({ loading: false })
      }
    }
  },

  search: (keyword: string) => {
    set({ searchKeyword: keyword, page: 1 })
    void get().loadFiles()
  },

  setTagFilter: (tag: string) => {
    set({ tagFilter: tag, tagFilter2: '', page: 1 })
    void get().loadFiles()
  },

  setTagFilters: (tag: string, tag2?: string) => {
    const t2 = tag2?.trim() ?? ''
    set({
      tagFilter: tag,
      tagFilter2: t2 && t2 !== tag ? t2 : '',
      page: 1,
    })
    void get().loadFiles()
  },

  clearTagFilters: () => {
    set({ tagFilter: '', tagFilter2: '', page: 1 })
    void get().loadFiles()
  },

  setTimeSortOrder: (order: 'desc' | 'asc') => {
    set({ listSortBy: 'time', timeSortOrder: order, page: 1 })
    void get().loadFiles()
  },

  toggleTimeSort: () => {
    const { listSortBy, timeSortOrder } = get()
    if (listSortBy === 'time') {
      set({ timeSortOrder: timeSortOrder === 'desc' ? 'asc' : 'desc', page: 1 })
    } else {
      set({ listSortBy: 'time', page: 1 })
    }
    void get().loadFiles()
  },

  toggleNameSort: () => {
    const { listSortBy, nameSortOrder } = get()
    if (listSortBy === 'name') {
      set({ nameSortOrder: nameSortOrder === 'desc' ? 'asc' : 'desc', page: 1 })
    } else {
      set({ listSortBy: 'name', page: 1 })
    }
    void get().loadFiles()
  },

  setFolderFilter: (filter: FolderSelection) => {
    set({ folderFilter: filter, page: 1 })
    void get().loadFiles()
  },

  setPage: (p: number) => {
    set({ page: p })
    void get().loadFiles()
  },

  setPageSize: (s: number) => {
    set({ pageSize: s, page: 1 })
    void get().loadFiles()
  },

  setPagination: (p: number, ps: number) => {
    const cur = get()
    const nextPage = cur.pageSize !== ps ? 1 : p
    set({ page: nextPage, pageSize: ps })
    void get().loadFiles()
  },

  patchFileIndex: (fileId, patch) => {
    set((state) => {
      const idx = state.files.findIndex((f) => f.id === fileId)
      if (idx < 0) return state
      const next = [...state.files]
      next[idx] = { ...next[idx], ...patch }
      return { files: next }
    })
  },
}))
