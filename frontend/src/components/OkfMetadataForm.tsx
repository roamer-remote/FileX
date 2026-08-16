import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Collapse, Form, Input, Select, Switch } from 'antd'
import { listMyTags } from '@/api/files'
import type { OkfMetadataDraft } from '@/lib/okfMetadata'
import { DEFAULT_OKF_TYPE } from '@/lib/okfMetadata'
import './OkfMetadataForm.css'

export type OkfMetadataFormProps = {
  draft: OkfMetadataDraft
  onChange: (next: OkfMetadataDraft) => void
  disabled?: boolean
  showAdvancedToggle?: boolean
  layout?: 'form' | 'collapse'
  onCollapseActiveChange?: (active: boolean) => void
}

export default function OkfMetadataForm({
  draft,
  onChange,
  disabled = false,
  showAdvancedToggle = true,
  layout = 'form',
  onCollapseActiveChange,
}: OkfMetadataFormProps) {
  const { t } = useTranslation()
  const [allTags, setAllTags] = useState<string[]>([])
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [tagInput, setTagInput] = useState('')

  useEffect(() => {
    void listMyTags()
      .then((res) => setAllTags(res.data))
      .catch(() => setAllTags([]))
  }, [])

  const fields = (
    <div className="okf-metadata-form-fields">
      <Form layout="vertical" disabled={disabled} className="okf-metadata-form">
        <Form.Item label={t('okfNative.title')} required>
          <Input
            value={draft.title}
            placeholder={t('okfNative.titlePlaceholder')}
            onChange={(e) => onChange({ ...draft, title: e.target.value })}
          />
        </Form.Item>
        <Form.Item label={t('okfNative.type')} required>
          <Input
            value={draft.type}
            placeholder={DEFAULT_OKF_TYPE}
            onChange={(e) => onChange({ ...draft, type: e.target.value })}
          />
        </Form.Item>
        <Form.Item label={t('okfNative.description')}>
          <Input.TextArea
            value={draft.description}
            placeholder={t('okfNative.descriptionPlaceholder')}
            autoSize={{ minRows: 2, maxRows: 4 }}
            onChange={(e) => onChange({ ...draft, description: e.target.value })}
          />
        </Form.Item>
        <Form.Item label={t('okfNative.tags')}>
          <Select
            mode="tags"
            style={{ width: '100%' }}
            placeholder={t('okfNative.tagsPlaceholder')}
            value={draft.tags}
            searchValue={tagInput}
            onSearch={setTagInput}
            onChange={(tags) => {
              onChange({ ...draft, tags })
              setTagInput('')
            }}
            tokenSeparators={[',', ' ', ';']}
            options={allTags.map((x) => ({ label: x, value: x }))}
          />
        </Form.Item>
        {showAdvancedToggle ? (
          <div className="okf-metadata-form-advanced">
            <Switch
              size="small"
              checked={advancedOpen}
              disabled={disabled}
              onChange={setAdvancedOpen}
            />
            <span className="okf-metadata-form-advanced-label">{t('okfNative.advancedPath')}</span>
          </div>
        ) : null}
        {showAdvancedToggle && advancedOpen ? (
          <Form.Item label={t('okfNative.conceptPath')} extra={t('okfNative.conceptPathHint')}>
            <Input
              value={draft.conceptPath}
              placeholder={t('okfNative.conceptPathPlaceholder')}
              onChange={(e) => onChange({ ...draft, conceptPath: e.target.value })}
            />
          </Form.Item>
        ) : null}
      </Form>
    </div>
  )

  if (layout === 'collapse') {
    return (
      <Collapse
        className="okf-metadata-collapse"
        bordered={false}
        onChange={(keys) => onCollapseActiveChange?.(keys.includes('okf'))}
        items={[
          {
            key: 'okf',
            label: t('okfNative.uploadPanelTitle'),
            children: (
              <>
                <p className="okf-metadata-collapse-hint">{t('okfNative.uploadPanelHint')}</p>
                {fields}
              </>
            ),
          },
        ]}
      />
    )
  }

  return fields
}
