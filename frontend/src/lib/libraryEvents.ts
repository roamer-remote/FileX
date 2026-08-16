export const LIBRARY_STATS_REFRESH = 'filex:library-stats-refresh'

export function emitLibraryStatsRefresh(): void {
  window.dispatchEvent(new Event(LIBRARY_STATS_REFRESH))
}
