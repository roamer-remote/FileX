import { useEffect, useMemo, useState } from 'react'
import { fetchAvatarBlob } from '@/api/auth'

export function useUserAvatarUrl(
  hasAvatar: boolean | undefined,
  username: string | undefined,
  avatarRevision = 0,
) {
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null)

  const initial = useMemo(() => {
    const u = username?.trim()
    if (!u) return '?'
    return u.slice(0, 1).toUpperCase()
  }, [username])

  useEffect(() => {
    let revoked = false
    let objectUrl: string | null = null

    if (!hasAvatar) {
      setAvatarUrl(null)
      return () => undefined
    }

    void (async () => {
      const blob = await fetchAvatarBlob({ skipErrorToast: true, cacheBust: avatarRevision })
      if (revoked) return
      if (!blob || blob.size === 0) {
        setAvatarUrl(null)
        return
      }
      objectUrl = URL.createObjectURL(blob)
      setAvatarUrl(objectUrl)
    })()

    return () => {
      revoked = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [hasAvatar, avatarRevision])

  return { avatarUrl, initial }
}
