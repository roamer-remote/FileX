import api from './index'
import type { UiStateResponse, UserUiStateV1 } from '@/lib/uiStateTypes'

export function getUiState() {
  return api.get<UiStateResponse>('/account/ui-state', { skipErrorToast: true })
}

export function putUiState(patch: Record<string, unknown>) {
  return api.put<UiStateResponse>('/account/ui-state', patch, { skipErrorToast: true })
}

export function migrateUiState(snapshot: UserUiStateV1) {
  return api.post<UiStateResponse>('/account/ui-state/migrate', snapshot, { skipErrorToast: true })
}
