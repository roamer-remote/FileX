import { Avatar } from 'antd'
import { useAuthStore } from '@/stores/authStore'
import { useUserAvatarUrl } from '@/hooks/useUserAvatarUrl'

export default function UserNavAvatar() {
  const user = useAuthStore((s) => s.user)
  const avatarRevision = useAuthStore((s) => s.avatarRevision)
  const { avatarUrl, initial } = useUserAvatarUrl(user?.has_avatar, user?.username, avatarRevision)

  return (
    <Avatar size={24} className="user-nav-avatar" src={avatarUrl ?? undefined} alt="">
      {!avatarUrl ? initial : null}
    </Avatar>
  )
}
