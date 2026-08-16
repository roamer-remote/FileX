import { DeleteOutlined } from '@ant-design/icons'
import type { AntdIconProps } from '@ant-design/icons/lib/components/AntdIcon'

/** 全站统一的红色删除图标（垃圾桶轮廓） */
export function DeleteActionIcon({ className, ...props }: AntdIconProps) {
  const merged = className ? `fx-delete-icon ${className}` : 'fx-delete-icon'
  return <DeleteOutlined className={merged} {...props} />
}
