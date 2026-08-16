import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Spin } from 'antd'
import { getLicenseStatus, LICENSE_INVALID_EVENT, type LicenseStatus } from '@/api/license'
import LicenseGate from './LicenseGate'

type Props = {
  children: ReactNode
}

export default function LicenseRoot({ children }: Props) {
  const [status, setStatus] = useState<LicenseStatus | null>(null)
  const [loading, setLoading] = useState(true)

  const refetch = useCallback(async () => {
    try {
      const res = await getLicenseStatus({ skipErrorToast: true })
      setStatus(res.data)
    } catch {
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refetch()
  }, [refetch])

  useEffect(() => {
    const onInvalid = () => {
      void refetch()
    }
    window.addEventListener(LICENSE_INVALID_EVENT, onInvalid)
    return () => window.removeEventListener(LICENSE_INVALID_EVENT, onInvalid)
  }, [refetch])

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (status && !status.valid) {
    return <LicenseGate status={status} onActivated={refetch} />
  }

  return children
}
