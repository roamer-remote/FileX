import { useTranslation } from 'react-i18next'
import { Button, Descriptions, Empty, Space, Tag } from 'antd'
import type { DepartmentItem } from '@/api/adminRbac'
import { DeleteActionIcon } from '@/components/DeleteActionIcon'
import { departmentPathLabel } from '@/lib/departmentTree'

type DepartmentDetailPaneProps = {
  departments: DepartmentItem[]
  selectedDept: DepartmentItem | null
  onCreateChild: (parentId: number | null) => void
  onEdit: (dept: DepartmentItem) => void
  onDelete: (dept: DepartmentItem) => void
}

export default function DepartmentDetailPane({
  departments,
  selectedDept,
  onCreateChild,
  onEdit,
  onDelete,
}: DepartmentDetailPaneProps) {
  const { t } = useTranslation()

  if (!selectedDept) {
    return (
      <div className="admin-org-detail-pane admin-org-detail-pane--empty">
        <Empty description={t('adminRbac.departmentDetailEmpty')} />
        <Button type="primary" onClick={() => onCreateChild(null)}>
          {t('adminRbac.addDepartment')}
        </Button>
      </div>
    )
  }

  const path = departmentPathLabel(departments, selectedDept.id) || selectedDept.name

  return (
    <div className="admin-org-detail-pane">
      <Descriptions
        title={selectedDept.name}
        column={1}
        size="small"
        bordered
        className="admin-org-detail-descriptions"
      >
        <Descriptions.Item label={t('adminRbac.fieldDepartmentName')}>
          {selectedDept.name}
          {selectedDept.is_builtin ? (
            <Tag style={{ marginInlineStart: 8 }}>{t('adminRbac.builtin')}</Tag>
          ) : null}
        </Descriptions.Item>
        <Descriptions.Item label={t('adminRbac.fieldDepartmentPath')}>
          {path}
        </Descriptions.Item>
        <Descriptions.Item label={t('adminRbac.fieldSortOrder')}>
          {selectedDept.sort_order}
        </Descriptions.Item>
      </Descriptions>
      <Space wrap className="admin-org-detail-actions">
        <Button type="primary" onClick={() => onCreateChild(selectedDept.id)}>
          {t('adminRbac.addChildDepartment')}
        </Button>
        {!selectedDept.is_builtin ? (
          <>
            <Button onClick={() => onEdit(selectedDept)}>{t('adminRbac.edit')}</Button>
            <Button danger icon={<DeleteActionIcon />} onClick={() => onDelete(selectedDept)}>
              {t('adminRbac.delete')}
            </Button>
          </>
        ) : null}
      </Space>
    </div>
  )
}
