import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CaretDownOutlined, CaretRightOutlined } from '@ant-design/icons'
import { Modal, TreeSelect } from 'antd'
import type { DataNode } from 'antd/es/tree'
import type { TreeNodeProps } from 'rc-tree'
import type { FolderItem } from '@/api/folders'
import { buildFolderTree } from '@/lib/folderTree'
import FolderTreeIcon from './FolderTreeIcon'
import './MoveToFolderModal.css'

export type MoveToFolderValue = number | 'uncategorized'

type MoveFolderTreeNode = DataNode & {
  value: MoveToFolderValue
  title: string
  hasChildren?: boolean
  isUncategorized?: boolean
  children?: MoveFolderTreeNode[]
}

function mapTreeNodes(nodes: ReturnType<typeof buildFolderTree>): MoveFolderTreeNode[] {
  return nodes.map((n) => ({
    value: n.id,
    title: n.name,
    key: n.id,
    hasChildren: n.children.length > 0,
    children: n.children.length > 0 ? mapTreeNodes(n.children) : undefined,
  }))
}

function buildMoveTreeData(folders: FolderItem[], uncategorizedLabel: string): MoveFolderTreeNode[] {
  const tree = buildFolderTree(folders)
  return [
    {
      value: 'uncategorized',
      title: uncategorizedLabel,
      key: 'uncategorized',
      isUncategorized: true,
    },
    ...mapTreeNodes(tree),
  ]
}

type Props = {
  open: boolean
  folders: FolderItem[]
  initialFolderId: number | null
  onCancel: () => void
  onConfirm: (value: MoveToFolderValue) => void | Promise<void>
  confirming?: boolean
}

export default function MoveToFolderModal({
  open,
  folders,
  initialFolderId,
  onCancel,
  onConfirm,
  confirming,
}: Props) {
  const { t } = useTranslation()
  const treeData = useMemo(
    () => buildMoveTreeData(folders, t('folders.uncategorized')),
    [folders, t],
  )
  const initialValue: MoveToFolderValue =
    initialFolderId == null ? 'uncategorized' : initialFolderId
  const [value, setValue] = useState<MoveToFolderValue>(initialValue)

  useEffect(() => {
    if (open) setValue(initialValue)
  }, [open, initialValue])

  return (
    <Modal
      title={t('folders.moveTo')}
      open={open}
      onCancel={onCancel}
      destroyOnHidden
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      confirmLoading={confirming}
      onOk={() => void onConfirm(value)}
    >
      <p style={{ marginBottom: 12, color: 'var(--text-secondary)', fontSize: 13 }}>
        {t('folders.moveHint')}
      </p>
      <TreeSelect
        className="move-folder-tree-select"
        popupClassName="move-folder-tree-select-popup"
        style={{ width: '100%' }}
        treeData={treeData}
        value={value}
        placeholder={t('folders.selectTarget')}
        treeDefaultExpandAll
        treeLine={{ showLeafIcon: false }}
        showSearch
        treeNodeFilterProp="title"
        listHeight={280}
        switcherIcon={({ expanded }: TreeNodeProps<DataNode>) =>
          expanded ? (
            <CaretDownOutlined className="move-folder-tree-switcher-icon" aria-hidden />
          ) : (
            <CaretRightOutlined className="move-folder-tree-switcher-icon" aria-hidden />
          )
        }
        treeTitleRender={(node) => {
          const data = node as MoveFolderTreeNode & { expanded?: boolean }
          const iconVariant = data.isUncategorized ? 'uncategorized' : 'child'
          const open = Boolean(data.hasChildren && data.expanded)
          return (
            <span className="move-folder-tree-node">
              <FolderTreeIcon
                variant={iconVariant}
                open={open}
                className="move-folder-tree-node-icon"
              />
              <span className="move-folder-tree-node-label">{data.title}</span>
            </span>
          )
        }}
        onChange={(v) => setValue(v as MoveToFolderValue)}
      />
    </Modal>
  )
}
