import { createContext, useContext, type ReactNode } from 'react'
import { useAdminMqWebSocket } from '@/hooks/useAdminMqWebSocket'

type MqStatusValue = ReturnType<typeof useAdminMqWebSocket>

const MqStatusContext = createContext<MqStatusValue | null>(null)

export function MqStatusProvider({ enabled, children }: { enabled: boolean; children: ReactNode }) {
  const value = useAdminMqWebSocket(enabled)
  return <MqStatusContext.Provider value={value}>{children}</MqStatusContext.Provider>
}

export function useMqStatus() {
  const ctx = useContext(MqStatusContext)
  if (!ctx) {
    throw new Error('useMqStatus must be used within MqStatusProvider')
  }
  return ctx
}
